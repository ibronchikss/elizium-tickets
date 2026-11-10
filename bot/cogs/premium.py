from __future__ import annotations

import logging
import secrets
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import utils
from ..core import admin_only

log = logging.getLogger("ticketbot.cog.premium")


def make_key() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(4))


class Premium(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _is_owner(self, user: discord.abc.User) -> bool:
        return user.id in self.bot.cfg.owner_ids

    premium = app_commands.Group(name="premium", description="Premium-подписка", guild_only=True)

    @premium.command(name="status", description="Статус Premium на этом сервере")
    async def premium_status(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        until = self.bot.get(gid, "premium_until", 0)
        if self.bot.cfg.premium_for_all:
            text = self.bot.t(gid, "premium_all")
        elif until == -1:
            text = self.bot.t(gid, "premium_forever")
        elif until > utils.now():
            text = self.bot.t(gid, "premium_until", when=utils.ts(until, "F"), rel=utils.ts(until, "R"))
        else:
            text = self.bot.t(gid, "premium_none")
        e = self.bot.embed(gid, title="⭐ Premium", description=text)
        e.add_field(name=self.bot.t(gid, "premium_features"), value=self.bot.t(gid, "premium_features_list"), inline=False)
        await utils.reply(interaction, embed=e)

    @premium.command(name="activate", description="Активировать Premium по ключу")
    @app_commands.describe(key="Ключ активации")
    @admin_only()
    async def premium_activate(self, interaction: discord.Interaction, key: str) -> None:
        gid = interaction.guild_id
        key = key.strip().upper()
        row = await self.bot.db.one("SELECT * FROM premium_keys WHERE key = ?", (key,))
        if row is None or row["used_guild"] is not None:
            return await utils.reply(interaction, self.bot.t(gid, "err_bad_key"))
        claimed = await self.bot.db.update("UPDATE premium_keys SET used_guild = ?, used_at = ? WHERE key = ? AND used_guild IS NULL",
                                           (gid, utils.now(), key))
        if not claimed:
            return await utils.reply(interaction, self.bot.t(gid, "err_bad_key"))
        await self._grant(gid, row["days"])
        await utils.reply(interaction, self.bot.t(gid, "premium_activated"))

    async def _grant(self, gid: int, days: int) -> None:
        current = self.bot.get(gid, "premium_until", 0)
        if current == -1 or days == -1:
            await self.bot.set(gid, "premium_until", -1)
            return
        base = max(current, utils.now())
        await self.bot.set(gid, "premium_until", base + days * 86400)

    @premium.command(name="genkey", description="[Владелец бота] Создать ключ Premium")
    @app_commands.describe(days="На сколько дней (-1 — навсегда)", count="Сколько ключей")
    async def premium_genkey(self, interaction: discord.Interaction, days: app_commands.Range[int, -1, 3650],
                             count: app_commands.Range[int, 1, 20] = 1) -> None:
        gid = interaction.guild_id
        if not self._is_owner(interaction.user) or days == 0:
            return await utils.reply(interaction, self.bot.t(gid, "err_owner_only"))
        keys = [make_key() for _ in range(count)]
        await self.bot.db.many("INSERT INTO premium_keys(key, days, created_by, created_at) VALUES(?,?,?,?)",
                               [(k, days, interaction.user.id, utils.now()) for k in keys])
        await utils.reply(interaction, "\n".join(f"`{k}`" for k in keys))

    @premium.command(name="grant", description="[Владелец бота] Выдать Premium серверу")
    @app_commands.describe(days="Дней (-1 — навсегда)", server_id="ID сервера (по умолчанию текущий)")
    async def premium_grant(self, interaction: discord.Interaction, days: app_commands.Range[int, -1, 3650],
                            server_id: Optional[str] = None) -> None:
        gid = interaction.guild_id
        if not self._is_owner(interaction.user) or days == 0:
            return await utils.reply(interaction, self.bot.t(gid, "err_owner_only"))
        target = int(server_id) if server_id and server_id.isdigit() else gid
        await self._grant(target, days)
        await utils.reply(interaction, self.bot.t(gid, "done"))

    @premium.command(name="revoke", description="[Владелец бота] Забрать Premium у сервера")
    @app_commands.describe(server_id="ID сервера (по умолчанию текущий)")
    async def premium_revoke(self, interaction: discord.Interaction, server_id: Optional[str] = None) -> None:
        gid = interaction.guild_id
        if not self._is_owner(interaction.user):
            return await utils.reply(interaction, self.bot.t(gid, "err_owner_only"))
        target = int(server_id) if server_id and server_id.isdigit() else gid
        await self.bot.set(target, "premium_until", None)
        await utils.reply(interaction, self.bot.t(gid, "done"))


async def setup(bot) -> None:
    await bot.add_cog(Premium(bot))
