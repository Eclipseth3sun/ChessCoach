"""App settings persisted to a JSON file next to the project root."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "settings.json"

DEFAULTS = {
    "anthropic_api_key": "",
    "chesscom_username": "",
    "claude_model": "claude-sonnet-4-6",
    "engine_movetime_ms": 150,   # per-position think time for the analysis pass
    "engine_multipv": 3,
    "engine_threads": 4,
    # Coach provider: "claude" or "ollama"
    "coach_provider": "ollama",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5:14b",
}


def load() -> dict:
    if SETTINGS_PATH.exists():
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return {**DEFAULTS, **data}
    return dict(DEFAULTS)


def save(updates: dict) -> dict:
    current = load()
    all_keys = set(DEFAULTS) | {"coach_provider", "ollama_url", "ollama_model"}
    for key in all_keys:
        if key in updates and updates[key] is not None:
            current[key] = updates[key]
    SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current
