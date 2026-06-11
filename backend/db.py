"""SQLite schema and access helpers.

Schema is designed so cross-game profiling (phase 3) is a GROUP BY over
`themes` and `moves.classification`, not a migration.
"""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "chesscoach.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'chess.com',
    source_url TEXT UNIQUE,
    pgn TEXT NOT NULL,
    white TEXT, black TEXT,
    white_elo INTEGER, black_elo INTEGER,
    result TEXT, eco TEXT, opening TEXT,
    time_control TEXT, played_at TEXT,
    user_color TEXT,                -- 'white' | 'black' (relative to configured user)
    engine_analyzed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS moves (
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    ply INTEGER NOT NULL,           -- 1-based half-move number
    san TEXT NOT NULL,
    uci TEXT NOT NULL,
    fen_after TEXT NOT NULL,
    eval_cp INTEGER,                -- white-POV centipawns after the move
    eval_mate INTEGER,              -- white-POV mate distance after the move (overrides eval_cp)
    best_uci TEXT,                  -- engine best move in the position before this move
    best_san TEXT,
    best_line TEXT,                 -- SAN pv of the best line, space separated
    classification TEXT,            -- best/good/inaccuracy/mistake/blunder
    win_pct_loss REAL,              -- mover's win% lost by this move vs engine best
    PRIMARY KEY (game_id, ply)
);

CREATE TABLE IF NOT EXISTS analyses (
    game_id INTEGER PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
    commentary TEXT NOT NULL,       -- JSON blob from the coach
    model TEXT,
    input_tokens INTEGER, output_tokens INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS themes (
    id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,             -- controlled vocabulary, e.g. 'isolated-queen-pawn'
    side TEXT,                      -- 'user' | 'opponent' | 'both'
    severity TEXT,                  -- 'minor' | 'significant' | 'decisive'
    ply_start INTEGER, ply_end INTEGER,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_themes_slug ON themes(slug);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def insert_game(conn: sqlite3.Connection, g: dict) -> int | None:
    """Insert a game; returns new id, or None if the source_url already exists."""
    try:
        cur = conn.execute(
            """INSERT INTO games (source, source_url, pgn, white, black, white_elo,
                   black_elo, result, eco, opening, time_control, played_at, user_color)
               VALUES (:source, :source_url, :pgn, :white, :black, :white_elo,
                   :black_elo, :result, :eco, :opening, :time_control, :played_at, :user_color)""",
            g,
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def list_games(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        """SELECT g.id, g.white, g.black, g.white_elo, g.black_elo, g.result, g.eco,
                  g.opening, g.time_control, g.played_at, g.user_color, g.engine_analyzed,
                  g.source_url,
                  EXISTS(SELECT 1 FROM analyses a WHERE a.game_id = g.id) AS coached
           FROM games g ORDER BY g.played_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_game(conn: sqlite3.Connection, game_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if row is None:
        return None
    game = dict(row)
    game["moves"] = [
        dict(r) for r in conn.execute(
            "SELECT * FROM moves WHERE game_id = ? ORDER BY ply", (game_id,)
        )
    ]
    analysis = conn.execute(
        "SELECT * FROM analyses WHERE game_id = ?", (game_id,)
    ).fetchone()
    game["coach"] = json.loads(analysis["commentary"]) if analysis else None
    game["themes"] = [
        dict(r) for r in conn.execute(
            "SELECT * FROM themes WHERE game_id = ? ORDER BY ply_start", (game_id,)
        )
    ]
    return game


def save_engine_pass(conn: sqlite3.Connection, game_id: int, moves: list[dict]) -> None:
    conn.execute("DELETE FROM moves WHERE game_id = ?", (game_id,))
    conn.executemany(
        """INSERT INTO moves (game_id, ply, san, uci, fen_after, eval_cp, eval_mate,
               best_uci, best_san, best_line, classification, win_pct_loss)
           VALUES (:game_id, :ply, :san, :uci, :fen_after, :eval_cp, :eval_mate,
               :best_uci, :best_san, :best_line, :classification, :win_pct_loss)""",
        moves,
    )
    conn.execute("UPDATE games SET engine_analyzed = 1 WHERE id = ?", (game_id,))


def save_coach(conn: sqlite3.Connection, game_id: int, commentary: dict,
               model: str, input_tokens: int, output_tokens: int) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO analyses (game_id, commentary, model, input_tokens, output_tokens)
           VALUES (?, ?, ?, ?, ?)""",
        (game_id, json.dumps(commentary), model, input_tokens, output_tokens),
    )
    conn.execute("DELETE FROM themes WHERE game_id = ?", (game_id,))
    for t in commentary.get("themes", []):
        conn.execute(
            """INSERT INTO themes (game_id, slug, side, severity, ply_start, ply_end, note)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (game_id, t.get("slug"), t.get("side"), t.get("severity"),
             t.get("ply_start"), t.get("ply_end"), t.get("note")),
        )
