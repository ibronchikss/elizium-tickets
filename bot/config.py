from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Минимальный загрузчик .env (без зависимостей)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "y", "да")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _ids(name: str) -> frozenset[int]:
    out = set()
    for part in os.environ.get(name, "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return frozenset(out)


@dataclass(frozen=True)
class Config:
    token: str
    owner_ids: frozenset
    db_path: str
    default_language: str
    premium_for_all: bool
    free_panel_limit: int
    free_kb_limit: int
    free_form_questions: int
    free_transcript_days: int
    status_text: str
    brand_footer: str
    default_color: int
    vote_url: str
    support_url: str
    dev_guild_id: int | None
    sync_commands: bool

    @classmethod
    def load(cls) -> "Config":
        load_dotenv(ROOT / ".env")
        color_raw = os.environ.get("EMBED_COLOR", "5865F2").strip().lstrip("#")
        try:
            color = int(color_raw, 16)
        except ValueError:
            color = 0x5865F2
        db_path = os.environ.get("DB_PATH", "data/tickets.db")
        if not os.path.isabs(db_path):
            db_path = str(ROOT / db_path)
        lang = os.environ.get("DEFAULT_LANGUAGE", "ru").strip().lower()
        return cls(
            token=os.environ.get("DISCORD_TOKEN", "").strip(),
            owner_ids=_ids("OWNER_IDS"),
            db_path=db_path,
            default_language=lang if lang in ("ru", "en") else "ru",
            premium_for_all=_bool("PREMIUM_FOR_ALL", True),
            free_panel_limit=_int("FREE_PANEL_LIMIT", 3),
            free_kb_limit=_int("FREE_KB_LIMIT", 5),
            free_form_questions=_int("FREE_FORM_QUESTIONS", 5),
            free_transcript_days=_int("FREE_TRANSCRIPT_DAYS", 30),
            status_text=os.environ.get("STATUS_TEXT", "/help | Tickets"),
            brand_footer=os.environ.get("BRAND_FOOTER", ""),
            default_color=color,
            vote_url=os.environ.get("VOTE_URL", "").strip(),
            support_url=os.environ.get("SUPPORT_URL", "").strip(),
            dev_guild_id=_int("DEV_GUILD_ID", 0) or None,
            sync_commands=_bool("SYNC_COMMANDS", True),
        )
