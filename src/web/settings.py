"""Web-app settings: .env loading, state paths, auth token."""

import os
import secrets
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WEB_STATE_DIR = PROJECT_ROOT / ".webapp"
LOGS_DIR = WEB_STATE_DIR / "logs"
JOBS_FILE = WEB_STATE_DIR / "jobs.json"
TOKEN_FILE = WEB_STATE_DIR / "token"


def load_env_file() -> None:
    """Load ``PROJECT_ROOT/.env`` into ``os.environ`` without overriding.

    Minimal parser (no external dependency): skips blanks/comments, strips
    optional quotes. Values already present in the environment win.
    """
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def get_web_token() -> str:
    """Auth token: ``WEB_TOKEN`` env var wins; else persist a generated one.

    The generated token lives in ``.webapp/token`` so it survives restarts.
    """
    tok = os.environ.get("WEB_TOKEN", "").strip()
    if tok:
        return tok
    WEB_STATE_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    tok = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(tok + "\n", encoding="utf-8")
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass
    return tok


def ensure_state_dirs() -> None:
    WEB_STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
