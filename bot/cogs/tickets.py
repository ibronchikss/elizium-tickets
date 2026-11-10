from __future__ import annotations

import logging
from typing import Optional, Union

import discord
from discord import app_commands
from discord.ext import commands

from .. import ac, utils
from ..core import admin_only, premium_only, support_only
from ..services import TicketError
from ..views import CloseRequestView, PanelPicker

log = logging.getLogger("ticketbot.cog.tickets")

PRIORITY_CHOICES = [
    app_commands.Choice(name="low / низкий", value=0),
    app_commands.Choice(name="normal / обычный", value=1),
    app_commands.Choice(name="high / высокий", value=2),
    app_commands.Choice(name="urgent / срочный", value=3),
]


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.svc = bot.tickets
        self.menus = [
            app_commands.ContextMenu(name="Create ticket for user", callback=self.menu_ticket_for_user),
            app_commands.ContextMenu(name="Create ticket from message", callback=self.menu_ticket_from_message),
            app_commands.ContextMenu(name="Pin message", callback=self.menu_pin),
        ]
        for menu in self.menus:
            bot.tree.add_command(menu)

    async def cog_unload(self) -> None:
        for menu in self.menus:
            self.bot.tree.remove_command(menu.name, type=menu.type)

    # ------------------------------------------------------------------ утилиты
    async def ticket_here(self, interaction: discord.Interaction) -> Optional[dict]:
        ticket = await self.svc.by_channel(interaction.channel_id)
        if ticket is None or ticket["status"] != "open":
            await utils.reply(interaction, self.bot.t(interaction.guild_id, "err_not_ticket"))
            return None
        return ticket

    async def staff_ticket(self, interaction: discord.Interaction) -> Optional[dict]:
        """Тикет в текущем канале + проверка, что вызывающий — поддержка."""
        ticket = await self.ticket_here(interaction)
        if ticket is None:
            return None
        if not await self.svc.can_manage(interaction.user, ticket):
            await utils.reply(interaction, self.bot.t(interaction.guild_id, "err_not_support"))
            return None
        return ticket

    # ------------------------------------------------------------------ открытие / закрытие
    @app_commands.command(name="open", description="Открыть тикет / Open a ticket")
    @app_commands.guild_only()
    @app_commands.describe(panel="Тип тикета (панель)")
    async def open_cmd(self, interaction: discord.Interaction, panel: Optional[str] = None) -> None:
        gid = interaction.guild_id
        if panel:
            found = await self.svc.panel_by_name(gid, panel)
            if found is None:
                return await utils.reply(interaction, self.bot.t(gid, "err_panel_missing"))
            return await self.svc.start(interaction, found["id"])
        panels = await self.svc.guild_panels(gid, enabled_only=True)
        if not panels:
            return await utils.reply(interaction, self.bot.t(gid, "err_no_panels"))
        if len(panels) == 1:
            return await self.svc.start(interaction, panels[0]["id"])
        await utils.reply(interaction, self.bot.t(gid, "pick_panel"), view=PanelPicker(panels))

    @open_cmd.autocomplete("panel")
    async def open_panel_ac(self, interaction: discord.Interaction, current: str):
        return await ac.panel_ac(interaction, current)

    @app_commands.command(name="close", description="Закрыть тикет / Close the ticket")
    @app_commands.guild_only()
    @app_commands.describe(reason="Причина закрытия")
    async def close_cmd(self, interaction: discord.Interaction, reason: Optional[str] = None) -> None:
        ticket = await self.ticket_here(interaction)
        if ticket is None:
            return
        if not await self.svc.can_close(interaction.user, ticket):
            return await utils.reply(interaction, self.bot.t(interaction.guild_id, "err_cannot_close"))
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "closing"))
        await self.svc.close(ticket, closer=interaction.user, reason=utils.trunc(reason, 500) if reason else None)

    @app_commands.command(name="closerequest", description="Попросить автора подтвердить закрытие тикета")
    @app_commands.guild_only()
    @app_commands.describe(close_delay="Автозакрытие, если автор не ответит (напр. 12h, 1d)", reason="Причина")
    async def closerequest_cmd(self, interaction: discord.Interaction, close_delay: Optional[str] = None,
                               reason: Optional[str] = None) -> None:
        gid = interaction.guild_id
        ticket = await self.staff_ticket(interaction)
        if ticket is None:
            return
        delay = None
        if close_delay:
            delay = utils.parse_duration(close_delay)
            if delay is None or delay < 60:
                return await utils.reply(interaction, self.bot.t(gid, "err_bad_duration"))
        close_at = utils.now() + delay if delay else None
        reason = utils.trunc(reason, 500) if reason else None
        await self.bot.db.update(
            "UPDATE tickets SET close_at = ?, close_request_by = ?, close_request_reason = ? WHERE id = ?",
            (close_at, interaction.user.id, reason, ticket["id"]))
        text = self.bot.t(gid, "close_request_msg", user=interaction.user.mention)
        if reason:
            text += "\n" + self.bot.t(gid, "close_request_reason", reason=reason)
        if delay:
            text += "\n" + self.bot.t(gid, "close_request_delay", when=utils.ts(close_at, "R"))
        embed = self.bot.embed(gid, title=self.bot.t(gid, "close_request_title"), description=text)
        await interaction.channel.send(content=f"<@{ticket['opener_id']}>", embed=embed,
                                       view=CloseRequestView.build(self.bot, gid))
        await utils.reply(interaction, self.bot.t(gid, "close_request_sent"))

    # ------------------------------------------------------------------ claim
    @app_commands.command(name="claim", description="Взять тикет / Claim the ticket")
    @app_commands.guild_only()
    async def claim_cmd(self, interaction: discord.Interaction) -> None:
        await self.svc.claim_interaction(interaction)

    @app_commands.command(name="release", description="Снять с себя тикет / Release the ticket")
    @app_commands.guild_only()
    async def release_cmd(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        ticket = await self.staff_ticket(interaction)
        if ticket is None:
            return
        err = await self.svc.release(ticket, interaction.user)
        await utils.reply(interaction, self.bot.t(gid, err or "released_ok"))

    @app_commands.command(name="transfer", description="Передать тикет другому сотруднику")
    @app_commands.guild_only()
    @app_commands.describe(user="Новый ответственный")
    async def transfer_cmd(self, interaction: discord.Interaction, user: discord.Member) -> None:
        gid = interaction.guild_id
        ticket = await self.staff_ticket(interaction)
        if ticket is None:
            return
        if not await self.svc.can_manage(user, ticket):
            return await utils.reply(interaction, self.bot.t(gid, "err_target_not_staff"))
        await self.bot.db.update("UPDATE tickets SET claimed_by = ?, first_response_at = COALESCE(first_response_at, ?) WHERE id = ?",
                                 (user.id, utils.now(), ticket["id"]))
        e = self.bot.embed(gid, footer=False, description=self.bot.t(gid, "transferred_msg", user=user.mention, by=interaction.user.mention))
        await interaction.channel.send(embed=e)
        await utils.reply(interaction, self.bot.t(gid, "done"))

    # ------------------------------------------------------------------ участники
    @app_commands.command(name="add", description="Добавить пользователя или роль в тикет")
    @app_commands.guild_only()
    @app_commands.describe(user_or_role="Пользователь или роль")
    async def add_cmd(self, interaction: discord.Interaction, user_or_role: Union[discord.Member, discord.Role]) -> None:
        gid = interaction.guild_id
        ticket = await self.staff_ticket(interaction)
        if ticket is None:
            return
        try:
            await self.svc.add_member(ticket, user_or_role)
        except TicketError as exc:
            return await utils.reply(interaction, exc.message)
        await utils.reply(interaction, self.bot.t(gid, "added_ok", target=user_or_role.mention), ephemeral=False)

    @app_commands.command(name="remove", description="Убрать пользователя или роль из тикета")
    @app_commands.guild_only()
    @app_commands.describe(user_or_role="Пользователь или роль")
    async def remove_cmd(self, interaction: discord.Interaction, user_or_role: Union[discord.Member, discord.Role]) -> None:
        gid = interaction.guild_id
        ticket = await self.staff_ticket(interaction)
        if ticket is None:
            return
        try:
            await self.svc.remove_member(ticket, user_or_role)
        except TicketError as exc:
            return await utils.reply(interaction, exc.message)
        await utils.reply(interaction, self.bot.t(gid, "removed_ok", target=user_or_role.mention), ephemeral=False)

    # ------------------------------------------------------------------ приоритет, правка, перенос
    @app_commands.command(name="priority", description="Приоритет тикета (Premium)")
    @app_commands.guild_only()
    @app_commands.describe(level="Уровень приоритета")
    @app_commands.choices(level=PRIORITY_CHOICES)
    @premium_only("priority")
    async def priority_cmd(self, interaction: discord.Interaction, level: app_commands.Choice[int]) -> None:
        ticket = await self.staff_ticket(interaction)
        if ticket is None:
            return
        await self.svc.set_priority(ticket, level.value, interaction.user)
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "done"))

    @app_commands.command(name="edit", description="Изменить название или тему тикета")
    @app_commands.guild_only()
    @app_commands.describe(name="Новое название канала", topic="Новая тема тикета")
    async def edit_cmd(self, interaction: discord.Interaction, name: Optional[str] = None, topic: Optional[str] = None) -> None:
        gid = interaction.guild_id
        ticket = await self.staff_ticket(interaction)
        if ticket is None:
            return
        if not name and not topic:
            return await utils.reply(interaction, self.bot.t(gid, "err_nothing_to_edit"))
        await interaction.response.defer(ephemeral=True)
        channel = self.svc.channel_of(ticket)
        if name and channel is not None:
            await channel.edit(name=utils.slug(name, 90))
        if topic:
            await self.bot.db.update("UPDATE tickets SET subject = ? WHERE id = ?", (utils.trunc(topic, 100), ticket["id"]))
            if channel is not None and not ticket["is_thread"]:
                await channel.edit(topic=utils.trunc(topic, 1000))
        await utils.reply(interaction, self.bot.t(gid, "done"))

    @app_commands.command(name="move", description="Перенести тикет в другую панель")
    @app_commands.guild_only()
    @app_commands.describe(panel="Целевая панель")
    async def move_cmd(self, interaction: discord.Interaction, panel: str) -> None:
        gid = interaction.guild_id
        ticket = await self.staff_ticket(interaction)
        if ticket is None:
            return
        target = await self.svc.panel_by_name(gid, panel)
        if target is None:
            return await utils.reply(interaction, self.bot.t(gid, "err_panel_missing"))
        await interaction.response.defer(ephemeral=True)
        await self.svc.move(ticket, target)
        await interaction.channel.send(embed=self.bot.embed(gid, footer=False, description=self.bot.t(
            gid, "moved_msg", user=interaction.user.mention, panel=target["name"])))
        await utils.reply(interaction, self.bot.t(gid, "done"))

    @move_cmd.autocomplete("panel")
    async def move_panel_ac(self, interaction: discord.Interaction, current: str):
        return await ac.panel_ac(interaction, current)

    # ------------------------------------------------------------------ список тикетов
    tickets = app_commands.Group(name="tickets", description="Просмотр тикетов", guild_only=True)

    @tickets.command(name="list", description="Список открытых тикетов")
    @app_commands.describe(priority="Только этого приоритета", mine="Только мои (взятые мной)",
                           unclaimed="Только без ответственного", user="Тикеты этого автора")
    @app_commands.choices(priority=PRIORITY_CHOICES)
    @support_only()
    async def tickets_list(self, interaction: discord.Interaction, priority: Optional[app_commands.Choice[int]] = None,
                           mine: bool = False, unclaimed: bool = False, user: Optional[discord.Member] = None) -> None:
        gid = interaction.guild_id
        sql = "SELECT * FROM tickets WHERE guild_id = ? AND status = 'open'"
        params: list = [gid]
        if priority is not None:
            sql += " AND priority = ?"
            params.append(priority.value)
        if mine:
            sql += " AND claimed_by = ?"
            params.append(interaction.user.id)
        if unclaimed:
            sql += " AND claimed_by IS NULL"
        if user is not None:
            sql += " AND opener_id = ?"
            params.append(user.id)
        sql += " ORDER BY priority DESC, created_at ASC LIMIT 25"
        rows = await self.bot.db.all(sql, params)
        if not rows:
            return await utils.reply(interaction, self.bot.t(gid, "tickets_none"))
        lines = []
        for r in rows:
            claimed = f"<@{r['claimed_by']}>" if r["claimed_by"] else "—"
            lines.append(f"{utils.PRIORITY_EMOJI[r['priority']]} **#{r['number']}** <#{r['channel_id']}> · <@{r['opener_id']}> · "
                         f"{self.bot.t(gid, 'f_claimed_by')}: {claimed} · {utils.ts(r['created_at'])}")
        e = self.bot.embed(gid, title=self.bot.t(gid, "tickets_list_title", count=len(rows)), description="\n".join(lines))
        await utils.reply(interaction, embed=e)

    @app_commands.command(name="transcript", description="Получить сохранённый транскрипт тикета")
    @app_commands.guild_only()
    @app_commands.describe(number="Номер тикета")
    @support_only()
    async def transcript_cmd(self, interaction: discord.Interaction, number: int) -> None:
        from .. import transcript as tr
        import io

        gid = interaction.guild_id
        ticket = await self.svc.by_number(gid, number)
        if ticket is None:
            return await utils.reply(interaction, self.bot.t(gid, "err_ticket_not_found"))
        row = await self.bot.db.one("SELECT html FROM transcripts WHERE ticket_id = ?", (ticket["id"],))
        text = tr.unpack(row["html"]) if row else None
        if not text:
            return await utils.reply(interaction, self.bot.t(gid, "err_no_transcript"))
        file = discord.File(io.BytesIO(text.encode("utf-8")), filename=f"transcript-{number}.html")
        await utils.reply(interaction, self.bot.t(gid, "transcript_sent", number=number), file=file)

    @app_commands.command(name="on-call", description="Вкл/выкл дежурство (авто-добавление в новые тикеты)")
    @app_commands.guild_only()
    @support_only()
    async def oncall_cmd(self, interaction: discord.Interaction) -> None:
        gid, uid = interaction.guild_id, interaction.user.id
        removed = await self.bot.db.update("DELETE FROM oncall WHERE guild_id = ? AND user_id = ?", (gid, uid))
        if removed:
            return await utils.reply(interaction, self.bot.t(gid, "oncall_off"))
        await self.bot.db.execute("INSERT OR IGNORE INTO oncall(guild_id, user_id) VALUES(?, ?)", (gid, uid))
        await utils.reply(interaction, self.bot.t(gid, "oncall_on"))

    # ------------------------------------------------------------------ контекстные меню
    @app_commands.guild_only()
    async def menu_ticket_for_user(self, interaction: discord.Interaction, member: discord.Member) -> None:
        gid = interaction.guild_id
        if not await self.bot.is_support(interaction.user):
            return await utils.reply(interaction, self.bot.t(gid, "err_not_support"))
        await self._open_for(interaction, member, None, None)

    @app_commands.guild_only()
    async def menu_ticket_from_message(self, interaction: discord.Interaction, message: discord.Message) -> None:
        gid = interaction.guild_id
        if not await self.bot.is_support(interaction.user):
            return await utils.reply(interaction, self.bot.t(gid, "err_not_support"))
        author = message.author if isinstance(message.author, discord.Member) else interaction.guild.get_member(message.author.id)
        if author is None or author.bot:
            return await utils.reply(interaction, self.bot.t(gid, "err_generic"))
        await self._open_for(interaction, author, utils.trunc(message.content, 100) or None, message)

    async def _open_for(self, interaction, member, subject, quote) -> None:
        gid = interaction.guild_id
        panels = await self.svc.guild_panels(gid, enabled_only=True)
        if not panels:
            return await utils.reply(interaction, self.bot.t(gid, "err_no_panels"))
        if len(panels) == 1:
            return await self.svc.start(interaction, panels[0]["id"], target=member, subject=subject, quote=quote)
        await utils.reply(interaction, self.bot.t(gid, "pick_panel"),
                          view=PanelPicker(panels, target=member, subject=subject, quote=quote))

    @app_commands.guild_only()
    async def menu_pin(self, interaction: discord.Interaction, message: discord.Message) -> None:
        gid = interaction.guild_id
        ticket = await self.svc.by_channel(interaction.channel_id)
        if ticket is None or ticket["status"] != "open":
            return await utils.reply(interaction, self.bot.t(gid, "err_not_ticket"))
        extra = await self.bot.db.val("SELECT 1 FROM ticket_users WHERE ticket_id = ? AND user_id = ?",
                                      (ticket["id"], interaction.user.id), 0)
        if not (interaction.user.id == ticket["opener_id"] or extra or await self.svc.can_manage(interaction.user, ticket)):
            return await utils.reply(interaction, self.bot.t(gid, "err_cannot_close"))
        try:
            await message.pin(reason=f"Pinned by {interaction.user}")
        except discord.HTTPException:
            return await utils.reply(interaction, self.bot.t(gid, "err_generic"))
        await utils.reply(interaction, self.bot.t(gid, "pinned_ok"))

    # ------------------------------------------------------------------ слушатели событий
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        ticket_id = self.bot.open_channels.get(message.channel.id)
        if ticket_id is None:
            return
        ticket = await self.svc.by_id(ticket_id)
        if ticket is None or ticket["status"] != "open":
            return
        db = self.bot.db
        await db.execute(
            "INSERT INTO ticket_msgs(ticket_id, user_id, count) VALUES(?, ?, 1) "
            "ON CONFLICT(ticket_id, user_id) DO UPDATE SET count = count + 1", (ticket_id, message.author.id))
        await db.update("UPDATE tickets SET last_activity_at = ?, warned = 0 WHERE id = ?", (utils.now(), ticket_id))
        gid = message.guild.id
        if message.author.id == ticket["opener_id"] and ticket["close_at"]:
            await db.update("UPDATE tickets SET close_at = NULL WHERE id = ?", (ticket_id,))
            try:
                await message.channel.send(embed=self.bot.embed(gid, footer=False, description=self.bot.t(gid, "close_cancelled")))
            except discord.HTTPException:
                pass
        if ticket["first_response_at"] is None and message.author.id != ticket["opener_id"]:
            if await self.svc.can_manage(message.author, ticket):
                await db.update("UPDATE tickets SET first_response_at = ? WHERE id = ? AND first_response_at IS NULL",
                                (utils.now(), ticket_id))

    async def _mark_deleted(self, channel_id: int) -> None:
        ticket_id = self.bot.open_channels.pop(channel_id, None)
        if ticket_id is None:
            return
        me = self.bot.user.id if self.bot.user else 0
        await self.bot.db.update(
            "UPDATE tickets SET status = 'closed', closed_at = ?, closed_by = ?, close_reason = ? WHERE id = ? AND status = 'open'",
            (utils.now(), me, "channel deleted", ticket_id))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel) -> None:
        await self._mark_deleted(channel.id)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        await self._mark_deleted(thread.id)

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread) -> None:
        # Premium keep-alive: не даём открытым тикетам-тредам автоархивироваться
        gid = after.guild.id
        if (after.archived and not before.archived and after.id in self.bot.open_channels
                and self.bot.is_premium(gid) and self.bot.get(gid, "keepalive")):
            try:
                await after.edit(archived=False)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        gid = member.guild.id
        if not self.bot.get(gid, "close_on_leave"):
            return
        rows = await self.bot.db.all("SELECT * FROM tickets WHERE guild_id = ? AND opener_id = ? AND status = 'open'",
                                     (gid, member.id))
        for ticket in rows:
            await self.svc.close(ticket, closer=None, reason=self.bot.t(gid, "reason_left"))


async def setup(bot) -> None:
    await bot.add_cog(Tickets(bot))
