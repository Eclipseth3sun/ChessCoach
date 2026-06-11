"""Import games from the chess.com public API (free, no auth required)."""
import io

import chess.pgn
import httpx

from . import db

API = "https://api.chess.com/pub"
# chess.com requires a descriptive User-Agent or it 403s
HEADERS = {"User-Agent": "ChessCoach personal analysis app (contact: levi.allen251@gmail.com)"}


def fetch_archives(username: str) -> list[str]:
    """Return the list of monthly archive URLs, oldest first."""
    r = httpx.get(f"{API}/player/{username}/games/archives", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()["archives"]


def import_games(username: str, months: int = 3) -> dict:
    """Import the most recent `months` archives. Returns counts."""
    username = username.strip().lower()
    archives = fetch_archives(username)[-months:]
    imported = skipped = 0
    with db.connect() as conn:
        for url in archives:
            r = httpx.get(url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            for g in r.json().get("games", []):
                pgn_text = g.get("pgn")
                if not pgn_text or g.get("rules") != "chess":  # skip variants
                    continue
                record = _parse_game(pgn_text, g, username)
                if record and db.insert_game(conn, record):
                    imported += 1
                else:
                    skipped += 1
        conn.commit()
    return {"imported": imported, "skipped": skipped, "archives": len(archives)}


def _parse_game(pgn_text: str, raw: dict, username: str) -> dict | None:
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return None
    h = game.headers
    white = h.get("White", "")
    black = h.get("Black", "")
    if username == white.lower():
        user_color = "white"
    elif username == black.lower():
        user_color = "black"
    else:
        user_color = None

    def _elo(tag):
        try:
            return int(h.get(tag, ""))
        except ValueError:
            return None

    return {
        "source": "chess.com",
        "source_url": raw.get("url"),
        "pgn": pgn_text,
        "white": white,
        "black": black,
        "white_elo": _elo("WhiteElo"),
        "black_elo": _elo("BlackElo"),
        "result": h.get("Result"),
        "eco": h.get("ECO"),
        "opening": h.get("ECOUrl", "").rsplit("/", 1)[-1].replace("-", " ") or None,
        "time_control": h.get("TimeControl"),
        "played_at": f"{h.get('UTCDate', '').replace('.', '-')} {h.get('UTCTime', '')}".strip(),
        "user_color": user_color,
    }
