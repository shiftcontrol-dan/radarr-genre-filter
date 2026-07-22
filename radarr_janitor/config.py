from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency). Existing env vars win."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


@dataclass
class Config:
    radarr_url: str
    radarr_api_key: str
    omdb_api_key: str
    tmdb_api_key: str
    db_path: Path
    verify_ssl: bool
    cache_ttl_days: int
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    log_level: str

    @classmethod
    def load(cls, dotenv: str | os.PathLike | None = None) -> "Config":
        base = Path(__file__).resolve().parent.parent
        _load_dotenv(Path(dotenv) if dotenv else base / ".env")
        db_path = Path(os.environ.get("JANITOR_DB", str(base / "janitor.db")))
        if not db_path.is_absolute():
            db_path = base / db_path
        return cls(
            radarr_url=os.environ.get("RADARR_URL", "http://localhost:7878").rstrip("/"),
            radarr_api_key=os.environ.get("RADARR_API_KEY", ""),
            omdb_api_key=os.environ.get("OMDB_API_KEY", ""),
            tmdb_api_key=os.environ.get("TMDB_API_KEY", "1a7373301961d03f97f853a876dd1212"),
            db_path=db_path,
            verify_ssl=os.environ.get("VERIFY_SSL", "true").lower() != "false",
            cache_ttl_days=int(os.environ.get("CACHE_TTL_DAYS", "90")),
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID") or None,
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )
