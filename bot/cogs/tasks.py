from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from .. import utils

log = logging.getLogger("ticketbot.cog.tasks")


class Tasks(commands.Cog):
    """Фоновые задачи: отложенное закрытие, автозакрытие по неактивности, SLA."""

    def __init__(self, bot):
        self.bot = bot
        self._ticks = 0
        self.loop.start()

    async def cog_unload(self) -> None:
        self.loop.cancel()

    @tasks.loop(seconds=60)
    async def loop(self) -> None:
        try:
            await self.process_close_requests()
            await self.process_autoclose()
            await self.process_sla()
            self._ticks += 1
            if self._ticks % 60 == 1:  # раз в час
                await self.process_transcript_retention()
        except Exception:
            log.exception("Ошибка фоновой задачи")

    @loop.before_loop
    async def before_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------ /closerequest с таймером
    async def process_close_requests(self) -> None:
        rows = await self.bot.db.all(
            "SELECT * FROM tickets WHERE status = 'open' AND close_at IS NOT NULL AND close_at <= ?", (utils.now(),))
        for ticket in rows:
            gid = ticket["guild_id"]
            reason = ticket["close_request_reason"] or self.bot.t(gid, "reason_close_request")
            await self.bot.tickets.close(ticket, closer=None, reason=reason)

    # ------------------------------------------------------------------ автозакрытие (Premium)
    async def process_autoclose(self) -> None:
        now = utils.now()
        for guild in self.bot.guilds:
            gid = guild.id
            hours = self.bot.get(gid, "autoclose_hours") or 0
            if not hours or not self.bot.is_premium(gid):
                continue
            warn = self.bot.get(gid, "autoclose_warn_hours") or 0
            limit = hours * 3600
            rows = await self.bot.db.all("SELECT * FROM tickets WHERE guild_id = ? AND status = 'open'", (gid,))
            for ticket in rows:
                idle = now - ticket["last_activity_at"]
                if idle >= limit:
                    await self.bot.tickets.close(ticket, closer=None, reason=self.bot.t(gid, "reason_autoclose", hours=hours))
                elif warn and not ticket["warned"] and idle >= limit - warn * 3600:
                    channel = self.bot.tickets.channel_of(ticket)
                    if channel is None:
                        continue
                    await self.bot.db.update("UPDATE tickets SET warned = 1 WHERE id = ?", (ticket["id"],))
                    try:
                        e = self.bot.embed(gid, description=self.bot.t(
                            gid, "autoclose_warning", when=utils.ts(ticket["last_activity_at"] + limit, "R")))
                        await channel.send(content=f"<@{ticket['opener_id']}>", embed=e)
                    except discord.HTTPException:
                        pass

    # ------------------------------------------------------------------ срок хранения транскриптов
    async def process_transcript_retention(self) -> None:
        """Бесплатный тариф хранит транскрипты FREE_TRANSCRIPT_DAYS дней, Premium — без срока."""
        days = self.bot.cfg.free_transcript_days
        if days <= 0 or self.bot.cfg.premium_for_all:
            return
        border = utils.now() - days * 86400
        for guild in self.bot.guilds:
            if not self.bot.is_premium(guild.id):
                await self.bot.db.update(
                    "DELETE FROM transcripts WHERE guild_id = ? AND created_at < ?", (guild.id, border))

    # ------------------------------------------------------------------ SLA (Premium)
    async def process_sla(self) -> None:
        now = utils.now()
        for guild in self.bot.guilds:
            gid = guild.id
            minutes = self.bot.get(gid, "sla_minutes") or 0
            if not minutes or not self.bot.is_premium(gid):
                continue
            rows = await self.bot.db.all(
                "SELECT * FROM tickets WHERE guild_id = ? AND status = 'open' AND first_response_at IS NULL "
                "AND sla_alerted = 0 AND created_at <= ?", (gid, now - minutes * 60))
            if not rows:
                continue
            dest_id = self.bot.get(gid, "sla_channel_id") or self.bot.get(gid, "log_channel_id")
            dest = guild.get_channel(dest_id) if dest_id else None
            role_id = self.bot.get(gid, "sla_role_id")
            for ticket in rows:
                await self.bot.db.update("UPDATE tickets SET sla_alerted = 1 WHERE id = ?", (ticket["id"],))
                if dest is None:
                    continue
                e = self.bot.embed(gid, title=self.bot.t(gid, "sla_title"), color=0xED4245, description=self.bot.t(
                    gid, "sla_desc", channel=f"<#{ticket['channel_id']}>", number=ticket["number"],
                    user=f"<@{ticket['opener_id']}>", minutes=minutes, since=utils.ts(ticket["created_at"], "R")))
                try:
                    await dest.send(content=f"<@&{role_id}>" if role_id else None, embed=e,
                                    allowed_mentions=discord.AllowedMentions(roles=True))
                except discord.HTTPException:
                    pass


async def setup(bot) -> None:
    await bot.add_cog(Tasks(bot))
