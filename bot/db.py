from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS guild_config(
    guild_id INTEGER NOT NULL,
    key      TEXT    NOT NULL,
    value    TEXT    NOT NULL,
    PRIMARY KEY(guild_id, key)
);

CREATE TABLE IF NOT EXISTS counters(
    guild_id INTEGER PRIMARY KEY,
    n        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS staff(
    guild_id  INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    is_role   INTEGER NOT NULL,
    level     TEXT    NOT NULL,
    PRIMARY KEY(guild_id, target_id, level)
);

CREATE TABLE IF NOT EXISTS blacklist(
    guild_id  INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    is_role   INTEGER NOT NULL,
    PRIMARY KEY(guild_id, target_id)
);

CREATE TABLE IF NOT EXISTS oncall(
    guild_id INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    PRIMARY KEY(guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS hours(
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id  INTEGER NOT NULL,
    days      TEXT    NOT NULL,
    start_min INTEGER NOT NULL,
    end_min   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS forms(
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    name     TEXT    NOT NULL,
    UNIQUE(guild_id, name)
);

CREATE TABLE IF NOT EXISTS form_questions(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    form_id     INTEGER NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    label       TEXT    NOT NULL,
    style       TEXT    NOT NULL DEFAULT 'short',
    placeholder TEXT,
    required    INTEGER NOT NULL DEFAULT 1,
    min_length  INTEGER,
    max_length  INTEGER
);

CREATE TABLE IF NOT EXISTS panels(
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id        INTEGER NOT NULL,
    name            TEXT    NOT NULL,
    title           TEXT,
    description     TEXT,
    color           INTEGER,
    button_label    TEXT,
    button_emoji    TEXT,
    button_style    TEXT    NOT NULL DEFAULT 'blurple',
    image_url       TEXT,
    thumbnail_url   TEXT,
    channel_id      INTEGER,
    message_id      INTEGER,
    category_id     INTEGER,
    form_id         INTEGER REFERENCES forms(id) ON DELETE SET NULL,
    support_roles   TEXT    NOT NULL DEFAULT '[]',
    ping_roles      TEXT    NOT NULL DEFAULT '[]',
    welcome_message TEXT,
    naming          TEXT,
    required_role_id INTEGER,
    ticket_limit    INTEGER,
    use_threads     INTEGER,
    enforce_hours   INTEGER NOT NULL DEFAULT 0,
    role_on_open    INTEGER,
    role_on_close   INTEGER,
    default_priority INTEGER NOT NULL DEFAULT 1,
    enabled         INTEGER NOT NULL DEFAULT 1,
    UNIQUE(guild_id, name)
);

CREATE TABLE IF NOT EXISTS multipanels(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    title       TEXT,
    description TEXT,
    color       INTEGER,
    style       TEXT    NOT NULL DEFAULT 'buttons',
    placeholder TEXT,
    channel_id  INTEGER,
    message_id  INTEGER,
    panel_ids   TEXT    NOT NULL DEFAULT '[]',
    UNIQUE(guild_id, name)
);

CREATE TABLE IF NOT EXISTS tickets(
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id             INTEGER NOT NULL,
    number               INTEGER NOT NULL,
    channel_id           INTEGER NOT NULL UNIQUE,
    is_thread            INTEGER NOT NULL DEFAULT 0,
    panel_id             INTEGER,
    opener_id            INTEGER NOT NULL,
    claimed_by           INTEGER,
    status               TEXT    NOT NULL DEFAULT 'open',
    priority             INTEGER NOT NULL DEFAULT 1,
    subject              TEXT,
    created_at           INTEGER NOT NULL,
    closed_at            INTEGER,
    closed_by            INTEGER,
    close_reason         TEXT,
    first_response_at    INTEGER,
    last_activity_at     INTEGER NOT NULL,
    close_at             INTEGER,
    close_request_by     INTEGER,
    close_request_reason TEXT,
    warned               INTEGER NOT NULL DEFAULT 0,
    sla_alerted          INTEGER NOT NULL DEFAULT 0,
    rating               INTEGER,
    rating_comment       TEXT
);
CREATE INDEX IF NOT EXISTS idx_tickets_guild_status ON tickets(guild_id, status);
CREATE INDEX IF NOT EXISTS idx_tickets_opener ON tickets(guild_id, opener_id, status);

CREATE TABLE IF NOT EXISTS ticket_users(
    ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    user_id   INTEGER NOT NULL,
    PRIMARY KEY(ticket_id, user_id)
);

CREATE TABLE IF NOT EXISTS ticket_msgs(
    ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    user_id   INTEGER NOT NULL,
    count     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(ticket_id, user_id)
);

CREATE TABLE IF NOT EXISTS transcripts(
    ticket_id  INTEGER PRIMARY KEY REFERENCES tickets(id) ON DELETE CASCADE,
    guild_id   INTEGER NOT NULL,
    html       BLOB    NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tags(
    guild_id INTEGER NOT NULL,
    name     TEXT    NOT NULL,
    content  TEXT    NOT NULL,
    PRIMARY KEY(guild_id, name)
);

CREATE TABLE IF NOT EXISTS kb(
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    title    TEXT    NOT NULL,
    content  TEXT    NOT NULL,
    keywords TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_kb_guild ON kb(guild_id);

CREATE TABLE IF NOT EXISTS premium_keys(
    key        TEXT PRIMARY KEY,
    days       INTEGER NOT NULL,
    created_by INTEGER,
    created_at INTEGER NOT NULL,
    used_guild INTEGER,
    used_at    INTEGER
);
"""


class Database:
    """Асинхронная обёртка над sqlite3 (stdlib): один коннект + lock + to_thread."""

    def __init__(self, path: str):
        self.path = path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        await self._run(lambda c: c.executescript(SCHEMA))

    async def close(self) -> None:
        if self._conn is not None:
            conn, self._conn = self._conn, None
            await asyncio.to_thread(conn.close)

    async def _run(self, fn):
        if self._conn is None:
            raise RuntimeError("База данных не подключена")
        async with self._lock:
            return await asyncio.to_thread(fn, self._conn)

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Выполнить запрос, вернуть lastrowid."""
        return await self._run(lambda c: c.execute(sql, tuple(params)).lastrowid)

    async def update(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Выполнить запрос, вернуть число затронутых строк."""
        return await self._run(lambda c: c.execute(sql, tuple(params)).rowcount)

    async def one(self, sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
        def fn(c):
            row = c.execute(sql, tuple(params)).fetchone()
            return dict(row) if row is not None else None

        return await self._run(fn)

    async def all(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        return await self._run(lambda c: [dict(r) for r in c.execute(sql, tuple(params)).fetchall()])

    async def val(self, sql: str, params: Iterable[Any] = (), default: Any = None) -> Any:
        def fn(c):
            row = c.execute(sql, tuple(params)).fetchone()
            return row[0] if row is not None and row[0] is not None else default

        return await self._run(fn)

    async def many(self, sql: str, seq: Iterable[Iterable[Any]]) -> None:
        rows = [tuple(x) for x in seq]
        await self._run(lambda c: c.executemany(sql, rows))

    async def next_ticket_number(self, guild_id: int) -> int:
        return await self.val(
            "INSERT INTO counters(guild_id, n) VALUES(?, 1) "
            "ON CONFLICT(guild_id) DO UPDATE SET n = n + 1 RETURNING n",
            (guild_id,),
        )
