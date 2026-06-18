"""Coaching pass: turn engine results + positional facts into strategy coaching.

Architecture: one focused LLM call PER key moment (so the model reasons about a
single position at a time, and WE assign the ply so navigation is always correct),
plus one game-level call for the opening assessment, themes, and takeaways.

Supports two backends:
  - "ollama"  — free local LLM via Ollama (default)
  - "claude"  — Anthropic API (requires API key)
"""
import io
import json
import re

import httpx
import chess
import chess.pgn

from . import db, engine, features, settings

# Controlled vocabulary so cross-game profiling can GROUP BY slug later.
THEME_SLUGS = [
    "isolated-queen-pawn", "weak-pawn-structure", "bad-bishop", "weak-color-complex",
    "passive-pieces", "undeveloped-pieces", "premature-attack", "missed-pawn-break",
    "wrong-piece-trade", "gave-up-bishop-pair", "weak-king", "ignored-open-file",
    "no-plan-drift", "space-concession", "missed-outpost", "overextension",
    "endgame-technique", "time-trouble", "tactical-oversight", "missed-tactic",
]


def _str(v) -> str:
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return str(v) if v else ""


# --- shared prompt fragments -------------------------------------------------

_GROUNDING = """GROUNDING RULES (follow strictly — accuracy matters more than eloquence):
- You are given an exact PIECE PLACEMENT list for the position. You may ONLY name a square or
  piece that appears in that list. NEVER state a piece is on a square unless the placement
  confirms it. If you are unsure where a piece is, do not mention it.
- You are told whether the student is White or Black. NEVER attribute the student's move to the
  opponent, or an opponent's piece to the student. Keep the two sides straight. "Your" pieces are
  the student's color in the placement list.
- For ANY claim that a move attacks, threatens, pressures, defends, captures, or checks something,
  use ONLY the "CONSEQUENCES" section. If CONSEQUENCES says the move attacks NO enemy pieces, you
  must NOT say it attacks or pressures anything. If you want to write "attacks the X on e5", the
  CONSEQUENCES must list "X on e5" — otherwise do not write it.
- PIECE TYPE IS FIXED BY THE DATA. The piece on a square is exactly the type stated in PIECE
  PLACEMENT, CONSEQUENCES, or "Captures in the engine's line". Never substitute a different type.
  If c6 holds a queen, never call it a knight; if c8 holds a rook, never call it a bishop.
- Do NOT say a move "captures", "wins", or "gains" a piece unless the "Captures in the engine's
  line" section lists that exact capture. Attacking a piece is not the same as winning it —
  the enemy can move it. Don't claim material gain that the capture list doesn't show.
- Do not invent pawn-structure features (passed/isolated/backward pawns, outposts, open files).
  Use only what the "Position facts" section states. If it isn't listed, it isn't there.
- If a claim isn't supported by the placement, facts, consequences, or engine lines, do not make it."""

_DEPTH = """DEPTH — the student wants real strategic understanding, not move labels or eval numbers
read aloud. You are given the engine's top candidate moves with evaluations (ENGINE CANDIDATES);
your job is to INTERPRET them. Work in BOTH layers, leading with strategy:

STRATEGIC LAYER (lead with this):
- Translate the evaluation into human terms: which side is better and concretely WHY — name the
  structural and piece-quality reasons, never just the number.
- Read the imbalances: good vs bad bishop, whether a knight is worth more than a bishop in THIS
  pawn structure (and why), the bishop pair, space, weak color complexes, who owns the key
  files/diagonals/squares and outposts.
- State the PLAN the position calls for: which part of the board to play on (kingside, queenside,
  or centre), the pawn break or lever that opens it, and the key squares each side must fight for.
- Compare the ENGINE CANDIDATES against what was played: what the better move achieves
  positionally and what the played move conceded (a square, a file, the bishop pair, the
  initiative). Make the change in the balance concrete.
- When an engine line involves a sacrifice or concession, explain the positional COMPENSATION.

TACTICAL LAYER (make the strategy concrete):
- Ground the plan in actual moves: which piece goes where, what the CONSEQUENCES confirm a move
  attacks/defends, and the short forcing line that makes the idea work.
- Only state tactics confirmed by the CONSEQUENCES section and the engine lines provided.

Tie the two together — the tactics should serve the strategic plan, not float free."""


MOMENT_SYSTEM = f"""You are a chess coach specializing in POSITIONAL and STRATEGIC understanding.
You will analyze ONE moment from the student's game in depth. Speak to the student directly ("you").

{_GROUNDING}

{_DEPTH}

Respond with a SINGLE JSON object using EXACTLY these two keys and nothing else:
{{
  "title": "<a 3-6 word label specific to this actual position>",
  "explanation": "<4-7 sentences. LEAD with the strategic interpretation (which side is better and why; the key imbalance; the plan and the squares/files to fight for; how the engine candidates change the balance versus what was played). THEN ground it in concrete tactics confirmed by the CONSEQUENCES section and engine lines. Tie the tactics to the plan.>"
}}
Base every claim only on the data in the user message. Output no other keys."""


SUMMARY_SYSTEM = f"""You are a chess coach. You are given an overview of one of the student's games
and the key moments already analyzed. Write the opening assessment, recurring strategic themes, and
study takeaways. Speak to the student directly ("you"). Ground every claim in the data given — do
not invent specific squares or piece locations you were not provided.

You are given an EVALUATION SCOREBOARD. Your opening_summary MUST agree with it about who stood
better — never say you came out of the opening worse if the scoreboard shows you winning, or
vice versa.

If a TIME USAGE section is provided and it shows the student rushing (sped up, mistakes played
quickly, or lots of unused clock), include ONE takeaway about spending time on critical moves —
specifically a pre-move check for hanging pieces, checks, and captures. Cite the real numbers.

Respond with a SINGLE JSON object using EXACTLY these keys:
{{
  "opening_summary": "<2-4 sentences: the opening and pawn structure, how you handled it, and who stood better coming out of the opening and why>",
  "themes": [
    {{"slug": "<one of the allowed slugs>", "side": "user", "severity": "minor|significant|decisive", "ply_start": <int>, "ply_end": <int>, "note": "<short note grounded in the game>"}}
  ],
  "takeaways": ["<a concrete study recommendation based on the recurring issues in THIS game>", "<another, if warranted>"]
}}
Use only the allowed theme slugs listed in the user message."""


# --- per-moment data block ---------------------------------------------------

def _safe_consequences(board: chess.Board, uci: str | None) -> str:
    if not uci:
        return ""
    try:
        return features.move_consequences(board, chess.Move.from_uci(uci))
    except Exception:
        return ""


def _annotate_captures(board_before_fen: str, san_line: str) -> str:
    """Spell out every capture in the engine's line with exact piece identities, so the
    model can't misname what a move 'takes' (e.g. queen-on-c6 narrated as a knight)."""
    if not san_line:
        return ""
    b = chess.Board(board_before_fen)
    notes = []
    for san in san_line.split():
        try:
            mv = b.parse_san(san)
        except Exception:
            break
        if b.is_capture(mv):
            mover = b.piece_at(mv.from_square)
            victim = b.piece_at(mv.to_square)
            vname = chess.piece_name(victim.piece_type) if victim else "pawn"
            mname = chess.piece_name(mover.piece_type) if mover else "piece"
            notes.append(f"{san}: {mname} takes {vname} on {chess.square_name(mv.to_square)}")
        b.push(mv)
    if not notes:
        return "Captures in the engine's line: NONE — this line wins no material.\n"
    return ("Captures in the engine's line (exact identities — use these, never guess a "
            "piece type):\n  " + "; ".join(notes) + "\n")


def _scoreboard(moves: list[dict], user_white: bool) -> str:
    """A compact eval timeline from the student's perspective — the ground truth for who
    stood better, so the opening summary can't invert it."""
    if not moves:
        return ""

    def ucp(m):
        if m["eval_mate"] is not None:
            return 10000 if ((m["eval_mate"] > 0) == user_white) else -10000
        cp = m["eval_cp"] or 0
        return cp if user_white else -cp

    def word(cp):
        if cp >= 250: return "winning"
        if cp >= 80: return "clearly better"
        if cp > -80: return "roughly equal"
        if cp > -250: return "clearly worse"
        return "losing"

    opening = None
    for m in moves:
        if m["ply"] <= 24:
            opening = m
    last = moves[-1]
    samples = [f"m{(m['ply'] + 1) // 2}:{_persp_eval(m['eval_cp'], m['eval_mate'], user_white)}"
               for m in moves if m["ply"] % 8 == 0 or m["ply"] == last["ply"]]
    lines = ["EVALUATION SCOREBOARD (engine, from YOUR perspective, + = better for you. This is the "
             "ground truth for who stood better — your opening_summary MUST agree with it):"]
    if opening is not None:
        lines.append(f"- Out of the opening (move {(opening['ply'] + 1) // 2}) you were "
                     f"{word(ucp(opening))} ({_persp_eval(opening['eval_cp'], opening['eval_mate'], user_white)}).")
    lines.append(f"- Final: {word(ucp(last))} "
                 f"({_persp_eval(last['eval_cp'], last['eval_mate'], user_white)}).")
    lines.append("- Trajectory: " + " ".join(samples))
    return "\n".join(lines) + "\n"


def _persp_eval(cp: int | None, mate: int | None, user_white: bool) -> str:
    """Format a white-POV engine score from the student's perspective (+ = better for you)."""
    if mate is not None:
        m = mate if user_white else -mate
        return f"{'+' if m > 0 else '-'}M{abs(m)}"
    if cp is None:
        return "?"
    v = (cp if user_white else -cp) / 100
    return f"{'+' if v >= 0 else ''}{v:.1f}"


def _candidates_block(candidates: list[dict], user_white: bool) -> str:
    if not candidates:
        return ""
    lines = ["ENGINE CANDIDATES from this position (eval from YOUR perspective, + = better for you "
             "— interpret these positionally, do not just restate the numbers):"]
    for i, c in enumerate(candidates, 1):
        ev = _persp_eval(c.get("eval_cp"), c.get("eval_mate"), user_white)
        lines.append(f"  {i}. {c['move']} ({ev})  line: {c['line']}")
    return "\n".join(lines) + "\n"


def _moment_block(m: dict, board_before_fen: str, user_color: str,
                  candidates: list[dict] | None = None) -> str:
    board = chess.Board(board_before_fen)
    facts = features.describe(board)
    placement = features.piece_placement(board)
    user_white = user_color == "white"
    played_consequences = _safe_consequences(board, m.get("uci"))
    candidates_block = _candidates_block(candidates or [], user_white)
    played_eval = _persp_eval(m.get("eval_cp"), m.get("eval_mate"), user_white)
    time_line = (f"TIME: you spent {m['time_spent']:.0f}s on this move.\n"
                 if m.get("time_spent") is not None else "")
    move_no = (m["ply"] + 1) // 2
    dots = "." if m["ply"] % 2 == 1 else "..."
    mtype = m.get("moment_type", "negative")
    side = user_color.capitalize()
    if mtype == "positive":
        label = "STRONG MOVE"
        task = (f"You ({side}) played {move_no}{dots} {m['san']}, the engine's top choice. "
                f"Explain WHY this was the right strategic/positional decision.")
        loss_line = ""
        best_consequences = ""
        best_captures = ""
    else:
        label = "MISTAKE"
        task = (f"You ({side}) played {move_no}{dots} {m['san']}; the engine preferred "
                f"{m['best_san']}. Explain what the position demanded and why your move was "
                f"inferior, in terms of plans, structure, and piece quality.")
        loss_line = f"Win% your move gave away: {m['win_pct_loss']}\n"
        bc = _safe_consequences(board, m.get("best_uci"))
        best_consequences = f"For comparison, the engine's move {m['best_san']} —\n{bc}\n" if bc else ""
        best_captures = _annotate_captures(board_before_fen, m.get("best_line") or "")
    return (
        f"--- {label} at ply {m['ply']} — you are {side} ---\n"
        f"{task}\n"
        f"{loss_line}"
        f"PIECE PLACEMENT before your move (use ONLY these squares — do not invent others):\n"
        f"{placement}\n"
        f"Position facts:\n{facts}\n"
        f"{candidates_block}"
        f"YOU PLAYED {m['san']} (eval after your move from your perspective: {played_eval}).\n"
        f"{time_line}"
        f"{played_consequences}\n"
        f"{best_consequences}"
        f"Engine's best line from here: {m['best_line'] or m['best_san']}\n"
        f"{best_captures}"
    )


# --- user-message builders ---------------------------------------------------

def _moment_user_prompt(game: dict, user_color: str, block: str) -> str:
    user_name = game["white"] if user_color == "white" else game["black"]
    opening = game.get("opening") or game.get("eco") or "unknown"
    return (
        f"Student is {user_name}, playing {user_color}. Opening: {opening}.\n\n"
        f"{block}\n"
        f"Analyze THIS moment in depth per your instructions. JSON only."
    )


def _summary_user_prompt(game: dict, user_color: str, moments_out: list[dict],
                         counts: dict, movetext: str) -> str:
    user_name = game["white"] if user_color == "white" else game["black"]
    user_elo = game["white_elo"] if user_color == "white" else game["black_elo"]
    opponent = game["black"] if user_color == "white" else game["white"]
    moment_list = "\n".join(
        f"- ply {km['ply']} ({km['moment_type']}): {km['title']}" for km in moments_out
    ) or "(no individually flagged moments)"
    scoreboard = _scoreboard(game.get("moves") or [], user_color == "white")
    tr = engine.time_report(game.get("moves") or [], user_color)
    time_block = ""
    if tr:
        rushed = "; ".join(
            f"{r['san']} ({r['classification']}, {r['time_spent']:.0f}s)" for r in tr["rushed"]
        ) or "none under 25s"
        unused = f"{tr['unused_secs'] / 60:.1f} min" if tr["unused_secs"] is not None else "unknown"
        time_block = (
            "TIME USAGE (clock data from the game):\n"
            f"- Average {tr['avg']:.0f}s/move; early {tr['early_avg']:.0f}s vs late {tr['late_avg']:.0f}s "
            f"({'SPED UP markedly in the second half' if tr['sped_up'] else 'fairly steady'}).\n"
            f"- Clock left unused at the end: {unused}.\n"
            f"- Mistakes played quickly (<25s): {rushed}.\n\n"
        )
    return (
        f"Student: {user_name} ({user_elo or '?'} elo), playing {user_color}.\n"
        f"Opponent: {opponent}. Result: {game['result']}. "
        f"Opening: {game.get('opening') or game.get('eco') or 'unknown'}. "
        f"Time control: {game.get('time_control')}.\n"
        f"Student's move quality: {counts['blunder']} blunders, {counts['mistake']} mistakes, "
        f"{counts['inaccuracy']} inaccuracies.\n\n"
        f"{scoreboard}\n"
        f"{time_block}"
        f"Key moments already analyzed:\n{moment_list}\n\n"
        f"Full game:\n{movetext}\n\n"
        f"Allowed theme slugs: {', '.join(THEME_SLUGS)}\n"
        f"Write the opening assessment, themes, and takeaways per your instructions. JSON only."
    )


# --- LLM backends ------------------------------------------------------------

def _call_ollama(prompt: str, cfg: dict, system: str, num_predict: int = 1800
                 ) -> tuple[str, str, int, int]:
    """Returns (text, model, input_tokens, output_tokens). Raises on error."""
    base = cfg["ollama_url"].rstrip("/")
    model = cfg["ollama_model"]
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.3,
            "num_predict": num_predict,
            # Ollama defaults num_ctx to 2048, which truncates these prompts;
            # 16384 fits comfortably on a 16GB GPU.
            "num_ctx": 16384,
        },
    }
    try:
        r = httpx.post(f"{base}/api/chat", json=payload, timeout=300)
        r.raise_for_status()
    except httpx.ConnectError:
        raise ValueError(
            "Cannot reach Ollama. Make sure it's running: open a terminal and run 'ollama serve'"
        )
    data = r.json()
    text = data["message"]["content"]
    return text, model, data.get("prompt_eval_count", 0), data.get("eval_count", 0)


def _call_claude(prompt: str, cfg: dict, system: str, max_tokens: int = 1800
                 ) -> tuple[str, str, int, int]:
    """Returns (text, model, input_tokens, output_tokens). Requires anthropic package."""
    import anthropic
    if not cfg.get("anthropic_api_key"):
        raise ValueError("No Anthropic API key configured (Settings screen)")
    client = anthropic.Anthropic(api_key=cfg["anthropic_api_key"])
    model = cfg["claude_model"]
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text, model, resp.usage.input_tokens, resp.usage.output_tokens


# --- orchestration -----------------------------------------------------------

def coach_game(game_id: int, progress: dict | None = None) -> dict:
    cfg = settings.load()
    with db.connect() as conn:
        game = db.get_game(conn, game_id)
    if game is None:
        raise ValueError(f"game {game_id} not found")
    if not game["moves"]:
        raise ValueError("run engine analysis first")

    user_color = game.get("user_color") or "white"
    moments = engine.key_moments(game["moves"], user_color, max_negative=7, max_positive=3)
    fen_by_ply = {m["ply"]: m["fen_after"] for m in game["moves"]}
    before_fens = [fen_by_ply.get(m["ply"] - 1, chess.STARTING_FEN) for m in moments]

    # total steps for the progress bar: engine candidate pass + one call per moment + summary
    if progress is not None:
        progress["total"] = len(moments) + 2
        progress["done"] = 0
        progress["label"] = "Gathering engine candidate moves…"

    candidates = (engine.batch_candidates(before_fens, multipv=cfg.get("engine_multipv", 3))
                  if moments else {})
    if progress is not None:
        progress["done"] = 1

    provider = cfg.get("coach_provider", "ollama")

    def call(prompt: str, system: str, budget: int) -> tuple[str, str, int, int]:
        if provider == "claude":
            return _call_claude(prompt, cfg, system, max_tokens=budget)
        return _call_ollama(prompt, cfg, system, num_predict=budget)

    in_tok = out_tok = 0
    model = cfg.get("claude_model") if provider == "claude" else cfg.get("ollama_model")

    # One focused call per moment. Ply / moment_type are OURS — never the model's.
    key_moments_out: list[dict] = []
    for idx, m in enumerate(moments):
        if progress is not None:
            progress["label"] = f"Analyzing key moment {idx + 1} of {len(moments)}…"
        before = fen_by_ply.get(m["ply"] - 1, chess.STARTING_FEN)
        block = _moment_block(m, before, user_color, candidates.get(before))
        text, model, ti, to = call(_moment_user_prompt(game, user_color, block), MOMENT_SYSTEM, 1500)
        in_tok += ti
        out_tok += to
        try:
            parsed = _parse_json(text)
        except Exception:
            parsed = {}
        explanation = (parsed.get("explanation") or parsed.get("analysis")
                       or parsed.get("note") or parsed.get("comment") or "")
        title = (parsed.get("title") or parsed.get("label") or m["san"])
        key_moments_out.append({
            "ply": m["ply"],
            "moment_type": m.get("moment_type", "negative"),
            "title": _str(title),
            "explanation": _str(explanation),
        })
        if progress is not None:
            progress["done"] = 1 + idx + 1

    # Game-level synthesis: opening, themes, takeaways.
    if progress is not None:
        progress["label"] = "Writing opening summary & takeaways…"
    counts = {"blunder": 0, "mistake": 0, "inaccuracy": 0}
    for mv in game["moves"]:
        is_user = (user_color == "white") == (mv["ply"] % 2 == 1)
        if is_user and mv["classification"] in counts:
            counts[mv["classification"]] += 1
    movetext = str(chess.pgn.read_game(io.StringIO(game["pgn"])).mainline_moves())
    text, model, ti, to = call(
        _summary_user_prompt(game, user_color, key_moments_out, counts, movetext),
        SUMMARY_SYSTEM, 1500)
    in_tok += ti
    out_tok += to
    if progress is not None:
        progress["done"] = progress["total"]
        progress["label"] = "Done"
    try:
        summ = _normalize(_parse_json(text))
    except Exception:
        summ = {"opening_summary": "", "themes": [], "takeaways": []}

    commentary = {
        "opening_summary": summ["opening_summary"],
        "key_moments": key_moments_out,
        "themes": summ["themes"],
        "takeaways": summ["takeaways"],
    }
    with db.connect() as conn:
        db.save_coach(conn, game_id, commentary, model, in_tok, out_tok)
        conn.commit()
    return commentary


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"coach returned non-JSON: {text[:200]}")
    return json.loads(text[start:end + 1])


def _normalize(raw: dict) -> dict:
    """Coerce the game-summary LLM JSON into our canonical shape.

    Used for the summary call (opening_summary / themes / takeaways). Per-moment
    output is assembled directly in coach_game, so key_moments here is incidental.
    """
    opening = (
        raw.get("opening_summary")
        or raw.get("opening_analysis")
        or raw.get("opening")
        or raw.get("summary")
        or raw.get("overview")
        or raw.get("introduction")
        or ""
    )

    themes_raw = raw.get("themes") or raw.get("strategic_themes") or raw.get("patterns") or []
    themes = []
    for t in themes_raw:
        if isinstance(t, str):
            themes.append({"slug": t, "side": "user", "severity": "minor",
                           "ply_start": None, "ply_end": None, "note": ""})
        elif isinstance(t, dict):
            themes.append(t)

    takeaways = (
        raw.get("takeaways")
        or raw.get("recommendations")
        or raw.get("study_recommendations")
        or raw.get("suggestions")
        or raw.get("advice")
        or []
    )
    if isinstance(takeaways, str):
        takeaways = [takeaways]
    if not isinstance(takeaways, list):
        takeaways = []

    return {
        "opening_summary": _str(opening),
        "themes": themes,
        "takeaways": [_str(t) for t in takeaways if t],
    }
