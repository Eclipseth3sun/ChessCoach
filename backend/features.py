"""Deterministic positional feature extraction with python-chess.

These facts ground the Claude coaching pass so its prose describes the actual
board, not a hallucinated one.
"""
import chess

FILES = "abcdefgh"


def _pawn_files(board: chess.Board, color: chess.Color) -> list[int]:
    return sorted(chess.square_file(s) for s in board.pieces(chess.PAWN, color))


def isolated_pawns(board: chess.Board, color: chess.Color) -> list[str]:
    files = set(_pawn_files(board, color))
    out = []
    for sq in board.pieces(chess.PAWN, color):
        f = chess.square_file(sq)
        if (f - 1) not in files and (f + 1) not in files:
            out.append(chess.square_name(sq))
    return sorted(out)


def doubled_files(board: chess.Board, color: chess.Color) -> list[str]:
    files = _pawn_files(board, color)
    return sorted({FILES[f] for f in files if files.count(f) > 1})


def passed_pawns(board: chess.Board, color: chess.Color) -> list[str]:
    """Pawns with no enemy pawn ahead on their own or adjacent files."""
    enemy = board.pieces(chess.PAWN, not color)
    out = []
    for sq in board.pieces(chess.PAWN, color):
        f, r = chess.square_file(sq), chess.square_rank(sq)
        blocked = False
        for esq in enemy:
            ef, er = chess.square_file(esq), chess.square_rank(esq)
            if abs(ef - f) <= 1 and ((color == chess.WHITE and er > r) or
                                     (color == chess.BLACK and er < r)):
                blocked = True
                break
        if not blocked:
            out.append(chess.square_name(sq))
    return sorted(out)


def backward_pawns(board: chess.Board, color: chess.Color) -> list[str]:
    """Pawns whose stop square is controlled by an enemy pawn and that no
    friendly pawn on an adjacent file is level with or behind to support."""
    out = []
    direction = 1 if color == chess.WHITE else -1
    for sq in board.pieces(chess.PAWN, color):
        f, r = chess.square_file(sq), chess.square_rank(sq)
        stop_rank = r + direction
        if not (0 <= stop_rank <= 7):
            continue
        stop = chess.square(f, stop_rank)
        # supported now or later by a friendly pawn on an adjacent file?
        supported = any(
            abs(chess.square_file(p) - f) == 1
            and ((color == chess.WHITE and chess.square_rank(p) <= r)
                 or (color == chess.BLACK and chess.square_rank(p) >= r))
            for p in board.pieces(chess.PAWN, color) if p != sq
        )
        attacked = any(
            stop in board.attacks(e) for e in board.pieces(chess.PAWN, not color)
        )
        if attacked and not supported:
            out.append(chess.square_name(sq))
    return sorted(out)


def pawn_islands(board: chess.Board, color: chess.Color) -> int:
    files = sorted(set(_pawn_files(board, color)))
    if not files:
        return 0
    islands = 1
    for a, b in zip(files, files[1:]):
        if b - a > 1:
            islands += 1
    return islands


def open_files(board: chess.Board) -> dict:
    """{'open': [...], 'semi_open_white': [...], 'semi_open_black': [...]}"""
    wf, bf = set(_pawn_files(board, chess.WHITE)), set(_pawn_files(board, chess.BLACK))
    return {
        "open": [FILES[f] for f in range(8) if f not in wf and f not in bf],
        "semi_open_white": [FILES[f] for f in range(8) if f not in wf and f in bf],
        "semi_open_black": [FILES[f] for f in range(8) if f in wf and f not in bf],
    }


def bishop_situation(board: chess.Board, color: chess.Color) -> dict:
    bishops = list(board.pieces(chess.BISHOP, color))
    own_pawns = board.pieces(chess.PAWN, color)
    light_pawns = sum(1 for p in own_pawns if (chess.square_file(p) + chess.square_rank(p)) % 2 == 1)
    dark_pawns = len(own_pawns) - light_pawns
    info = {"bishop_pair": len(bishops) >= 2, "bishops": []}
    for b in bishops:
        light = (chess.square_file(b) + chess.square_rank(b)) % 2 == 1
        same_color_pawns = light_pawns if light else dark_pawns
        info["bishops"].append({
            "square": chess.square_name(b),
            "complex": "light" if light else "dark",
            "own_pawns_on_same_complex": same_color_pawns,
            "bad": same_color_pawns >= 4,
        })
    return info


def knight_outposts(board: chess.Board, color: chess.Color) -> list[str]:
    """Knights on ranks 4-6 (rel.), defended by a friendly pawn, and not
    evictable by an enemy pawn advance."""
    out = []
    for sq in board.pieces(chess.KNIGHT, color):
        rel_rank = chess.square_rank(sq) if color == chess.WHITE else 7 - chess.square_rank(sq)
        if not (3 <= rel_rank <= 5):
            continue
        defended = any(sq in board.attacks(p) for p in board.pieces(chess.PAWN, color))
        f, r = chess.square_file(sq), chess.square_rank(sq)
        evictable = False
        for esq in board.pieces(chess.PAWN, not color):
            ef, er = chess.square_file(esq), chess.square_rank(esq)
            if abs(ef - f) == 1 and ((color == chess.WHITE and er > r) or
                                     (color == chess.BLACK and er < r)):
                evictable = True
                break
        if defended and not evictable:
            out.append(chess.square_name(sq))
    return sorted(out)


def king_safety(board: chess.Board, color: chess.Color) -> dict:
    ksq = board.king(color)
    if ksq is None:
        return {}
    kf = chess.square_file(ksq)
    shield_rank = chess.square_rank(ksq) + (1 if color == chess.WHITE else -1)
    shield = 0
    if 0 <= shield_rank <= 7:
        for f in (kf - 1, kf, kf + 1):
            if 0 <= f <= 7:
                piece = board.piece_at(chess.square(f, shield_rank))
                if piece and piece.piece_type == chess.PAWN and piece.color == color:
                    shield += 1
    files = open_files(board)
    near = {FILES[f] for f in (kf - 1, kf, kf + 1) if 0 <= f <= 7}
    open_near = sorted(near & set(files["open"]))
    semi_key = "semi_open_black" if color == chess.WHITE else "semi_open_white"
    semi_near = sorted(near & set(files[semi_key]))  # semi-open from the attacker's side
    return {
        "square": chess.square_name(ksq),
        "pawn_shield": shield,
        "open_files_near_king": open_near,
        "semi_open_files_near_king": semi_near,
        "castled": kf >= 5 or kf <= 2,
    }


def space(board: chess.Board, color: chess.Color) -> int:
    """Squares in the opponent's half attacked by this side."""
    half = range(4, 8) if color == chess.WHITE else range(0, 4)
    return sum(
        1 for sq in chess.SQUARES
        if chess.square_rank(sq) in half and board.is_attacked_by(color, sq)
    )


def material(board: chess.Board, color: chess.Color) -> int:
    vals = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    return sum(len(board.pieces(pt, color)) * v for pt, v in vals.items())


def game_phase(board: chess.Board) -> str:
    non_pawn = material(board, chess.WHITE) + material(board, chess.BLACK) \
        - len(board.pieces(chess.PAWN, chess.WHITE)) - len(board.pieces(chess.PAWN, chess.BLACK))
    if board.fullmove_number <= 10 and non_pawn >= 50:
        return "opening"
    if non_pawn <= 16:
        return "endgame"
    return "middlegame"


def extract(board: chess.Board) -> dict:
    out = {"phase": game_phase(board), "sides": {}}
    for color, name in ((chess.WHITE, "white"), (chess.BLACK, "black")):
        out["sides"][name] = {
            "material": material(board, color),
            "isolated_pawns": isolated_pawns(board, color),
            "doubled_pawn_files": doubled_files(board, color),
            "backward_pawns": backward_pawns(board, color),
            "passed_pawns": passed_pawns(board, color),
            "pawn_islands": pawn_islands(board, color),
            "bishops": bishop_situation(board, color),
            "knight_outposts": knight_outposts(board, color),
            "king": king_safety(board, color),
            "space": space(board, color),
        }
    out["files"] = open_files(board)
    return out


def piece_placement(board: chess.Board) -> str:
    """Exact piece listing per side so the LLM never has to parse a FEN.

    FEN parsing is where local models invent squares and swap colors. Handing
    them an explicit roster (e.g. "White: Kg1, Qd3, Rf1, ...") removes the guesswork.
    """
    order = [chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]
    letter = {chess.KING: "K", chess.QUEEN: "Q", chess.ROOK: "R",
              chess.BISHOP: "B", chess.KNIGHT: "N", chess.PAWN: ""}
    lines = []
    for color, name in ((chess.WHITE, "White"), (chess.BLACK, "Black")):
        items = []
        for pt in order:
            for sq in sorted(board.pieces(pt, color)):
                items.append(f"{letter[pt]}{chess.square_name(sq)}")
        lines.append(f"{name}: {', '.join(items) if items else '(none)'}")
    return "\n".join(lines)


def move_consequences(board: chess.Board, move: chess.Move) -> str:
    """Deterministic facts about what a move concretely does.

    LLMs invent tactics ("attacks the knight on e5") when left to infer them.
    Computing the real consequences — what the moved piece attacks, whether it
    is defended/attacked, whether it gives check — gives the coach ground truth
    so it can explain the move without confabulating.
    """
    piece = board.piece_at(move.from_square)
    if piece is None:
        return ""
    mover = piece.color
    san = board.san(move)
    pname = chess.piece_name(piece.piece_type)
    after = board.copy(stack=False)
    after.push(move)
    dest = move.to_square
    dname = chess.square_name(dest)

    lines = [f"CONSEQUENCES of {san} (deterministic — use ONLY this for any claim "
             f"about attacks/threats/checks):"]
    lines.append(f"- The moved {pname} lands on {dname}.")

    attacked = []
    for sq in after.attacks(dest):
        p = after.piece_at(sq)
        if p and p.color != mover:
            attacked.append(f"{chess.piece_name(p.piece_type)} on {chess.square_name(sq)}")
    lines.append(f"- From {dname} it attacks: "
                 + (", ".join(attacked) if attacked else "NO enemy pieces"))

    defended = bool(after.attackers(mover, dest))
    attacked_back = bool(after.attackers(not mover, dest))
    state = "defended" if defended else "undefended"
    if attacked_back:
        state += " but attacked by the opponent (so it can be captured/traded)"
    lines.append(f"- The {pname} on {dname} is {state}.")

    if after.is_check():
        lines.append("- This move GIVES CHECK.")
    if board.is_capture(move):
        cap = board.piece_at(move.to_square) or (chess.Piece(chess.PAWN, not mover))
        lines.append(f"- This move CAPTURES the {chess.piece_name(cap.piece_type)} on {dname}.")
    return "\n".join(lines)


def describe(board: chess.Board) -> str:
    """Compact human-readable summary for the coach prompt."""
    f = extract(board)
    lines = [f"Phase: {f['phase']}. Files open: {', '.join(f['files']['open']) or 'none'}."]
    for name in ("white", "black"):
        s = f["sides"][name]
        bits = [f"material {s['material']}"]
        if s["isolated_pawns"]:
            bits.append(f"isolated pawns: {', '.join(s['isolated_pawns'])}")
        if s["doubled_pawn_files"]:
            bits.append(f"doubled pawns on: {', '.join(s['doubled_pawn_files'])}")
        if s["backward_pawns"]:
            bits.append(f"backward pawns: {', '.join(s['backward_pawns'])}")
        if s["passed_pawns"]:
            bits.append(f"passed pawns: {', '.join(s['passed_pawns'])}")
        bits.append(f"{s['pawn_islands']} pawn island(s)")
        for b in s["bishops"]["bishops"]:
            if b["bad"]:
                bits.append(f"bad {b['complex']}-squared bishop on {b['square']} "
                            f"({b['own_pawns_on_same_complex']} own pawns on its color)")
        if s["bishops"]["bishop_pair"]:
            bits.append("bishop pair")
        if s["knight_outposts"]:
            bits.append(f"knight outpost(s): {', '.join(s['knight_outposts'])}")
        k = s["king"]
        if k:
            kbits = f"king {k['square']}, shield {k['pawn_shield']}/3"
            if k["open_files_near_king"]:
                kbits += f", OPEN file(s) near king: {', '.join(k['open_files_near_king'])}"
            bits.append(kbits)
        bits.append(f"space {s['space']}")
        lines.append(f"{name.capitalize()}: " + "; ".join(bits) + ".")
    return "\n".join(lines)
