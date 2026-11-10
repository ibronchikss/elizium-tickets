from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any, Optional

import discord

PRIORITY_NAMES = {0: "low", 1: "normal", 2: "high", 3: "urgent"}
PRIORITY_EMOJI = {0: "🟢", 1: "🔵", 2: "🟠", 3: "🔴"}
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def now() -> int:
    return int(time.time())


def ts(value: Optional[int], style: str = "R") -> str:
    if not value:
        return "—"
    return f"<t:{int(value)}:{style}>"


def trunc(text: Optional[str], n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------- длительности ----------
_DUR = re.compile(r"(\d+)\s*([smhdwсмчдн])", re.I)
_MULT = {"s": 1, "с": 1, "m": 60, "м": 60, "h": 3600, "ч": 3600, "d": 86400, "д": 86400, "w": 604800, "н": 604800}


def parse_duration(text: str) -> Optional[int]:
    """'30m', '2h', '1d12h', '2ч', '5' (= 5 часов) -> секунды. None если не распознано."""
    text = (text or "").strip().lower()
    if not text:
        return None
    if text.isdigit():
        return int(text) * 3600
    parts = _DUR.findall(text)
    if not parts or _DUR.sub("", text).strip():
        return None
    return sum(int(n) * _MULT[u] for n, u in parts)


def fmt_duration(seconds: Optional[float], lang: str = "ru") -> str:
    if seconds is None:
        return "—"
    seconds = int(max(0, seconds))
    units = (("д", "d", 86400), ("ч", "h", 3600), ("м", "m", 60), ("с", "s", 1))
    out = []
    for ru, en, size in units:
        if seconds >= size:
            q, seconds = divmod(seconds, size)
            out.append(f"{q}{ru if lang == 'ru' else en}")
        if len(out) == 2:
            break
    return " ".join(out) if out else ("0с" if lang == "ru" else "0s")


# ---------- прочее ----------
def parse_color(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    text = text.strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return int(text, 16)
    return None


_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def fill(text: str, **ctx: Any) -> str:
    """Подставляет {key} только для известных ключей, остальное не трогает."""
    return _PLACEHOLDER.sub(lambda m: str(ctx[m.group(1)]) if m.group(1) in ctx else m.group(0), text)


def slug(text: str, maxlen: int = 90) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^\w\-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    return text[:maxlen] or "ticket"


def jl(value: Any) -> list:
    """JSON-список из колонки БД."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        data = json.loads(value)
        return data if isinstance(data, list) else []
    except (TypeError, ValueError):
        return []


def chunks(seq: list, n: int) -> list[list]:
    return [seq[i : i + n] for i in range(0, len(seq), n)]


def valid_emoji(text: Optional[str]) -> bool:
    if not text:
        return False
    try:
        pe = discord.PartialEmoji.from_str(text.strip())
    except Exception:
        return False
    return bool(pe.name)


def parse_time_of_day(text: str) -> Optional[int]:
    """'09:30' -> минуты от полуночи."""
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", text or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 24 or mi > 59 or (h == 24 and mi != 0):
        return None
    return h * 60 + mi


def parse_days(text: str) -> Optional[list[int]]:
    """'mon-fri', 'пн-пт', 'mon,wed,sat', 'daily' -> [0..6]."""
    aliases = {
        "mon": 0, "пн": 0, "tue": 1, "вт": 1, "wed": 2, "ср": 2, "thu": 3, "чт": 3,
        "fri": 4, "пт": 4, "sat": 5, "сб": 5, "sun": 6, "вс": 6,
    }
    text = (text or "").strip().lower().replace(" ", "")
    if text in ("daily", "all", "every", "ежедневно", "*"):
        return list(range(7))
    out: set[int] = set()
    for part in text.split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            if a not in aliases or b not in aliases:
                return None
            i, j = aliases[a], aliases[b]
            rng = range(i, j + 1) if i <= j else list(range(i, 7)) + list(range(0, j + 1))
            out.update(rng)
        elif part in aliases:
            out.add(aliases[part])
        else:
            return None
    return sorted(out) or None


def hours_match(windows: list[dict], moment: datetime) -> bool:
    """Попадает ли локальное время в одно из окон поддержки. Нет окон — всегда True."""
    if not windows:
        return True
    minutes = moment.hour * 60 + moment.minute
    for w in windows:
        days = [int(x) for x in w["days"].split(",") if x != ""]
        if moment.weekday() in days and w["start_min"] <= minutes < w["end_min"]:
            return True
    return False


def score_article(query: str, article: dict) -> int:
    """Простейший поиск по базе знаний: совпадения слов в заголовке/ключах/тексте."""
    words = {w for w in re.findall(r"\w{3,}", (query or "").lower())}
    if not words:
        return 0
    title = article["title"].lower()
    keys = {k.strip().lower() for k in (article.get("keywords") or "").split(",") if k.strip()}
    body = article["content"].lower()
    score = 0
    for w in words:
        if w in keys:
            score += 5
        elif any(w in k for k in keys):
            score += 3
        if w in title:
            score += 3
        if w in body:
            score += 1
    return score


async def reply(interaction: discord.Interaction, content: Optional[str] = None, *, embed: Optional[discord.Embed] = None,
                view: Optional[discord.ui.View] = None, file: Optional[discord.File] = None, ephemeral: bool = True) -> None:
    """Ответить на interaction независимо от того, был ли уже первый ответ."""
    kwargs: dict[str, Any] = {"ephemeral": ephemeral}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if view is not None:
        kwargs["view"] = view
    if file is not None:
        kwargs["file"] = file
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)
