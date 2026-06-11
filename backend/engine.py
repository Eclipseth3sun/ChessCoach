"""Stockfish analysis pass: per-move evals, move classification, key moments.

Move quality is judged by win-probability loss (lichess-style), so a 2-pawn
slip in an already-lost position isn't branded a blunder.
"""
import io
import math
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from . import db, settings

ENGINE_PATH = Path(__file__).resolve().parent.parent / "engines" / "stockfish.exe"

# lichess centipawn -> win% curve
def win_pct(cp: int) -> float:
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


_PIECE_VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
              chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


def classify(loss: float, played_best: bool) -> str:
    if played_best:
        return "best"
    if loss >= 30:
        return "blunder"
    if loss >= 20:
        return "mistake"
    if loss >= 10:
        return "inaccuracy"
    return "good"


def _is_sacrifice(board: chess.Board, move: chess.Move) -> bool:
    """Heuristic: does this move hand the opponent material (>= a minor piece net)
    while leaving the moved piece capturable? Used to flag a 'brilliant' sac."""
    piece = board.piece_at(move.from_square)
    if piece is None:
        return False
    moved_val = _PIECE_VAL[piece.piece_type]
    captured_val = 0
    if board.is_capture(move):
        tp = board.piece_at(move.to_square)
        captured_val = _PIECE_VAL[tp.piece_type] if tp else 1  # en passant
    if moved_val - captured_val < 2:  # not giving up at least a minor net
        return False
    after = board.copy(stack=False)
    after.push(move)
    dest = move.to_square
    enemy = after.attackers(not piece.color, dest)
    if not enemy:
        return False
    defenders = after.attackers(piece.color, dest)
    cheapest = min(_PIECE_VAL[after.piece_at(s).piece_type] for s in enemy)
    return (not defenders) or cheapest <= moved_val


def _upgrade_best(sac: bool, mover_wp_before: float, mover_cp_after: int) -> str:
    """Refine a played-best move into brilliant / great / best.

    brilliant (!!): the best move is a sound sacrifice that keeps you in the game.
    great (!): the best move found while you were not already comfortable.
    """
    if sac and mover_cp_after >= -50:
        return "brilliant"
    if mover_wp_before < 55:
        return "great"
    return "best"


def _score_to_cp(score: chess.engine.PovScore) -> tuple[int, int | None]:
    """White-POV (clamped centipawns, mate distance or None)."""
    white = score.white()
    if white.is_mate():
        mate = white.mate()
        return (10000 if mate > 0 else -10000), mate
    return max(-1500, min(1500, white.score())), None


def analyze_game(game_id: int, progress: dict | None = None) -> None:
    """Run the engine over every position of a stored game and persist results."""
    cfg = settings.load()
    with db.connect() as conn:
        game_row = conn.execute("SELECT pgn FROM games WHERE id = ?", (game_id,)).fetchone()
    if game_row is None:
        raise ValueError(f"game {game_id} not found")

    game = chess.pgn.read_game(io.StringIO(game_row["pgn"]))
    nodes = list(game.mainline())
    limit = chess.engine.Limit(time=cfg["engine_movetime_ms"] / 1000)

    engine = chess.engine.SimpleEngine.popen_uci(str(ENGINE_PATH))
    engine.configure({"Threads": cfg["engine_threads"]})
    moves: list[dict] = []
    try:
        board = game.board()
        # eval of the starting position (for the first move's delta)
        info = engine.analyse(board, limit)
        prev_cp, _ = _score_to_cp(info["score"])
        prev_pv = info.get("pv") or []

        for i, node in enumerate(nodes):
            move = node.move
            san = board.san(move)
            best_san = best_line = best_uci = None
            if prev_pv:
                best_uci = prev_pv[0].uci()
                best_san = board.san(prev_pv[0])
                # SAN of the engine's preferred line from this position
                tmp = board.copy(stack=False)
                line = []
                for pv_move in prev_pv[:10]:
                    line.append(tmp.san(pv_move))
                    tmp.push(pv_move)
                best_line = " ".join(line)
            mover_white = board.turn == chess.WHITE
            sac = _is_sacrifice(board, move)  # must check before the move is made

            board.push(move)
            info = engine.analyse(board, limit)
            cp, mate = _score_to_cp(info["score"])

            # win% loss from the mover's perspective
            before = win_pct(prev_cp) if mover_white else 100 - win_pct(prev_cp)
            after = win_pct(cp) if mover_white else 100 - win_pct(cp)
            loss = max(0.0, before - after)
            played_best = best_uci == move.uci()
            if played_best:
                mover_cp_after = cp if mover_white else -cp
                classification = _upgrade_best(sac, before, mover_cp_after)
            else:
                classification = classify(loss, False)

            moves.append({
                "game_id": game_id,
                "ply": i + 1,
                "san": san,
                "uci": move.uci(),
                "fen_after": board.fen(),
                "eval_cp": cp,
                "eval_mate": mate,
                "best_uci": best_uci,
                "best_san": best_san,
                "best_line": best_line,
                "classification": classification,
                "win_pct_loss": round(loss, 1),
            })
            prev_cp = cp
            prev_pv = info.get("pv") or []
            if progress is not None:
                progress["done"] = i + 1
                progress["total"] = len(nodes)
    finally:
        engine.quit()

    with db.connect() as conn:
        db.save_engine_pass(conn, game_id, moves)
        conn.commit()


def get_bestline(fen: str, movetime_ms: int = 500, max_plies: int = 8) -> list[str]:
    """Return Stockfish's principal variation from `fen` as SAN moves.

    Uses a dedicated 500ms search for a high-quality PV, but truncates to
    `max_plies` (default 8 = ~4 moves per side). The full PV can run 14-20 moves
    and drift into incidental shuffling/trades that obscure the positional point;
    the first few moves are what actually demonstrate the engine's idea.
    """
    cfg = settings.load()
    board = chess.Board(fen)
    sf = chess.engine.SimpleEngine.popen_uci(str(ENGINE_PATH))
    sf.configure({"Threads": cfg["engine_threads"]})
    try:
        info = sf.analyse(board, chess.engine.Limit(time=movetime_ms / 1000))
        pv = (info.get("pv") or [])[:max_plies]
        sans: list[str] = []
        tmp = board.copy(stack=False)
        for move in pv:
            try:
                sans.append(tmp.san(move))
                tmp.push(move)
            except Exception:
                break
        return sans
    finally:
        sf.quit()


def batch_candidates(fens: list[str], multipv: int = 3, movetime_ms: int = 500,
                     line_plies: int = 6) -> dict[str, list[dict]]:
    """Top-N engine moves with evals + short SAN lines for each position.

    Opens one Stockfish process and analyses every key-moment position with
    MultiPV, so the coach can compare the engine's best move against its
    realistic alternatives (and what was actually played) and interpret the
    difference positionally. Eval is white-POV centipawns (mate distance or None).
    """
    cfg = settings.load()
    sf = chess.engine.SimpleEngine.popen_uci(str(ENGINE_PATH))
    sf.configure({"Threads": cfg["engine_threads"]})
    results: dict[str, list[dict]] = {}
    try:
        for fen in fens:
            if fen in results:
                continue
            board = chess.Board(fen)
            infos = sf.analyse(board, chess.engine.Limit(time=movetime_ms / 1000),
                               multipv=max(1, multipv))
            cands = []
            for info in infos:
                pv = info.get("pv") or []
                if not pv:
                    continue
                cp, mate = _score_to_cp(info["score"])
                tmp = board.copy(stack=False)
                sans = []
                for mv in pv[:line_plies]:
                    sans.append(tmp.san(mv))
                    tmp.push(mv)
                cands.append({"move": sans[0], "eval_cp": cp, "eval_mate": mate,
                              "line": " ".join(sans)})
            results[fen] = cands
    finally:
        sf.quit()
    return results


def key_moments(moves: list[dict], user_color: str | None,
                max_negative: int = 5, max_positive: int = 2) -> list[dict]:
    """Return annotated moments: the user's biggest mistakes + best plays in critical positions."""
    def is_user(m: dict) -> bool:
        if user_color is None:
            return True
        return (user_color == "white") == (m["ply"] % 2 == 1)

    user_plies = [m for m in moves if is_user(m)]

    # Negative: biggest win% losses
    negative = sorted(
        [m for m in user_plies if m["classification"] in ("blunder", "mistake", "inaccuracy")],
        key=lambda m: m["win_pct_loss"], reverse=True,
    )[:max_negative]

    # Positive: played engine's best in a contested or defensive situation.
    # We use eval_cp of the PREVIOUS move as the pre-move eval.
    eval_by_ply = {m["ply"]: m["eval_cp"] or 0 for m in moves}
    positive = []
    for m in user_plies:
        if m["classification"] != "best":
            continue
        cp_before = eval_by_ply.get(m["ply"] - 1, 0)
        mover_white = m["ply"] % 2 == 1
        wp_before = win_pct(cp_before) if mover_white else 100 - win_pct(cp_before)
        # Worth highlighting if the mover was not already comfortably winning (< 65% chance)
        if wp_before < 65:
            positive.append({**m, "moment_type": "positive"})

    positive = positive[:max_positive]
    all_moments = [{**m, "moment_type": "negative"} for m in negative] + positive
    all_moments.sort(key=lambda m: m["ply"])
    return all_moments
