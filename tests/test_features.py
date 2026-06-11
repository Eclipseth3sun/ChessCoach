import chess
import pytest

from backend import features
from backend.engine import classify, win_pct


def test_isolated_queen_pawn():
    # Classic IQP: white pawn d4, no c- or e-pawns
    board = chess.Board("rnbqkbnr/pp3ppp/4p3/8/3P4/8/PP3PPP/RNBQKBNR w KQkq - 0 1")
    assert features.isolated_pawns(board, chess.WHITE) == ["d4"]
    assert features.isolated_pawns(board, chess.BLACK) == []


def test_doubled_and_islands():
    # White: doubled c-pawns (c2, c3) + h2 -> 2 islands
    board = chess.Board("4k3/8/8/8/8/2P5/2P4P/4K3 w - - 0 1")
    assert features.doubled_files(board, chess.WHITE) == ["c"]
    assert features.pawn_islands(board, chess.WHITE) == 2


def test_passed_pawn():
    # White a5 pawn passed (black has only h-pawn)
    board = chess.Board("4k3/7p/8/P7/8/8/8/4K3 w - - 0 1")
    assert features.passed_pawns(board, chess.WHITE) == ["a5"]
    assert features.passed_pawns(board, chess.BLACK) == ["h7"]


def test_not_passed_when_blocked_by_adjacent_file():
    # White d4 vs black e5: e5 controls/blocks promotion path
    board = chess.Board("4k3/8/8/4p3/3P4/8/8/4K3 w - - 0 1")
    assert features.passed_pawns(board, chess.WHITE) == []


def test_open_and_semi_open_files():
    # White pawns: d4, e2 ; Black pawns: d5, h7
    board = chess.Board("4k3/7p/8/3p4/3P4/8/4P3/4K3 w - - 0 1")
    f = features.open_files(board)
    assert "a" in f["open"] and "d" not in f["open"] and "e" not in f["open"]
    assert f["semi_open_white"] == ["h"]   # white has no h-pawn, black does
    assert f["semi_open_black"] == ["e"]   # black has no e-pawn, white does


def test_bad_bishop():
    # White light-squared bishop on d3 behind pawns fixed on light squares
    board = chess.Board("4k3/8/8/8/2PP4/3BP3/1P6/4K3 w - - 0 1")
    info = features.bishop_situation(board, chess.WHITE)
    (bishop,) = info["bishops"]
    assert bishop["complex"] == "light"
    # c4, e3? c4: file 2 rank 3 -> 2+3=5 odd -> light. d4: 3+3=6 even -> dark.
    # e3: 4+2=6 even -> dark. b2: 1+1=2 even -> dark. So 1 light pawn -> not bad.
    assert bishop["own_pawns_on_same_complex"] == 1
    assert not bishop["bad"]


def test_knight_outpost():
    # White knight d5 defended by e4 pawn; black has no c- or e-pawns to evict it
    board = chess.Board("4k3/5p2/8/3N4/4P3/8/8/4K3 w - - 0 1")
    assert features.knight_outposts(board, chess.WHITE) == ["d5"]


def test_no_outpost_when_evictable():
    # Same but black has c7 pawn that can come to c6
    board = chess.Board("4k3/2p2p2/8/3N4/4P3/8/8/4K3 w - - 0 1")
    assert features.knight_outposts(board, chess.WHITE) == []


def test_king_safety_castled_with_shield():
    board = chess.Board("rnbq1rk1/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1 w - - 0 1")
    k = features.king_safety(board, chess.WHITE)
    assert k["square"] == "g1"
    assert k["pawn_shield"] == 3
    assert k["castled"]
    assert k["open_files_near_king"] == []


def test_game_phase():
    assert features.game_phase(chess.Board()) == "opening"
    endgame = chess.Board("4k3/4p3/8/8/8/8/4P3/4K1N1 w - - 40 41")
    assert features.game_phase(endgame) == "endgame"


def test_win_pct_symmetry():
    assert win_pct(0) == pytest.approx(50)
    assert win_pct(300) + win_pct(-300) == pytest.approx(100)
    assert win_pct(300) > 70


def test_classify_thresholds():
    assert classify(0.0, played_best=True) == "best"
    assert classify(5, False) == "good"
    assert classify(12, False) == "inaccuracy"
    assert classify(25, False) == "mistake"
    assert classify(35, False) == "blunder"
