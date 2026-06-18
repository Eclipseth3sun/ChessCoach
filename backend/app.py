"""FastAPI app: API routes + static frontend."""
import threading
from pathlib import Path

import chess
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import chesscom, coach, db, engine, settings

app = FastAPI(title="ChessCoach")
db.init_db()

# in-process engine job tracking: game_id -> {"done": n, "total": n, "error": str|None}
_jobs: dict[int, dict] = {}
# in-process coaching job tracking: game_id -> {"done", "total", "label", "error"}
_coach_jobs: dict[int, dict] = {}


class ImportRequest(BaseModel):
    username: str | None = None
    months: int = 3


class SettingsUpdate(BaseModel):
    anthropic_api_key: str | None = None
    chesscom_username: str | None = None
    claude_model: str | None = None
    engine_movetime_ms: int | None = None
    engine_multipv: int | None = None
    engine_threads: int | None = None
    # Coach provider settings — without these declared, Pydantic silently drops
    # them from the request and the Ollama model selection never reaches save().
    coach_provider: str | None = None
    ollama_url: str | None = None
    ollama_model: str | None = None


@app.get("/api/settings")
def get_settings():
    cfg = settings.load()
    # don't ship the raw key back to the UI; just whether it's set
    cfg["anthropic_api_key"] = bool(cfg["anthropic_api_key"])
    return cfg


@app.put("/api/settings")
def put_settings(update: SettingsUpdate):
    cfg = settings.save(update.model_dump(exclude_none=True))
    cfg["anthropic_api_key"] = bool(cfg["anthropic_api_key"])
    return cfg


@app.post("/api/import")
def import_games(req: ImportRequest):
    username = req.username or settings.load()["chesscom_username"]
    if not username:
        raise HTTPException(400, "No chess.com username configured")
    try:
        return chesscom.import_games(username, months=req.months)
    except Exception as e:  # surface chess.com errors readably
        raise HTTPException(502, f"chess.com import failed: {e}")


@app.get("/api/onboarding")
def onboarding():
    """Live setup state for the first-run checklist: prerequisites + data milestones."""
    cfg = settings.load()
    provider = cfg.get("coach_provider", "ollama")
    with db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM games").fetchone()["c"]
        analyzed = conn.execute(
            "SELECT COUNT(*) AS c FROM games WHERE engine_analyzed = 1").fetchone()["c"]
        coached = conn.execute(
            "SELECT COUNT(DISTINCT game_id) AS c FROM analyses").fetchone()["c"]

    out = {
        "coach_provider": provider,
        "chesscom_username": cfg.get("chesscom_username") or "",
        "games": total,
        "engine_analyzed": analyzed,
        "coached": coached,
        "ollama_model": cfg.get("ollama_model"),
        "ollama_reachable": False,
        "ollama_model_present": False,
        "claude_key_set": bool(cfg.get("anthropic_api_key")),
    }
    if provider == "ollama":
        try:
            base = cfg["ollama_url"].rstrip("/")
            r = httpx.get(f"{base}/api/tags", timeout=2.5)
            r.raise_for_status()
            out["ollama_reachable"] = True
            names = [m.get("name", "") for m in r.json().get("models", [])]
            want = (cfg.get("ollama_model") or "")
            out["ollama_model_present"] = any(
                n == want or n.split(":")[0] == want.split(":")[0] for n in names)
        except Exception:
            pass  # unreachable -> stays False, the checklist surfaces the fix
    return out


@app.get("/api/games")
def games(limit: int = 200):
    with db.connect() as conn:
        return db.list_games(conn, limit)


@app.get("/api/games/{game_id}")
def game(game_id: int):
    with db.connect() as conn:
        g = db.get_game(conn, game_id)
    if g is None:
        raise HTTPException(404, "game not found")
    g["time_report"] = engine.time_report(g.get("moves") or [], g.get("user_color"))
    return g


@app.post("/api/games/{game_id}/analyze")
def analyze(game_id: int):
    if game_id in _jobs and _jobs[game_id].get("error") is None \
            and _jobs[game_id]["done"] < _jobs[game_id]["total"]:
        return {"status": "already_running"}
    progress = {"done": 0, "total": 1, "error": None}
    _jobs[game_id] = progress

    def run():
        try:
            engine.analyze_game(game_id, progress)
        except Exception as e:
            progress["error"] = str(e)

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started"}


@app.get("/api/games/{game_id}/analyze/status")
def analyze_status(game_id: int):
    job = _jobs.get(game_id)
    if job is None:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT engine_analyzed FROM games WHERE id = ?", (game_id,)
            ).fetchone()
        done = bool(row and row["engine_analyzed"])
        return {"status": "done" if done else "not_started"}
    if job["error"]:
        return {"status": "error", "error": job["error"]}
    if job["done"] >= job["total"]:
        return {"status": "done"}
    return {"status": "running", "done": job["done"], "total": job["total"]}


@app.post("/api/games/{game_id}/coach")
def coach_game(game_id: int):
    job = _coach_jobs.get(game_id)
    if job and job.get("error") is None and job["done"] < job["total"]:
        return {"status": "already_running"}
    progress = {"done": 0, "total": 1, "label": "Starting…", "error": None}
    _coach_jobs[game_id] = progress

    def run():
        try:
            coach.coach_game(game_id, progress)
        except Exception as e:
            progress["error"] = str(e)

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started"}


@app.get("/api/games/{game_id}/coach/status")
def coach_status(game_id: int):
    job = _coach_jobs.get(game_id)
    if job is None:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT EXISTS(SELECT 1 FROM analyses WHERE game_id = ?) AS c", (game_id,)
            ).fetchone()
        return {"status": "done" if row and row["c"] else "not_started"}
    if job["error"]:
        return {"status": "error", "error": job["error"]}
    if job["done"] >= job["total"]:
        return {"status": "done"}
    return {"status": "running", "done": job["done"], "total": job["total"],
            "label": job.get("label", "")}


@app.get("/api/games/{game_id}/bestline/{ply}")
def get_deep_bestline(game_id: int, ply: int):
    """Return Stockfish's full PV from the position just before `ply` was played."""
    with db.connect() as conn:
        if ply <= 1:
            fen = chess.STARTING_FEN
        else:
            row = conn.execute(
                "SELECT fen_after FROM moves WHERE game_id = ? AND ply = ?",
                (game_id, ply - 1)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "position not found — run engine analysis first")
            fen = row["fen_after"]

    try:
        sans = engine.get_bestline(fen)
    except Exception as e:
        raise HTTPException(500, f"engine error: {e}")

    return {"fen": fen, "sans": sans}


# Serve the built frontend (must be mounted last so /api wins)
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
