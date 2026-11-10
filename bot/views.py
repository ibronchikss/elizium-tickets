from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord

from . import utils

if TYPE_CHECKING:  # pragma: no cover
    from .core import TicketBot

log = logging.getLogger("ticketbot.views")

BUTTON_STYLES = {
    "blurple": discord.ButtonStyle.primary,
    "gray": discord.ButtonStyle.secondary,
    "green": discord.ButtonStyle.success,
    "red": discord.ButtonStyle.danger,
}


# ====================================================================== панели
class OpenButton(discord.ui.DynamicItem[discord.ui.Button], template=r"tk:open:(?P<id>[0-9]+)"):
    """Кнопка «Открыть тикет» — переживает перезапуск бота, настройки берёт из БД."""

    def __init__(self, panel_id: int, label: Optional[str] = None, style: str = "blurple", emoji: Optional[str] = None):
        if not label and not emoji:
            label = "Open ticket"
        super().__init__(discord.ui.Button(label=label, style=BUTTON_STYLES.get(style, discord.ButtonStyle.primary),
                                           emoji=emoji or None, custom_id=f"tk:open:{panel_id}"))
        self.panel_id = panel_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.client.tickets.start(interaction, self.panel_id)


class MultiSelect(discord.ui.DynamicItem[discord.ui.Select], template=r"tk:msel:(?P<id>[0-9]+)"):
    """Выпадающий список мульти-панели."""

    def __init__(self, multi_id: int, placeholder: Optional[str] = None, options: Optional[list[discord.SelectOption]] = None):
        super().__init__(discord.ui.Select(custom_id=f"tk:msel:{multi_id}", placeholder=placeholder or "Select…",
                                           options=options or [discord.SelectOption(label="—", value="0")]))
        self.multi_id = multi_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        values = (interaction.data or {}).get("values") or []
        if not values or not str(values[0]).isdigit():
            return await interaction.response.defer()
        await interaction.client.tickets.start(interaction, int(values[0]))
        try:  # сбросить выбор в списке, чтобы можно было выбрать тот же пункт повторно
            if interaction.message is not None:
                await interaction.message.edit(view=self.view)
        except discord.HTTPException:
            pass


def build_panel_view(panel: dict) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(OpenButton(panel["id"], panel["button_label"], panel["button_style"], panel["button_emoji"]))
    return view


def build_multipanel_view(multi: dict, panels: list[dict]) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    if multi["style"] == "select":
        options = []
        for p in panels[:25]:
            options.append(discord.SelectOption(label=utils.trunc(p["button_label"] or p["name"], 100), value=str(p["id"]),
                                                emoji=p["button_emoji"] or None,
                                                description=utils.trunc(p["description"], 100) if p["description"] else None))
        if options:
            view.add_item(MultiSelect(multi["id"], multi["placeholder"], options))
    else:
        for p in panels[:25]:
            view.add_item(OpenButton(p["id"], p["button_label"] or p["name"], p["button_style"], p["button_emoji"]))
    return view


class PanelPicker(discord.ui.View):
    """Эфемерный выбор панели (для /open и контекстных меню)."""

    def __init__(self, panels: list[dict], *, target: Optional[discord.Member] = None, subject: Optional[str] = None,
                 quote: Optional[discord.Message] = None):
        super().__init__(timeout=120)
        self.target, self.subject, self.quote = target, subject, quote
        select = discord.ui.Select(placeholder="…", options=[
            discord.SelectOption(label=utils.trunc(p["button_label"] or p["name"], 100), value=str(p["id"]),
                                 emoji=p["button_emoji"] or None) for p in panels[:25]])
        select.callback = self._picked
        self.select = select
        self.add_item(select)

    async def _picked(self, interaction: discord.Interaction) -> None:
        await interaction.client.tickets.start(interaction, int(self.select.values[0]), target=self.target,
                                               subject=self.subject, quote=self.quote)


# ====================================================================== управление тикетом
class TicketControls(discord.ui.View):
    """Постоянные кнопки в приветственном сообщении тикета."""

    def __init__(self, close_label: str = "Close", claim_label: str = "Claim"):
        super().__init__(timeout=None)
        self.close_btn.label = close_label
        self.claim_btn.label = claim_label

    @classmethod
    def build(cls, bot: "TicketBot", guild_id: Optional[int]) -> "TicketControls":
        return cls(bot.t(guild_id, "btn_close"), bot.t(guild_id, "btn_claim"))

    @discord.ui.button(label="Close", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="tk:close")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.client.tickets.close_prompt(interaction)

    @discord.ui.button(label="Claim", emoji="🙋", style=discord.ButtonStyle.success, custom_id="tk:claim")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.client.tickets.claim_interaction(interaction)


class ConfirmClose(discord.ui.View):
    def __init__(self, bot: "TicketBot", ticket_id: int, guild_id: Optional[int]):
        super().__init__(timeout=60)
        self.bot, self.ticket_id = bot, ticket_id
        self.confirm.label = bot.t(guild_id, "btn_confirm")
        self.cancel.label = bot.t(guild_id, "btn_cancel")

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="🔒")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await self.bot.tickets.by_id(self.ticket_id)
        if ticket is None or ticket["status"] != "open":
            return await interaction.response.edit_message(content=self.bot.t(interaction.guild_id, "err_not_ticket"), view=None)
        await interaction.response.edit_message(content=self.bot.t(interaction.guild_id, "closing"), view=None)
        await self.bot.tickets.close(ticket, closer=interaction.user)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=self.bot.t(interaction.guild_id, "cancelled"), view=None)


class CloseRequestView(discord.ui.View):
    """Запрос на закрытие: подтвердить/отклонить может автор тикета."""

    def __init__(self, approve_label: str = "Close ticket", deny_label: str = "Keep open"):
        super().__init__(timeout=None)
        self.approve.label = approve_label
        self.deny.label = deny_label

    @classmethod
    def build(cls, bot: "TicketBot", guild_id: Optional[int]) -> "CloseRequestView":
        return cls(bot.t(guild_id, "btn_cr_approve"), bot.t(guild_id, "btn_cr_deny"))

    async def _ticket(self, interaction: discord.Interaction) -> Optional[dict]:
        bot = interaction.client
        ticket = await bot.tickets.by_channel(interaction.channel_id)
        if ticket is None or ticket["status"] != "open":
            await utils.reply(interaction, bot.t(interaction.guild_id, "err_not_ticket"))
            return None
        if interaction.user.id != ticket["opener_id"] and not await bot.tickets.can_manage(interaction.user, ticket):
            await utils.reply(interaction, bot.t(interaction.guild_id, "err_only_opener"))
            return None
        return ticket

    @discord.ui.button(label="Close ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="tk:cr:yes")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await self._ticket(interaction)
        if ticket is None:
            return
        await interaction.response.edit_message(view=None)
        reason = ticket["close_request_reason"]
        await interaction.client.tickets.close(ticket, closer=interaction.user, reason=reason)

    @discord.ui.button(label="Keep open", style=discord.ButtonStyle.secondary, emoji="✖️", custom_id="tk:cr:no")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await self._ticket(interaction)
        if ticket is None:
            return
        bot = interaction.client
        await bot.db.update("UPDATE tickets SET close_at = NULL WHERE id = ?", (ticket["id"],))
        await interaction.response.edit_message(view=None)
        await interaction.followup.send(bot.t(interaction.guild_id, "close_denied", user=interaction.user.mention))


# ====================================================================== формы
class FormFlow:
    """Состояние заполнения формы (вопросы разбиты по 5 на шаг)."""

    def __init__(self, panel: dict, opener: discord.Member, chunks: list[list[dict]]):
        self.panel, self.opener, self.chunks = panel, opener, chunks
        self.answers: list[tuple[str, str]] = []
        self.step = 0


class FormModal(discord.ui.Modal):
    def __init__(self, bot: "TicketBot", flow: FormFlow):
        total = len(flow.chunks)
        title = flow.panel["title"] or flow.panel["name"]
        if total > 1:
            title = f"{utils.trunc(title, 36)} ({flow.step + 1}/{total})"
        super().__init__(title=utils.trunc(title, 45), timeout=900)
        self.bot, self.flow = bot, flow
        self.inputs: list[discord.ui.TextInput] = []
        for q in flow.chunks[flow.step]:
            paragraph = q["style"] == "paragraph"
            ti = discord.ui.TextInput(
                label=utils.trunc(q["label"], 45),
                style=discord.TextStyle.paragraph if paragraph else discord.TextStyle.short,
                placeholder=utils.trunc(q["placeholder"], 100) if q["placeholder"] else None,
                required=bool(q["required"]),
                min_length=q["min_length"] or None,
                max_length=q["max_length"] or None,
            )
            self.inputs.append(ti)
            self.add_item(ti)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        flow = self.flow
        for q, ti in zip(flow.chunks[flow.step], self.inputs):
            flow.answers.append((q["label"], ti.value))
        flow.step += 1
        gid = interaction.guild_id
        if flow.step < len(flow.chunks):
            await interaction.response.send_message(
                self.bot.t(gid, "form_next", step=flow.step + 1, total=len(flow.chunks)),
                view=NextStepView(self.bot, flow, gid), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.bot.tickets.finish(interaction, flow.panel, flow.opener, flow.answers, None)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.exception("Ошибка в форме тикета", exc_info=error)
        try:
            await utils.reply(interaction, self.bot.t(interaction.guild_id, "err_generic"))
        except discord.HTTPException:
            pass


class NextStepView(discord.ui.View):
    def __init__(self, bot: "TicketBot", flow: FormFlow, guild_id: Optional[int]):
        super().__init__(timeout=600)
        self.bot, self.flow = bot, flow
        self.next.label = bot.t(guild_id, "btn_continue")

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary, emoji="➡️")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.flow.step >= len(self.flow.chunks):
            return await interaction.response.defer()
        await interaction.response.send_modal(FormModal(self.bot, self.flow))


# ====================================================================== оценка после закрытия
class RateButton(discord.ui.DynamicItem[discord.ui.Button], template=r"tk:rate:(?P<tid>[0-9]+):(?P<n>[1-5])"):
    def __init__(self, ticket_id: int, n: int):
        super().__init__(discord.ui.Button(label=str(n), emoji="⭐", style=discord.ButtonStyle.secondary,
                                           custom_id=f"tk:rate:{ticket_id}:{n}"))
        self.ticket_id, self.n = ticket_id, n

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(int(match["tid"]), int(match["n"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        bot = interaction.client
        ticket = await bot.tickets.by_id(self.ticket_id)
        if ticket is None or ticket["opener_id"] != interaction.user.id:
            return await interaction.response.defer()
        gid = ticket["guild_id"]
        changed = await bot.db.update("UPDATE tickets SET rating = ? WHERE id = ? AND rating IS NULL", (self.n, self.ticket_id))
        if not changed:
            return await interaction.response.send_message(bot.t(gid, "survey_already"), ephemeral=True)
        view = discord.ui.View(timeout=None)
        view.add_item(CommentButton(self.ticket_id, bot.t(gid, "btn_comment")))
        e = bot.embed(gid, title=bot.t(gid, "survey_thanks"), description="⭐" * self.n)
        await interaction.response.edit_message(embed=e, view=view)
        guild = bot.get_guild(gid)
        log_id = bot.get(gid, "log_channel_id")
        if guild is not None and log_id and (ch := guild.get_channel(log_id)) is not None:
            le = bot.embed(gid, title=bot.t(gid, "log_rating_title", number=ticket["number"]),
                           description=f"<@{ticket['opener_id']}>: {'⭐' * self.n} ({self.n}/5)", color=0xFEE75C)
            try:
                await ch.send(embed=le)
            except discord.HTTPException:
                pass


class CommentButton(discord.ui.DynamicItem[discord.ui.Button], template=r"tk:cmt:(?P<tid>[0-9]+)"):
    def __init__(self, ticket_id: int, label: str = "Leave a comment"):
        super().__init__(discord.ui.Button(label=label, emoji="💬", style=discord.ButtonStyle.primary,
                                           custom_id=f"tk:cmt:{ticket_id}"))
        self.ticket_id = ticket_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(int(match["tid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket = await interaction.client.tickets.by_id(self.ticket_id)
        if ticket is None or ticket["opener_id"] != interaction.user.id:
            return await interaction.response.defer()
        await interaction.response.send_modal(CommentModal(interaction.client, ticket))


class CommentModal(discord.ui.Modal):
    def __init__(self, bot: "TicketBot", ticket: dict):
        gid = ticket["guild_id"]
        super().__init__(title=utils.trunc(bot.t(gid, "survey_comment_title"), 45), timeout=600)
        self.bot, self.ticket = bot, ticket
        self.text = discord.ui.TextInput(label=utils.trunc(bot.t(gid, "survey_comment_label"), 45),
                                         style=discord.TextStyle.paragraph, required=True, max_length=1000)
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        gid = self.ticket["guild_id"]
        await self.bot.db.update("UPDATE tickets SET rating_comment = ? WHERE id = ?", (self.text.value, self.ticket["id"]))
        await interaction.response.send_message(self.bot.t(gid, "survey_comment_thanks"), ephemeral=True)
        guild = self.bot.get_guild(gid)
        log_id = self.bot.get(gid, "log_channel_id")
        if guild is not None and log_id and (ch := guild.get_channel(log_id)) is not None:
            e = self.bot.embed(gid, title=self.bot.t(gid, "log_comment_title", number=self.ticket["number"]),
                               description=utils.trunc(self.text.value, 1500), color=0xFEE75C)
            try:
                await ch.send(embed=e)
            except discord.HTTPException:
                pass


def survey_view(ticket_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for n in range(1, 6):
        view.add_item(RateButton(ticket_id, n))
    return view


# ====================================================================== регистрация
def register(bot: "TicketBot") -> None:
    bot.add_dynamic_items(OpenButton, MultiSelect, RateButton, CommentButton)
    bot.add_view(TicketControls())
    bot.add_view(CloseRequestView())
