from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, Union

import discord

from . import transcript, utils
from .views import ConfirmClose, FormFlow, FormModal, TicketControls, survey_view

if TYPE_CHECKING:  # pragma: no cover
    from .core import TicketBot

log = logging.getLogger("ticketbot.tickets")

MEMBER_PERMS = dict(view_channel=True, send_messages=True, attach_files=True, embed_links=True,
                    read_message_history=True, add_reactions=True)
STAFF_PERMS = dict(MEMBER_PERMS, manage_messages=True)


class TicketError(Exception):
    """Понятная пользователю ошибка (message уже переведён)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class TicketService:
    def __init__(self, bot: "TicketBot"):
        self.bot = bot
        self._locks: dict[tuple[int, int], asyncio.Lock] = {}

    # ================================================================== выборки
    async def by_channel(self, channel_id: int) -> Optional[dict]:
        return await self.bot.db.one("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))

    async def by_id(self, ticket_id: int) -> Optional[dict]:
        return await self.bot.db.one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))

    async def by_number(self, guild_id: int, number: int) -> Optional[dict]:
        return await self.bot.db.one("SELECT * FROM tickets WHERE guild_id = ? AND number = ?", (guild_id, number))

    async def panel(self, panel_id: Optional[int]) -> Optional[dict]:
        if panel_id is None:
            return None
        return await self.bot.db.one("SELECT * FROM panels WHERE id = ?", (panel_id,))

    async def panel_by_name(self, guild_id: int, name: str) -> Optional[dict]:
        return await self.bot.db.one(
            "SELECT * FROM panels WHERE guild_id = ? AND lower(name) = lower(?)", (guild_id, name.strip()))

    async def guild_panels(self, guild_id: int, enabled_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM panels WHERE guild_id = ?" + (" AND enabled = 1" if enabled_only else "") + " ORDER BY id"
        return await self.bot.db.all(sql, (guild_id,))

    async def questions(self, form_id: Optional[int]) -> list[dict]:
        if not form_id:
            return []
        return await self.bot.db.all("SELECT * FROM form_questions WHERE form_id = ? ORDER BY position, id", (form_id,))

    async def staff_ids(self, guild_id: int) -> tuple[list[int], list[int]]:
        rows = await self.bot.db.all("SELECT target_id, is_role FROM staff WHERE guild_id = ?", (guild_id,))
        roles = sorted({r["target_id"] for r in rows if r["is_role"]})
        users = sorted({r["target_id"] for r in rows if not r["is_role"]})
        return roles, users

    def channel_of(self, ticket: dict):
        guild = self.bot.get_guild(ticket["guild_id"])
        if guild is None:
            return None
        return guild.get_channel_or_thread(ticket["channel_id"])

    async def can_manage(self, member: discord.abc.User, ticket: dict) -> bool:
        panel = await self.panel(ticket["panel_id"])
        roles = utils.jl(panel["support_roles"]) if panel else []
        return await self.bot.is_support(member, roles)

    async def can_close(self, member: discord.abc.User, ticket: dict) -> bool:
        return member.id == ticket["opener_id"] or await self.can_manage(member, ticket)

    # ================================================================== часы поддержки
    async def hours_windows(self, guild_id: int) -> list[dict]:
        return await self.bot.db.all("SELECT * FROM hours WHERE guild_id = ? ORDER BY id", (guild_id,))

    async def within_hours(self, guild_id: int) -> bool:
        windows = await self.hours_windows(guild_id)
        if not windows:
            return True
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(self.bot.get(guild_id, "timezone") or "UTC")
        except Exception:
            tz = timezone.utc
        return utils.hours_match(windows, datetime.now(tz))

    def format_hours(self, guild_id: int, windows: list[dict]) -> str:
        lang = self.bot.lang(guild_id)
        names = {
            "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
            "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        }[lang if lang in ("ru", "en") else "ru"]
        lines = []
        for w in windows:
            days = ",".join(names[int(d)] for d in w["days"].split(",") if d != "")
            lines.append(f"**{days}** {w['start_min'] // 60:02d}:{w['start_min'] % 60:02d}–"
                         f"{w['end_min'] // 60:02d}:{w['end_min'] % 60:02d}")
        return "\n".join(lines) + f"\n({self.bot.get(guild_id, 'timezone')})"

    # ================================================================== проверки перед открытием
    async def precheck(self, guild: discord.Guild, member: discord.Member, panel: dict, *, by_staff: bool = False) -> Optional[str]:
        bot, gid = self.bot, guild.id
        if not panel["enabled"]:
            return bot.t(gid, "err_panel_disabled")
        if by_staff:
            return None
        if await bot.is_blacklisted(member):
            return bot.t(gid, "err_blacklisted")
        req = panel["required_role_id"]
        if req and not any(r.id == req for r in member.roles):
            return bot.t(gid, "err_required_role", role=f"<@&{req}>")
        if panel["ticket_limit"]:
            limit = panel["ticket_limit"]
            count = await bot.db.val(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND opener_id = ? AND panel_id = ? AND status = 'open'",
                (gid, member.id, panel["id"]), 0)
        else:
            limit = bot.get(gid, "ticket_limit")
            count = await bot.db.val(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND opener_id = ? AND status = 'open'",
                (gid, member.id), 0)
        if limit and count >= limit:
            return bot.t(gid, "err_limit", limit=limit)
        if panel["enforce_hours"] and not await self.within_hours(gid):
            windows = await self.hours_windows(gid)
            return bot.t(gid, "err_hours", hours=self.format_hours(gid, windows))
        return None

    # ================================================================== открытие
    async def start(self, interaction: discord.Interaction, panel_id: int, *, target: Optional[discord.Member] = None,
                    subject: Optional[str] = None, quote: Optional[discord.Message] = None) -> None:
        bot = self.bot
        guild = interaction.guild
        if guild is None:
            return await utils.reply(interaction, bot.t(None, "err_guild_only"))
        gid = guild.id
        panel = await self.panel(panel_id)
        if panel is None or panel["guild_id"] != gid:
            return await utils.reply(interaction, bot.t(gid, "err_panel_missing"))
        opener = target or interaction.user
        if not isinstance(opener, discord.Member):
            return await utils.reply(interaction, bot.t(gid, "err_generic"))
        err = await self.precheck(guild, opener, panel, by_staff=target is not None)
        if err:
            return await utils.reply(interaction, err)

        questions = [] if target is not None else await self.questions(panel["form_id"])
        if questions:
            flow = FormFlow(panel, opener, utils.chunks(questions, 5))
            await interaction.response.send_modal(FormModal(bot, flow))
            return
        await interaction.response.defer(ephemeral=True)
        await self.finish(interaction, panel, opener, [], subject, interaction.user if target is not None else None, quote)

    async def finish(self, interaction: discord.Interaction, panel: dict, opener: discord.Member,
                     answers: list[tuple[str, str]], subject: Optional[str], created_by: Optional[discord.Member] = None,
                     quote: Optional[discord.Message] = None) -> None:
        """Создаёт тикет и отвечает пользователю (interaction уже должен быть deferred)."""
        bot = self.bot
        gid = interaction.guild.id
        if subject is None and answers:
            subject = utils.trunc(answers[0][1], 100)
        try:
            ticket, channel = await self.create(interaction.guild, opener, panel, answers=answers, subject=subject,
                                                created_by=created_by, quote=quote)
        except TicketError as exc:
            return await utils.reply(interaction, exc.message)
        except discord.Forbidden:
            return await utils.reply(interaction, bot.t(gid, "err_forbidden"))
        except discord.HTTPException:
            log.exception("Не удалось создать тикет")
            return await utils.reply(interaction, bot.t(gid, "err_generic"))
        await utils.reply(interaction, bot.t(gid, "ticket_created", channel=channel.mention))

    async def create(self, guild: discord.Guild, opener: discord.Member, panel: dict, *, answers: list[tuple[str, str]],
                     subject: Optional[str], created_by: Optional[discord.Member] = None,
                     quote: Optional[discord.Message] = None):
        bot, gid = self.bot, guild.id
        lock = self._locks.setdefault((gid, opener.id), asyncio.Lock())
        async with lock:
            err = await self.precheck(guild, opener, panel, by_staff=created_by is not None)
            if err:
                raise TicketError(err)

            number = await bot.db.next_ticket_number(gid)
            use_threads = panel["use_threads"] if panel["use_threads"] is not None else bot.get(gid, "use_threads")
            pattern = panel["naming"] or bot.get(gid, "naming") or "ticket-{number}"
            name = utils.slug(utils.fill(pattern, number=f"{number:04d}", user=utils.slug(opener.name),
                                         username=utils.slug(opener.display_name), panel=utils.slug(panel["name"])), 90)
            reason = f"Ticket #{number} — {opener}"
            on_call = [r["user_id"] for r in await bot.db.all("SELECT user_id FROM oncall WHERE guild_id = ?", (gid,))]
            _, staff_users = await self.staff_ids(gid)

            if use_threads:
                parent = guild.get_channel(panel["channel_id"] or 0) or guild.get_channel(bot.get(gid, "thread_parent_id") or 0)
                if not isinstance(parent, discord.TextChannel):
                    raise TicketError(bot.t(gid, "err_no_thread_parent"))
                channel = await parent.create_thread(name=name[:100], type=discord.ChannelType.private_thread,
                                                     invitable=False, auto_archive_duration=10080, reason=reason)
                try:
                    await channel.add_user(opener)
                    for uid in set(on_call) | set(staff_users):
                        member = guild.get_member(uid)
                        if member is not None and member.id != opener.id:
                            await channel.add_user(member)
                except discord.HTTPException:
                    log.warning("Не удалось добавить участников в тред", exc_info=True)
            else:
                category = guild.get_channel(panel["category_id"] or 0) or guild.get_channel(bot.get(gid, "category_id") or 0)
                if not isinstance(category, discord.CategoryChannel):
                    category = None
                overwrites = await self._overwrites(guild, opener, panel)
                topic = bot.t(gid, "channel_topic", user=str(opener), number=number, panel=panel["name"])
                channel = await guild.create_text_channel(name=name, category=category, overwrites=overwrites,
                                                          topic=utils.trunc(topic, 1000), reason=reason)

            try:
                ticket_id = await bot.db.execute(
                    "INSERT INTO tickets(guild_id, number, channel_id, is_thread, panel_id, opener_id, priority, subject, "
                    "created_at, last_activity_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (gid, number, channel.id, 1 if use_threads else 0, panel["id"], opener.id,
                     panel["default_priority"], subject, utils.now(), utils.now()))
            except Exception:
                await self._silent_delete(channel)
                raise
            bot.open_channels[channel.id] = ticket_id
            ticket = await self.by_id(ticket_id)

        await self._welcome(guild, channel, ticket, panel, opener, answers, on_call, created_by, quote)

        if bot.is_premium(gid) and panel["role_on_open"]:
            role = guild.get_role(panel["role_on_open"])
            if role:
                try:
                    await opener.add_roles(role, reason=f"Ticket #{number}")
                except discord.HTTPException:
                    pass
        return ticket, channel

    async def _silent_delete(self, channel) -> None:
        try:
            await channel.delete()
        except discord.HTTPException:
            pass

    async def _overwrites(self, guild: discord.Guild, opener: discord.Member, panel: dict) -> dict:
        ow: dict = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True, attach_files=True,
                                                  read_message_history=True, manage_messages=True),
            opener: discord.PermissionOverwrite(**MEMBER_PERMS),
        }
        role_ids, user_ids = await self.staff_ids(guild.id)
        for rid in set(role_ids) | set(utils.jl(panel["support_roles"])):
            role = guild.get_role(rid)
            if role is not None:
                ow[role] = discord.PermissionOverwrite(**STAFF_PERMS)
        for uid in user_ids:
            member = guild.get_member(uid)
            if member is not None and member.id != opener.id:
                ow[member] = discord.PermissionOverwrite(**STAFF_PERMS)
        return ow

    async def _welcome(self, guild, channel, ticket, panel, opener, answers, on_call, created_by, quote) -> None:
        bot, gid = self.bot, guild.id
        template = panel["welcome_message"] or bot.get(gid, "welcome") or bot.t(gid, "welcome_default")
        staff_mentions = " ".join(f"<@&{r}>" for r in utils.jl(panel["support_roles"]))
        text = utils.fill(template, user=opener.mention, username=opener.display_name, user_id=opener.id,
                          number=ticket["number"], panel=panel["name"], guild=guild.name, server=guild.name,
                          staff=staff_mentions, date=utils.ts(utils.now(), "F"))
        embed = bot.embed(gid, title=bot.t(gid, "ticket_title", number=ticket["number"]), description=text, color=panel["color"])
        if created_by is not None:
            embed.add_field(name=bot.t(gid, "f_created_by"), value=created_by.mention, inline=True)
        if ticket["priority"] != 1 and bot.is_premium(gid):
            embed.add_field(name=bot.t(gid, "f_priority"),
                            value=f"{utils.PRIORITY_EMOJI[ticket['priority']]} {bot.t(gid, 'prio_' + utils.PRIORITY_NAMES[ticket['priority']])}")
        mentions = [opener.mention] + [f"<@&{r}>" for r in utils.jl(panel["ping_roles"])] + [f"<@{u}>" for u in on_call]
        content = " ".join(dict.fromkeys(mentions))
        msg = await channel.send(content=content, embed=embed, view=TicketControls.build(bot, gid))
        try:
            await msg.pin()
        except discord.HTTPException:
            pass

        if answers:
            ans = bot.embed(gid, title=bot.t(gid, "form_answers"), footer=False)
            for label, value in answers[:25]:
                ans.add_field(name=utils.trunc(label, 256), value=utils.trunc(value or "—", 1024) or "—", inline=False)
            await channel.send(embed=ans)
        if quote is not None:
            q = bot.embed(gid, description=utils.trunc(quote.content or "—", 3500), footer=False)
            q.set_author(name=str(quote.author), icon_url=quote.author.display_avatar.url, url=quote.jump_url)
            await channel.send(embed=q)
        if bot.is_premium(gid):
            query = " ".join([ticket["subject"] or ""] + [a[1] for a in answers])
            await self.suggest_kb(gid, channel, query)

    async def suggest_kb(self, guild_id: int, channel, query: str) -> None:
        if not query.strip():
            return
        articles = await self.bot.db.all("SELECT * FROM kb WHERE guild_id = ?", (guild_id,))
        scored = sorted(((utils.score_article(query, a), a) for a in articles), key=lambda x: -x[0])
        top = [a for s, a in scored if s >= 3][:3]
        if not top:
            return
        e = self.bot.embed(guild_id, title=self.bot.t(guild_id, "kb_suggest_title"))
        for a in top:
            e.add_field(name=utils.trunc(a["title"], 256), value=utils.trunc(a["content"], 400), inline=False)
        try:
            await channel.send(embed=e)
        except discord.HTTPException:
            pass

    # ================================================================== закрытие
    async def close_prompt(self, interaction: discord.Interaction) -> None:
        bot = self.bot
        gid = interaction.guild_id
        ticket = await self.by_channel(interaction.channel_id)
        if ticket is None or ticket["status"] != "open":
            return await utils.reply(interaction, bot.t(gid, "err_not_ticket"))
        if not await self.can_close(interaction.user, ticket):
            return await utils.reply(interaction, bot.t(gid, "err_cannot_close"))
        if bot.get(gid, "close_confirm"):
            await utils.reply(interaction, bot.t(gid, "close_confirm"), view=ConfirmClose(bot, ticket["id"], gid))
        else:
            await utils.reply(interaction, bot.t(gid, "closing"))
            await self.close(ticket, closer=interaction.user)

    async def close(self, ticket: dict, *, closer: Optional[discord.abc.User] = None, reason: Optional[str] = None) -> bool:
        bot = self.bot
        gid = ticket["guild_id"]
        closer_id = closer.id if closer is not None else (bot.user.id if bot.user else 0)
        changed = await bot.db.update(
            "UPDATE tickets SET status = 'closed', closed_at = ?, closed_by = ?, close_reason = ?, close_at = NULL "
            "WHERE id = ? AND status = 'open'", (utils.now(), closer_id, reason, ticket["id"]))
        if not changed:
            return False
        bot.open_channels.pop(ticket["channel_id"], None)
        ticket = await self.by_id(ticket["id"])
        guild = bot.get_guild(gid)
        panel = await self.panel(ticket["panel_id"])
        channel = self.channel_of(ticket)
        opener = guild.get_member(ticket["opener_id"]) if guild else None
        if opener is None and ticket["opener_id"]:
            try:
                opener = await bot.fetch_user(ticket["opener_id"])
            except discord.HTTPException:
                opener = None

        html_text, msg_count = None, 0
        if channel is not None:
            meta = [
                (bot.t(gid, "f_ticket"), f"#{ticket['number']}"),
                (bot.t(gid, "f_opener"), f"{opener} ({ticket['opener_id']})" if opener else str(ticket["opener_id"])),
                (bot.t(gid, "f_panel"), panel["name"] if panel else "—"),
                (bot.t(gid, "f_reason"), reason or "—"),
            ]
            try:
                html_text, msg_count = await transcript.render(
                    channel, title=bot.t(gid, "transcript_title", number=ticket["number"], guild=guild.name if guild else ""),
                    meta=meta)
                await bot.db.execute(
                    "INSERT OR REPLACE INTO transcripts(ticket_id, guild_id, html, created_at) VALUES(?,?,?,?)",
                    (ticket["id"], gid, transcript.pack(html_text), utils.now()))
            except Exception:
                log.exception("Не удалось собрать транскрипт тикета %s", ticket["id"])

        def make_file() -> Optional[discord.File]:
            if not html_text:
                return None
            return discord.File(io.BytesIO(html_text.encode("utf-8")), filename=f"transcript-{ticket['number']}.html")

        if guild is not None:
            await self._send_log(guild, ticket, panel, opener, closer_id, reason, msg_count, make_file)
        await self._notify_opener(guild, ticket, opener, reason, make_file)

        if guild is not None and opener is not None and bot.is_premium(gid) and panel:
            member = guild.get_member(opener.id)
            if member is not None:
                try:
                    if panel["role_on_open"] and (role := guild.get_role(panel["role_on_open"])):
                        await member.remove_roles(role, reason="Ticket closed")
                    if panel["role_on_close"] and (role := guild.get_role(panel["role_on_close"])):
                        await member.add_roles(role, reason="Ticket closed")
                except discord.HTTPException:
                    pass

        if channel is not None:
            try:
                if ticket["is_thread"] and not bot.get(gid, "delete_on_close"):
                    await channel.edit(archived=True, locked=True)
                else:
                    await channel.delete(reason=f"Ticket #{ticket['number']} closed")
            except discord.HTTPException:
                log.warning("Не удалось удалить/архивировать канал тикета %s", ticket["id"], exc_info=True)
        return True

    async def _send_log(self, guild, ticket, panel, opener, closer_id, reason, msg_count, make_file) -> None:
        bot, gid = self.bot, guild.id
        log_id = bot.get(gid, "log_channel_id")
        tr_id = bot.get(gid, "transcript_channel_id") or log_id
        if not log_id and not tr_id:
            return
        lang = bot.lang(gid)
        e = bot.embed(gid, title=bot.t(gid, "log_closed_title", number=ticket["number"]), color=0xED4245)
        e.add_field(name=bot.t(gid, "f_opener"), value=f"<@{ticket['opener_id']}>")
        e.add_field(name=bot.t(gid, "f_closed_by"), value=f"<@{closer_id}>")
        e.add_field(name=bot.t(gid, "f_claimed_by"), value=f"<@{ticket['claimed_by']}>" if ticket["claimed_by"] else "—")
        e.add_field(name=bot.t(gid, "f_panel"), value=panel["name"] if panel else "—")
        e.add_field(name=bot.t(gid, "f_duration"), value=utils.fmt_duration(ticket["closed_at"] - ticket["created_at"], lang))
        e.add_field(name=bot.t(gid, "f_messages"), value=str(msg_count))
        e.add_field(name=bot.t(gid, "f_reason"), value=utils.trunc(reason or "—", 1000), inline=False)
        if ticket["subject"]:
            e.add_field(name=bot.t(gid, "f_subject"), value=utils.trunc(ticket["subject"], 1000), inline=False)
        e.add_field(name=bot.t(gid, "f_opened"), value=utils.ts(ticket["created_at"], "f"))
        try:
            if log_id and log_id == tr_id:
                ch = guild.get_channel(log_id)
                if ch is not None:
                    f = make_file()
                    await ch.send(embed=e, **({"file": f} if f else {}))
            else:
                if log_id and (ch := guild.get_channel(log_id)) is not None:
                    await ch.send(embed=e)
                if tr_id and (ch := guild.get_channel(tr_id)) is not None:
                    f = make_file()
                    await ch.send(embed=e, **({"file": f} if f else {}))
        except discord.HTTPException:
            log.warning("Не удалось отправить лог закрытия", exc_info=True)

    async def _notify_opener(self, guild, ticket, opener, reason, make_file) -> None:
        bot, gid = self.bot, ticket["guild_id"]
        if opener is None:
            return
        want_file = bool(bot.get(gid, "dm_transcript"))
        want_survey = bool(bot.get(gid, "survey")) and bot.is_premium(gid)
        if not want_file and not want_survey:
            return
        gname = guild.name if guild else ""
        e = bot.embed(gid, title=bot.t(gid, "dm_closed_title", number=ticket["number"], guild=gname),
                      description=bot.t(gid, "dm_closed_desc", reason=reason or "—"))
        kwargs: dict = {"embed": e}
        if want_file and (f := make_file()) is not None:
            kwargs["file"] = f
        if want_survey:
            e.add_field(name=bot.t(gid, "survey_title"), value=bot.t(gid, "survey_desc"), inline=False)
            kwargs["view"] = survey_view(ticket["id"])
        try:
            await opener.send(**kwargs)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ================================================================== claim / участники / приоритет
    async def claim(self, ticket: dict, member: discord.abc.User) -> Optional[str]:
        """None — успех, иначе ключ ошибки."""
        n = await self.bot.db.update(
            "UPDATE tickets SET claimed_by = ?, first_response_at = COALESCE(first_response_at, ?) "
            "WHERE id = ? AND claimed_by IS NULL AND status = 'open'", (member.id, utils.now(), ticket["id"]))
        if not n:
            return "err_already_claimed"
        channel = self.channel_of(ticket)
        if channel is not None:
            gid = ticket["guild_id"]
            e = self.bot.embed(gid, description=self.bot.t(gid, "claimed_msg", user=member.mention), footer=False, color=0x57F287)
            try:
                await channel.send(embed=e)
            except discord.HTTPException:
                pass
        return None

    async def release(self, ticket: dict, member: discord.abc.User) -> Optional[str]:
        if not ticket["claimed_by"]:
            return "err_not_claimed"
        if ticket["claimed_by"] != member.id and not await self.bot.is_admin(member):
            return "err_not_claimer"
        await self.bot.db.update("UPDATE tickets SET claimed_by = NULL WHERE id = ?", (ticket["id"],))
        channel = self.channel_of(ticket)
        if channel is not None:
            gid = ticket["guild_id"]
            e = self.bot.embed(gid, description=self.bot.t(gid, "released_msg", user=member.mention), footer=False)
            try:
                await channel.send(embed=e)
            except discord.HTTPException:
                pass
        return None

    async def claim_interaction(self, interaction: discord.Interaction) -> None:
        bot, gid = self.bot, interaction.guild_id
        ticket = await self.by_channel(interaction.channel_id)
        if ticket is None or ticket["status"] != "open":
            return await utils.reply(interaction, bot.t(gid, "err_not_ticket"))
        if not await self.can_manage(interaction.user, ticket):
            return await utils.reply(interaction, bot.t(gid, "err_not_support"))
        err = await self.claim(ticket, interaction.user)
        if err:
            return await utils.reply(interaction, bot.t(gid, err))
        await utils.reply(interaction, bot.t(gid, "claimed_ok"))

    async def add_member(self, ticket: dict, target: Union[discord.Member, discord.Role]) -> None:
        channel = self.channel_of(ticket)
        gid = ticket["guild_id"]
        if channel is None:
            raise TicketError(self.bot.t(gid, "err_not_ticket"))
        if ticket["is_thread"]:
            if isinstance(target, discord.Member):
                await channel.add_user(target)
            else:
                await channel.send(target.mention, allowed_mentions=discord.AllowedMentions(roles=True))
        else:
            await channel.set_permissions(target, overwrite=discord.PermissionOverwrite(**MEMBER_PERMS))
        if isinstance(target, discord.Member):
            await self.bot.db.execute("INSERT OR IGNORE INTO ticket_users(ticket_id, user_id) VALUES(?, ?)",
                                      (ticket["id"], target.id))

    async def remove_member(self, ticket: dict, target: Union[discord.Member, discord.Role]) -> None:
        channel = self.channel_of(ticket)
        gid = ticket["guild_id"]
        if channel is None:
            raise TicketError(self.bot.t(gid, "err_not_ticket"))
        if isinstance(target, discord.Member) and target.id == ticket["opener_id"]:
            raise TicketError(self.bot.t(gid, "err_remove_opener"))
        if ticket["is_thread"]:
            if not isinstance(target, discord.Member):
                raise TicketError(self.bot.t(gid, "err_role_in_thread"))
            await channel.remove_user(target)
        else:
            await channel.set_permissions(target, overwrite=None)
        if isinstance(target, discord.Member):
            await self.bot.db.execute("DELETE FROM ticket_users WHERE ticket_id = ? AND user_id = ?", (ticket["id"], target.id))

    async def set_priority(self, ticket: dict, level: int, by: discord.abc.User) -> None:
        await self.bot.db.update("UPDATE tickets SET priority = ? WHERE id = ?", (level, ticket["id"]))
        channel = self.channel_of(ticket)
        gid = ticket["guild_id"]
        if channel is not None:
            e = self.bot.embed(gid, footer=False, description=self.bot.t(
                gid, "priority_set", user=by.mention, emoji=utils.PRIORITY_EMOJI[level],
                level=self.bot.t(gid, "prio_" + utils.PRIORITY_NAMES[level])))
            try:
                await channel.send(embed=e)
            except discord.HTTPException:
                pass

    async def move(self, ticket: dict, new_panel: dict) -> None:
        bot = self.bot
        gid = ticket["guild_id"]
        channel = self.channel_of(ticket)
        old_panel = await self.panel(ticket["panel_id"])
        await bot.db.update("UPDATE tickets SET panel_id = ? WHERE id = ?", (new_panel["id"], ticket["id"]))
        if channel is None or ticket["is_thread"]:
            return
        guild = channel.guild
        global_roles, _ = await self.staff_ids(gid)
        old_roles = set(utils.jl(old_panel["support_roles"])) if old_panel else set()
        new_roles = set(utils.jl(new_panel["support_roles"]))
        for rid in new_roles:
            role = guild.get_role(rid)
            if role is not None:
                await channel.set_permissions(role, overwrite=discord.PermissionOverwrite(**STAFF_PERMS))
        for rid in old_roles - new_roles - set(global_roles):
            role = guild.get_role(rid)
            if role is not None:
                await channel.set_permissions(role, overwrite=None)
        category = guild.get_channel(new_panel["category_id"] or 0)
        if isinstance(category, discord.CategoryChannel):
            await channel.edit(category=category)
