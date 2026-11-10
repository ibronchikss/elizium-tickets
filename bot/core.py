from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from . import utils
from .config import Config
from .db import Database
from .i18n import tr

log = logging.getLogger("ticketbot")
_MISSING = object()

EXTENSIONS = (
    "bot.cogs.general",
    "bot.cogs.tickets",
    "bot.cogs.panels",
    "bot.cogs.settings",
    "bot.cogs.tags",
    "bot.cogs.stats",
    "bot.cogs.premium",
    "bot.cogs.tasks",
)

# Значения настроек сервера по умолчанию
DEFAULTS: dict[str, Any] = {
    "use_threads": False,        # тикеты в приватных тредах вместо каналов
    "ticket_limit": 1,           # сколько открытых тикетов на пользователя
    "category_id": None,         # категория для тикетов-каналов
    "thread_parent_id": None,    # канал-родитель для тредов (если не задан у панели)
    "log_channel_id": None,
    "transcript_channel_id": None,
    "naming": "ticket-{number}",
    "welcome": None,
    "close_confirm": True,
    "delete_on_close": True,
    "dm_transcript": True,
    "close_on_leave": True,
    "survey": False,             # premium: оценка после закрытия
    "keepalive": False,          # premium: не давать тредам автоархивироваться
    "autoclose_hours": 0,        # premium
    "autoclose_warn_hours": 0,   # premium
    "sla_minutes": 0,            # premium
    "sla_channel_id": None,
    "sla_role_id": None,
    "embed_color": None,         # premium
    "footer": None,              # premium
    "timezone": "UTC",
    "premium_until": 0,          # 0 — нет, -1 — навсегда, иначе unix-время окончания
}


class NotAdmin(app_commands.CheckFailure):
    pass


class NotSupport(app_commands.CheckFailure):
    pass


class PremiumRequired(app_commands.CheckFailure):
    pass


def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.NoPrivateMessage()
        if await interaction.client.is_admin(interaction.user):
            return True
        raise NotAdmin()

    return app_commands.check(predicate)


def support_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.NoPrivateMessage()
        if await interaction.client.is_support(interaction.user):
            return True
        raise NotSupport()

    return app_commands.check(predicate)


def premium_only(feature: str):
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is not None and interaction.client.is_premium(interaction.guild.id):
            return True
        raise PremiumRequired(feature)

    return app_commands.check(predicate)


class TicketBot(commands.Bot):
    def __init__(self, cfg: Config):
        intents = discord.Intents.default()
        intents.members = True          # привилегированный интент: Server Members
        intents.message_content = True  # привилегированный интент: Message Content (для транскриптов)
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=True, users=True, replied_user=False),
            activity=discord.Game(cfg.status_text) if cfg.status_text else None,
        )
        self.cfg = cfg
        self.db = Database(cfg.db_path)
        self.conf: dict[int, dict[str, Any]] = {}
        self.open_channels: dict[int, int] = {}   # channel_id -> ticket_id (только открытые)
        self.started_at = time.time()

        from .services import TicketService

        self.tickets = TicketService(self)
        self.tree.error(self.on_tree_error)

    # ------------------------------------------------------------------ запуск
    async def setup_hook(self) -> None:
        await self.db.connect()
        for row in await self.db.all("SELECT guild_id, key, value FROM guild_config"):
            try:
                self.conf.setdefault(row["guild_id"], {})[row["key"]] = json.loads(row["value"])
            except ValueError:
                continue
        for row in await self.db.all("SELECT id, channel_id FROM tickets WHERE status = 'open'"):
            self.open_channels[row["channel_id"]] = row["id"]

        from . import views

        views.register(self)
        for ext in EXTENSIONS:
            await self.load_extension(ext)

        if self.cfg.sync_commands:
            if self.cfg.dev_guild_id:
                guild = discord.Object(id=self.cfg.dev_guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            else:
                await self.tree.sync()
            log.info("Слеш-команды синхронизированы")

    async def close(self) -> None:
        await super().close()
        await self.db.close()

    async def on_ready(self) -> None:
        log.info("Вошёл как %s (%s), серверов: %d", self.user, getattr(self.user, "id", "?"), len(self.guilds))

    # ------------------------------------------------------------------ настройки
    def get(self, guild_id: Optional[int], key: str, default: Any = _MISSING) -> Any:
        data = self.conf.get(guild_id or 0)
        if data is not None and key in data:
            return data[key]
        return DEFAULTS.get(key) if default is _MISSING else default

    async def set(self, guild_id: int, key: str, value: Any) -> None:
        if value is None:
            await self.db.execute("DELETE FROM guild_config WHERE guild_id = ? AND key = ?", (guild_id, key))
            self.conf.get(guild_id, {}).pop(key, None)
            return
        await self.db.execute(
            "INSERT INTO guild_config(guild_id, key, value) VALUES(?, ?, ?) "
            "ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value",
            (guild_id, key, json.dumps(value)),
        )
        self.conf.setdefault(guild_id, {})[key] = value

    # ------------------------------------------------------------------ язык и премиум
    def lang(self, guild_id: Optional[int]) -> str:
        return self.get(guild_id, "language", self.cfg.default_language)

    def t(self, guild_id: Optional[int], key: str, **kw: Any) -> str:
        return tr(self.lang(guild_id), key, **kw)

    def is_premium(self, guild_id: Optional[int]) -> bool:
        if self.cfg.premium_for_all:
            return True
        until = self.get(guild_id, "premium_until", 0)
        return until == -1 or until > utils.now()

    def embed(self, guild_id: Optional[int], title: Optional[str] = None, description: Optional[str] = None, *,
              color: Optional[int] = None, footer: bool = True) -> discord.Embed:
        premium = self.is_premium(guild_id)
        if color is None and premium:
            color = self.get(guild_id, "embed_color")
        e = discord.Embed(title=title, description=description, color=color if color is not None else self.cfg.default_color)
        if footer:
            text = (self.get(guild_id, "footer") if premium else None) or self.cfg.brand_footer
            if text:
                e.set_footer(text=text)
        return e

    # ------------------------------------------------------------------ права
    async def _has_level(self, member: discord.Member, levels: tuple[str, ...]) -> bool:
        marks = ",".join("?" for _ in levels)
        rows = await self.db.all(
            f"SELECT target_id, is_role FROM staff WHERE guild_id = ? AND level IN ({marks})",
            (member.guild.id, *levels),
        )
        role_ids = {r.id for r in member.roles}
        for row in rows:
            if row["is_role"] and row["target_id"] in role_ids:
                return True
            if not row["is_role"] and row["target_id"] == member.id:
                return True
        return False

    async def is_admin(self, member: Any) -> bool:
        if member.id in self.cfg.owner_ids:
            return True
        if not isinstance(member, discord.Member):
            return False
        perms = member.guild_permissions
        if perms.administrator or perms.manage_guild:
            return True
        return await self._has_level(member, ("admin",))

    async def is_support(self, member: Any, extra_role_ids: Any = ()) -> bool:
        if await self.is_admin(member):
            return True
        if not isinstance(member, discord.Member):
            return False
        if any(r.id in set(extra_role_ids) for r in member.roles):
            return True
        return await self._has_level(member, ("support",))

    async def is_blacklisted(self, member: discord.Member) -> bool:
        rows = await self.db.all("SELECT target_id, is_role FROM blacklist WHERE guild_id = ?", (member.guild.id,))
        role_ids = {r.id for r in member.roles}
        for row in rows:
            if row["is_role"] and row["target_id"] in role_ids:
                return True
            if not row["is_role"] and row["target_id"] == member.id:
                return True
        return False

    # ------------------------------------------------------------------ ошибки команд
    async def on_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        gid = interaction.guild_id
        original = error.original if isinstance(error, app_commands.CommandInvokeError) else error
        if isinstance(original, NotAdmin):
            msg = self.t(gid, "err_not_admin")
        elif isinstance(original, NotSupport):
            msg = self.t(gid, "err_not_support")
        elif isinstance(original, PremiumRequired):
            msg = self.t(gid, "err_premium", feature=str(original) or "—")
        elif isinstance(original, app_commands.NoPrivateMessage):
            msg = self.t(gid, "err_guild_only")
        elif isinstance(original, app_commands.CommandOnCooldown):
            msg = self.t(gid, "err_cooldown", seconds=int(original.retry_after) + 1)
        elif isinstance(original, discord.Forbidden):
            msg = self.t(gid, "err_forbidden")
        else:
            log.exception("Ошибка в команде %s", getattr(interaction.command, "qualified_name", "?"), exc_info=original)
            msg = self.t(gid, "err_generic")
        try:
            await utils.reply(interaction, msg)
        except discord.HTTPException:
            pass
