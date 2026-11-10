from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import utils
from ..core import premium_only, support_only

log = logging.getLogger("ticketbot.cog.stats")

PERIODS = [
    app_commands.Choice(name="24 часа / 24h", value=1),
    app_commands.Choice(name="7 дней / 7d", value=7),
    app_commands.Choice(name="30 дней / 30d", value=30),
    app_commands.Choice(name="Всё время / all time", value=0),
]


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _since(self, days: int) -> int:
        return utils.now() - days * 86400 if days else 0

    stats = app_commands.Group(name="stats", description="Статистика тикетов (Premium)", guild_only=True)

    @stats.command(name="server", description="Общая статистика сервера")
    @app_commands.describe(period="Период")
    @app_commands.choices(period=PERIODS)
    @support_only()
    @premium_only("statistics")
    async def stats_server(self, interaction: discord.Interaction, period: Optional[app_commands.Choice[int]] = None) -> None:
        gid, db = interaction.guild_id, self.bot.db
        lang = self.bot.lang(gid)
        days = period.value if period else 30
        since = self._since(days)
        total = await db.val("SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND created_at >= ?", (gid, since), 0)
        open_now = await db.val("SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'open'", (gid,), 0)
        closed = await db.val("SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'closed' AND closed_at >= ?",
                              (gid, since), 0)
        first = await db.val("SELECT AVG(first_response_at - created_at) FROM tickets WHERE guild_id = ? AND created_at >= ? "
                             "AND first_response_at IS NOT NULL", (gid, since))
        duration = await db.val("SELECT AVG(closed_at - created_at) FROM tickets WHERE guild_id = ? AND closed_at >= ? "
                                "AND closed_at IS NOT NULL", (gid, since))
        rating = await db.val("SELECT AVG(rating) FROM tickets WHERE guild_id = ? AND created_at >= ? AND rating IS NOT NULL",
                              (gid, since))
        rated = await db.val("SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND created_at >= ? AND rating IS NOT NULL",
                             (gid, since), 0)
        label = period.name if period else PERIODS[2].name
        e = self.bot.embed(gid, title=self.bot.t(gid, "stats_title", period=label))
        e.add_field(name=self.bot.t(gid, "stats_opened"), value=str(total))
        e.add_field(name=self.bot.t(gid, "stats_closed"), value=str(closed))
        e.add_field(name=self.bot.t(gid, "stats_open_now"), value=str(open_now))
        e.add_field(name=self.bot.t(gid, "stats_first_response"), value=utils.fmt_duration(first, lang))
        e.add_field(name=self.bot.t(gid, "stats_avg_duration"), value=utils.fmt_duration(duration, lang))
        e.add_field(name=self.bot.t(gid, "stats_rating"),
                    value=f"⭐ {rating:.2f} ({rated})" if rating is not None else "—")

        by_panel = await db.all(
            "SELECT p.name AS name, COUNT(*) AS n FROM tickets t JOIN panels p ON p.id = t.panel_id "
            "WHERE t.guild_id = ? AND t.created_at >= ? GROUP BY p.id ORDER BY n DESC LIMIT 5", (gid, since))
        if by_panel:
            e.add_field(name=self.bot.t(gid, "stats_by_panel"),
                        value="\n".join(f"**{r['name']}** — {r['n']}" for r in by_panel), inline=False)
        by_prio = await db.all("SELECT priority, COUNT(*) AS n FROM tickets WHERE guild_id = ? AND status = 'open' "
                               "GROUP BY priority ORDER BY priority DESC", (gid,))
        if by_prio:
            e.add_field(name=self.bot.t(gid, "stats_by_priority"), value=" · ".join(
                f"{utils.PRIORITY_EMOJI[r['priority']]} {r['n']}" for r in by_prio), inline=False)
        top_days = await db.all(
            "SELECT strftime('%Y-%m-%d', created_at, 'unixepoch') AS d, COUNT(*) AS n FROM tickets "
            "WHERE guild_id = ? AND created_at >= ? GROUP BY d ORDER BY d DESC LIMIT 7", (gid, utils.now() - 7 * 86400))
        if top_days:
            peak = max(r["n"] for r in top_days) or 1
            e.add_field(name=self.bot.t(gid, "stats_trend"), value="\n".join(
                f"`{r['d']}` {'█' * max(1, round(r['n'] / peak * 12))} {r['n']}" for r in reversed(top_days)), inline=False)
        await utils.reply(interaction, embed=e)

    @stats.command(name="staff", description="Статистика сотрудника")
    @app_commands.describe(user="Сотрудник (по умолчанию вы)", period="Период")
    @app_commands.choices(period=PERIODS)
    @support_only()
    @premium_only("statistics")
    async def stats_staff(self, interaction: discord.Interaction, user: Optional[discord.Member] = None,
                          period: Optional[app_commands.Choice[int]] = None) -> None:
        gid, db = interaction.guild_id, self.bot.db
        lang = self.bot.lang(gid)
        user = user or interaction.user
        since = self._since(period.value if period else 30)
        claimed = await db.val("SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND claimed_by = ? AND created_at >= ?",
                               (gid, user.id, since), 0)
        closed = await db.val("SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND closed_by = ? AND closed_at >= ?",
                              (gid, user.id, since), 0)
        messages = await db.val(
            "SELECT SUM(m.count) FROM ticket_msgs m JOIN tickets t ON t.id = m.ticket_id "
            "WHERE t.guild_id = ? AND m.user_id = ? AND t.created_at >= ?", (gid, user.id, since), 0)
        first = await db.val("SELECT AVG(first_response_at - created_at) FROM tickets WHERE guild_id = ? AND claimed_by = ? "
                             "AND created_at >= ? AND first_response_at IS NOT NULL", (gid, user.id, since))
        rating = await db.val("SELECT AVG(rating) FROM tickets WHERE guild_id = ? AND claimed_by = ? AND created_at >= ? "
                              "AND rating IS NOT NULL", (gid, user.id, since))
        e = self.bot.embed(gid, title=self.bot.t(gid, "stats_staff_title", user=user.display_name))
        e.add_field(name=self.bot.t(gid, "stats_claimed"), value=str(claimed))
        e.add_field(name=self.bot.t(gid, "stats_closed"), value=str(closed))
        e.add_field(name=self.bot.t(gid, "stats_messages"), value=str(messages or 0))
        e.add_field(name=self.bot.t(gid, "stats_first_response"), value=utils.fmt_duration(first, lang))
        e.add_field(name=self.bot.t(gid, "stats_rating"), value=f"⭐ {rating:.2f}" if rating is not None else "—")
        e.set_thumbnail(url=user.display_avatar.url)
        await utils.reply(interaction, embed=e)

    @stats.command(name="leaderboard", description="Рейтинг сотрудников по закрытым тикетам")
    @app_commands.describe(period="Период")
    @app_commands.choices(period=PERIODS)
    @support_only()
    @premium_only("statistics")
    async def stats_leaderboard(self, interaction: discord.Interaction, period: Optional[app_commands.Choice[int]] = None) -> None:
        gid = interaction.guild_id
        since = self._since(period.value if period else 30)
        me = self.bot.user.id if self.bot.user else 0
        rows = await self.bot.db.all(
            "SELECT claimed_by AS uid, COUNT(*) AS n, AVG(rating) AS r FROM tickets "
            "WHERE guild_id = ? AND claimed_by IS NOT NULL AND created_at >= ? AND claimed_by != ? "
            "GROUP BY claimed_by ORDER BY n DESC LIMIT 10", (gid, since, me))
        if not rows:
            return await utils.reply(interaction, self.bot.t(gid, "stats_none"))
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"{medals[i] if i < 3 else f'`{i + 1}.`'} <@{r['uid']}> — **{r['n']}**"
                 + (f" · ⭐ {r['r']:.1f}" if r["r"] is not None else "") for i, r in enumerate(rows)]
        await utils.reply(interaction, embed=self.bot.embed(gid, title=self.bot.t(gid, "leaderboard_title"),
                                                            description="\n".join(lines)))

    @stats.command(name="ratings", description="Последние оценки пользователей")
    @support_only()
    @premium_only("statistics")
    async def stats_ratings(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        rows = await self.bot.db.all(
            "SELECT number, opener_id, claimed_by, rating, rating_comment FROM tickets "
            "WHERE guild_id = ? AND rating IS NOT NULL ORDER BY closed_at DESC LIMIT 10", (gid,))
        if not rows:
            return await utils.reply(interaction, self.bot.t(gid, "stats_none"))
        lines = []
        for r in rows:
            line = f"**#{r['number']}** {'⭐' * r['rating']} <@{r['opener_id']}>"
            if r["claimed_by"]:
                line += f" → <@{r['claimed_by']}>"
            if r["rating_comment"]:
                line += f"\n└ {utils.trunc(r['rating_comment'], 150)}"
            lines.append(line)
        await utils.reply(interaction, embed=self.bot.embed(gid, title=self.bot.t(gid, "ratings_title"), description="\n".join(lines)))


async def setup(bot) -> None:
    await bot.add_cog(Stats(bot))
