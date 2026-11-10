from __future__ import annotations

import json
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import ac, utils
from ..core import admin_only, premium_only
from ..views import build_multipanel_view, build_panel_view

log = logging.getLogger("ticketbot.cog.panels")

COLOR_CHOICES = [
    app_commands.Choice(name="Blurple / синий", value="blurple"),
    app_commands.Choice(name="Gray / серый", value="gray"),
    app_commands.Choice(name="Green / зелёный", value="green"),
    app_commands.Choice(name="Red / красный", value="red"),
]
STYLE_CHOICES = [
    app_commands.Choice(name="Short / короткий", value="short"),
    app_commands.Choice(name="Paragraph / абзац", value="paragraph"),
]
PRIO_CHOICES = [
    app_commands.Choice(name="low / низкий", value=0),
    app_commands.Choice(name="normal / обычный", value=1),
    app_commands.Choice(name="high / высокий", value=2),
    app_commands.Choice(name="urgent / срочный", value=3),
]


def _clear(value: Optional[str]) -> Optional[str]:
    """'-' означает «очистить поле»."""
    return None if value is not None and value.strip() == "-" else value


class Panels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.svc = bot.tickets

    # ================================================================== публикация
    def panel_embed(self, guild_id: int, panel: dict) -> discord.Embed:
        e = self.bot.embed(guild_id, title=panel["title"] or panel["name"],
                           description=panel["description"] or self.bot.t(guild_id, "panel_default_desc"),
                           color=panel["color"])
        if panel["image_url"]:
            e.set_image(url=panel["image_url"])
        if panel["thumbnail_url"]:
            e.set_thumbnail(url=panel["thumbnail_url"])
        return e

    async def publish_panel(self, guild: discord.Guild, panel: dict, channel: Optional[discord.TextChannel] = None) -> discord.Message:
        channel = channel or guild.get_channel(panel["channel_id"] or 0)
        if not isinstance(channel, discord.TextChannel):
            raise ValueError("no channel")
        embed, view = self.panel_embed(guild.id, panel), build_panel_view(panel)
        if panel["message_id"] and panel["channel_id"] == channel.id:
            try:
                msg = await channel.fetch_message(panel["message_id"])
                await msg.edit(embed=embed, view=view)
                return msg
            except discord.NotFound:
                pass
        msg = await channel.send(embed=embed, view=view)
        await self.bot.db.update("UPDATE panels SET channel_id = ?, message_id = ? WHERE id = ?", (channel.id, msg.id, panel["id"]))
        return msg

    async def refresh_panel(self, guild: discord.Guild, panel_id: int) -> None:
        """Обновить уже опубликованное сообщение панели (и мульти-панели с ней)."""
        panel = await self.svc.panel(panel_id)
        if panel and panel["message_id"]:
            try:
                await self.publish_panel(guild, panel)
            except (ValueError, discord.HTTPException):
                pass
        for multi in await self.bot.db.all("SELECT * FROM multipanels WHERE guild_id = ?", (guild.id,)):
            if panel_id in utils.jl(multi["panel_ids"]) and multi["message_id"]:
                try:
                    await self.publish_multi(guild, multi)
                except (ValueError, discord.HTTPException):
                    pass

    async def multi_panels(self, multi: dict) -> list[dict]:
        out = []
        for pid in utils.jl(multi["panel_ids"]):
            p = await self.svc.panel(pid)
            if p is not None:
                out.append(p)
        return out

    async def publish_multi(self, guild: discord.Guild, multi: dict, channel: Optional[discord.TextChannel] = None) -> discord.Message:
        channel = channel or guild.get_channel(multi["channel_id"] or 0)
        if not isinstance(channel, discord.TextChannel):
            raise ValueError("no channel")
        panels = await self.multi_panels(multi)
        embed = self.bot.embed(guild.id, title=multi["title"] or multi["name"],
                               description=multi["description"] or self.bot.t(guild.id, "panel_default_desc"), color=multi["color"])
        view = build_multipanel_view(multi, panels)
        if multi["message_id"] and multi["channel_id"] == channel.id:
            try:
                msg = await channel.fetch_message(multi["message_id"])
                await msg.edit(embed=embed, view=view)
                return msg
            except discord.NotFound:
                pass
        msg = await channel.send(embed=embed, view=view)
        await self.bot.db.update("UPDATE multipanels SET channel_id = ?, message_id = ? WHERE id = ?", (channel.id, msg.id, multi["id"]))
        return msg

    async def _get_panel(self, interaction: discord.Interaction, name: str) -> Optional[dict]:
        panel = await self.svc.panel_by_name(interaction.guild_id, name)
        if panel is None:
            await utils.reply(interaction, self.bot.t(interaction.guild_id, "err_panel_missing"))
        return panel

    # ================================================================== /panel
    panel = app_commands.Group(name="panel", description="Панели тикетов", guild_only=True)

    @panel.command(name="create", description="Создать панель тикетов")
    @app_commands.describe(name="Уникальное имя панели", title="Заголовок сообщения панели", description="Текст сообщения панели",
                           button_label="Текст кнопки", button_emoji="Эмодзи кнопки", button_color="Цвет кнопки",
                           category="Категория для каналов тикетов", channel="Канал, куда сразу опубликовать панель",
                           form="Форма вопросов перед открытием")
    @app_commands.choices(button_color=COLOR_CHOICES)
    @admin_only()
    async def panel_create(self, interaction: discord.Interaction, name: str, title: Optional[str] = None,
                           description: Optional[str] = None, button_label: Optional[str] = None,
                           button_emoji: Optional[str] = None, button_color: Optional[app_commands.Choice[str]] = None,
                           category: Optional[discord.CategoryChannel] = None, channel: Optional[discord.TextChannel] = None,
                           form: Optional[str] = None) -> None:
        gid = interaction.guild_id
        name = name.strip()
        if not name or len(name) > 60:
            return await utils.reply(interaction, self.bot.t(gid, "err_bad_name"))
        if await self.svc.panel_by_name(gid, name):
            return await utils.reply(interaction, self.bot.t(gid, "err_panel_exists"))
        count = await self.bot.db.val("SELECT COUNT(*) FROM panels WHERE guild_id = ?", (gid,), 0)
        if not self.bot.is_premium(gid) and count >= self.bot.cfg.free_panel_limit:
            return await utils.reply(interaction, self.bot.t(gid, "err_premium", feature=self.bot.t(
                gid, "feat_panels", n=self.bot.cfg.free_panel_limit)))
        if button_emoji and not utils.valid_emoji(button_emoji):
            return await utils.reply(interaction, self.bot.t(gid, "err_bad_emoji"))
        form_id = None
        if form:
            f = await self.bot.db.one("SELECT id FROM forms WHERE guild_id = ? AND lower(name) = lower(?)", (gid, form))
            if f is None:
                return await utils.reply(interaction, self.bot.t(gid, "err_form_missing"))
            form_id = f["id"]
        await interaction.response.defer(ephemeral=True)
        pid = await self.bot.db.execute(
            "INSERT INTO panels(guild_id, name, title, description, button_label, button_emoji, button_style, category_id, form_id) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (gid, name, title, description, button_label or self.bot.t(gid, "btn_open_default"),
             button_emoji.strip() if button_emoji else "🎫", button_color.value if button_color else "blurple",
             category.id if category else None, form_id))
        msg = self.bot.t(gid, "panel_created", name=name)
        if channel is not None:
            panel = await self.svc.panel(pid)
            try:
                sent = await self.publish_panel(interaction.guild, panel, channel)
                msg += "\n" + self.bot.t(gid, "panel_published", url=sent.jump_url)
            except discord.HTTPException:
                msg += "\n" + self.bot.t(gid, "err_forbidden")
        else:
            msg += "\n" + self.bot.t(gid, "panel_send_hint", name=name)
        await utils.reply(interaction, msg)

    @panel.command(name="edit", description="Изменить оформление панели ('-' очищает поле)")
    @app_commands.describe(panel="Панель", new_name="Новое имя", title="Заголовок", description="Описание",
                           button_label="Текст кнопки", button_emoji="Эмодзи кнопки", button_color="Цвет кнопки",
                           color="Цвет сообщения (hex, напр. #5865F2)", image="URL большой картинки",
                           thumbnail="URL миниатюры", form="Форма ('-' чтобы убрать)",
                           welcome="Приветствие в тикете ({user} {number} {panel} {staff} …)",
                           naming="Шаблон имени канала ({number} {user} {panel})")
    @app_commands.choices(button_color=COLOR_CHOICES)
    @admin_only()
    async def panel_edit(self, interaction: discord.Interaction, panel: str, new_name: Optional[str] = None,
                         title: Optional[str] = None, description: Optional[str] = None, button_label: Optional[str] = None,
                         button_emoji: Optional[str] = None, button_color: Optional[app_commands.Choice[str]] = None,
                         color: Optional[str] = None, image: Optional[str] = None, thumbnail: Optional[str] = None,
                         form: Optional[str] = None, welcome: Optional[str] = None, naming: Optional[str] = None) -> None:
        gid = interaction.guild_id
        row = await self._get_panel(interaction, panel)
        if row is None:
            return
        updates: dict = {}
        if new_name is not None:
            new_name = new_name.strip()
            other = await self.svc.panel_by_name(gid, new_name)
            if not new_name or len(new_name) > 60 or (other and other["id"] != row["id"]):
                return await utils.reply(interaction, self.bot.t(gid, "err_bad_name"))
            updates["name"] = new_name
        for key, val in (("title", title), ("description", description), ("button_label", button_label),
                         ("welcome_message", welcome), ("naming", naming)):
            if val is not None:
                updates[key] = _clear(val)
        if button_emoji is not None:
            if button_emoji.strip() == "-":
                updates["button_emoji"] = None
            elif utils.valid_emoji(button_emoji):
                updates["button_emoji"] = button_emoji.strip()
            else:
                return await utils.reply(interaction, self.bot.t(gid, "err_bad_emoji"))
        if button_color is not None:
            updates["button_style"] = button_color.value
        if color is not None:
            if color.strip() == "-":
                updates["color"] = None
            else:
                parsed = utils.parse_color(color)
                if parsed is None:
                    return await utils.reply(interaction, self.bot.t(gid, "err_bad_color"))
                updates["color"] = parsed
        for key, val in (("image_url", image), ("thumbnail_url", thumbnail)):
            if val is not None:
                val = _clear(val)
                if val is not None and not val.startswith(("http://", "https://")):
                    return await utils.reply(interaction, self.bot.t(gid, "err_bad_url"))
                updates[key] = val
        if form is not None:
            if form.strip() == "-":
                updates["form_id"] = None
            else:
                f = await self.bot.db.one("SELECT id FROM forms WHERE guild_id = ? AND lower(name) = lower(?)", (gid, form))
                if f is None:
                    return await utils.reply(interaction, self.bot.t(gid, "err_form_missing"))
                updates["form_id"] = f["id"]
        if not updates:
            return await utils.reply(interaction, self.bot.t(gid, "err_nothing_to_edit"))
        await interaction.response.defer(ephemeral=True)
        await self._apply(row["id"], updates)
        await self.refresh_panel(interaction.guild, row["id"])
        await utils.reply(interaction, self.bot.t(gid, "done"))

    async def _apply(self, panel_id: int, updates: dict) -> None:
        cols = ", ".join(f"{k} = ?" for k in updates)
        await self.bot.db.update(f"UPDATE panels SET {cols} WHERE id = ?", (*updates.values(), panel_id))

    @panel.command(name="config", description="Поведение панели: лимиты, треды, роли, часы, приоритет")
    @app_commands.describe(panel="Панель", category="Категория для каналов тикетов", ticket_limit="Лимит открытых тикетов этой панели (0 — общий)",
                           required_role="Роль, нужная для открытия", threads="Тикеты в тредах (по умолчанию — настройка сервера)",
                           enforce_hours="Открывать только в часы поддержки", role_on_open="Выдавать роль на время тикета (Premium)",
                           role_on_close="Выдавать роль после закрытия (Premium)", default_priority="Приоритет по умолчанию (Premium)",
                           enabled="Включена ли панель")
    @app_commands.choices(default_priority=PRIO_CHOICES)
    @admin_only()
    async def panel_config(self, interaction: discord.Interaction, panel: str, category: Optional[discord.CategoryChannel] = None,
                           ticket_limit: Optional[app_commands.Range[int, 0, 50]] = None, required_role: Optional[discord.Role] = None,
                           threads: Optional[bool] = None, enforce_hours: Optional[bool] = None,
                           role_on_open: Optional[discord.Role] = None, role_on_close: Optional[discord.Role] = None,
                           default_priority: Optional[app_commands.Choice[int]] = None, enabled: Optional[bool] = None) -> None:
        gid = interaction.guild_id
        row = await self._get_panel(interaction, panel)
        if row is None:
            return
        premium_fields = (role_on_open, role_on_close, default_priority)
        if any(x is not None for x in premium_fields) and not self.bot.is_premium(gid):
            return await utils.reply(interaction, self.bot.t(gid, "err_premium", feature=self.bot.t(gid, "feat_role_automation")))
        updates: dict = {}
        if category is not None:
            updates["category_id"] = category.id
        if ticket_limit is not None:
            updates["ticket_limit"] = ticket_limit or None
        if required_role is not None:
            updates["required_role_id"] = required_role.id
        if threads is not None:
            updates["use_threads"] = 1 if threads else 0
        if enforce_hours is not None:
            updates["enforce_hours"] = 1 if enforce_hours else 0
        if role_on_open is not None:
            updates["role_on_open"] = role_on_open.id
        if role_on_close is not None:
            updates["role_on_close"] = role_on_close.id
        if default_priority is not None:
            updates["default_priority"] = default_priority.value
        if enabled is not None:
            updates["enabled"] = 1 if enabled else 0
        if not updates:
            return await utils.reply(interaction, self.bot.t(gid, "err_nothing_to_edit"))
        await self._apply(row["id"], updates)
        await utils.reply(interaction, self.bot.t(gid, "done"))

    @panel.command(name="role", description="Роли панели: поддержка (доступ к тикетам) и пинг (упоминание при открытии)")
    @app_commands.describe(panel="Панель", action="Добавить или убрать", kind="Тип роли", role="Роль")
    @app_commands.choices(
        action=[app_commands.Choice(name="add / добавить", value="add"), app_commands.Choice(name="remove / убрать", value="remove")],
        kind=[app_commands.Choice(name="support / поддержка", value="support"), app_commands.Choice(name="ping / пинг", value="ping")])
    @admin_only()
    async def panel_role(self, interaction: discord.Interaction, panel: str, action: app_commands.Choice[str],
                         kind: app_commands.Choice[str], role: discord.Role) -> None:
        gid = interaction.guild_id
        row = await self._get_panel(interaction, panel)
        if row is None:
            return
        col = "support_roles" if kind.value == "support" else "ping_roles"
        roles = utils.jl(row[col])
        if action.value == "add" and role.id not in roles:
            roles.append(role.id)
        elif action.value == "remove" and role.id in roles:
            roles.remove(role.id)
        await self.bot.db.update(f"UPDATE panels SET {col} = ? WHERE id = ?", (json.dumps(roles), row["id"]))
        await utils.reply(interaction, self.bot.t(gid, "done"))

    @panel.command(name="send", description="Опубликовать (или обновить) панель в канале")
    @app_commands.describe(panel="Панель", channel="Канал (по умолчанию — прежний)")
    @admin_only()
    async def panel_send(self, interaction: discord.Interaction, panel: str, channel: Optional[discord.TextChannel] = None) -> None:
        gid = interaction.guild_id
        row = await self._get_panel(interaction, panel)
        if row is None:
            return
        target = channel or interaction.guild.get_channel(row["channel_id"] or 0)
        if not isinstance(target, discord.TextChannel):
            target = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
        if target is None:
            return await utils.reply(interaction, self.bot.t(gid, "err_need_channel"))
        await interaction.response.defer(ephemeral=True)
        try:
            msg = await self.publish_panel(interaction.guild, row, target)
        except discord.HTTPException:
            return await utils.reply(interaction, self.bot.t(gid, "err_forbidden"))
        await utils.reply(interaction, self.bot.t(gid, "panel_published", url=msg.jump_url))

    @panel.command(name="preview", description="Предпросмотр панели (только вам)")
    @app_commands.describe(panel="Панель")
    @admin_only()
    async def panel_preview(self, interaction: discord.Interaction, panel: str) -> None:
        row = await self._get_panel(interaction, panel)
        if row is None:
            return
        await utils.reply(interaction, embed=self.panel_embed(interaction.guild_id, row), view=build_panel_view(row))

    @panel.command(name="delete", description="Удалить панель")
    @app_commands.describe(panel="Панель")
    @admin_only()
    async def panel_delete(self, interaction: discord.Interaction, panel: str) -> None:
        gid = interaction.guild_id
        row = await self._get_panel(interaction, panel)
        if row is None:
            return
        await interaction.response.defer(ephemeral=True)
        if row["message_id"] and row["channel_id"]:
            ch = interaction.guild.get_channel(row["channel_id"])
            if ch is not None:
                try:
                    await (await ch.fetch_message(row["message_id"])).delete()
                except discord.HTTPException:
                    pass
        await self.bot.db.update("DELETE FROM panels WHERE id = ?", (row["id"],))
        for multi in await self.bot.db.all("SELECT * FROM multipanels WHERE guild_id = ?", (gid,)):
            ids = utils.jl(multi["panel_ids"])
            if row["id"] in ids:
                ids.remove(row["id"])
                await self.bot.db.update("UPDATE multipanels SET panel_ids = ? WHERE id = ?", (json.dumps(ids), multi["id"]))
                if multi["message_id"]:
                    try:
                        await self.publish_multi(interaction.guild, {**multi, "panel_ids": json.dumps(ids)})
                    except (ValueError, discord.HTTPException):
                        pass
        await utils.reply(interaction, self.bot.t(gid, "panel_deleted", name=row["name"]))

    @panel.command(name="list", description="Список панелей")
    @admin_only()
    async def panel_list(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        rows = await self.svc.guild_panels(gid)
        if not rows:
            return await utils.reply(interaction, self.bot.t(gid, "err_no_panels"))
        lines = []
        for r in rows:
            where = f"<#{r['channel_id']}>" if r["channel_id"] else "—"
            flags = ("✅" if r["enabled"] else "⛔") + (" 🧵" if r["use_threads"] else "") + (" 📝" if r["form_id"] else "")
            lines.append(f"{flags} **{r['name']}** → {where}")
        await utils.reply(interaction, embed=self.bot.embed(gid, title=self.bot.t(gid, "panels_title"), description="\n".join(lines)))

    @panel.command(name="show", description="Показать настройки панели")
    @app_commands.describe(panel="Панель")
    @admin_only()
    async def panel_show(self, interaction: discord.Interaction, panel: str) -> None:
        gid = interaction.guild_id
        r = await self._get_panel(interaction, panel)
        if r is None:
            return
        form = await self.bot.db.one("SELECT name FROM forms WHERE id = ?", (r["form_id"],)) if r["form_id"] else None
        yes, no = self.bot.t(gid, "yes"), self.bot.t(gid, "no")
        fmt = lambda ids, pre: " ".join(f"<{pre}{i}>" for i in ids) or "—"  # noqa: E731
        e = self.bot.embed(gid, title=f"🎫 {r['name']}")
        e.add_field(name=self.bot.t(gid, "f_channel"), value=f"<#{r['channel_id']}>" if r["channel_id"] else "—")
        e.add_field(name=self.bot.t(gid, "f_category"), value=f"<#{r['category_id']}>" if r["category_id"] else "—")
        e.add_field(name=self.bot.t(gid, "f_form"), value=form["name"] if form else "—")
        e.add_field(name=self.bot.t(gid, "f_support_roles"), value=fmt(utils.jl(r["support_roles"]), "@&"))
        e.add_field(name=self.bot.t(gid, "f_ping_roles"), value=fmt(utils.jl(r["ping_roles"]), "@&"))
        e.add_field(name=self.bot.t(gid, "f_limit"), value=str(r["ticket_limit"] or self.bot.get(gid, "ticket_limit")))
        e.add_field(name=self.bot.t(gid, "f_threads"), value="—" if r["use_threads"] is None else (yes if r["use_threads"] else no))
        e.add_field(name=self.bot.t(gid, "f_hours"), value=yes if r["enforce_hours"] else no)
        e.add_field(name=self.bot.t(gid, "f_enabled"), value=yes if r["enabled"] else no)
        e.add_field(name=self.bot.t(gid, "f_naming"), value=f"`{r['naming'] or self.bot.get(gid, 'naming')}`", inline=False)
        await utils.reply(interaction, embed=e)

    @panel_edit.autocomplete("panel")
    async def ac_edit(self, interaction: discord.Interaction, current: str):
        return await ac.panel_ac(interaction, current)

    @panel_edit.autocomplete("form")
    async def ac_edit_form(self, interaction: discord.Interaction, current: str):
        return await ac.form_ac(interaction, current)

    @panel_create.autocomplete("form")
    async def ac_create_form(self, interaction: discord.Interaction, current: str):
        return await ac.form_ac(interaction, current)

    @panel_config.autocomplete("panel")
    async def ac_config(self, interaction: discord.Interaction, current: str):
        return await ac.panel_ac(interaction, current)

    @panel_role.autocomplete("panel")
    async def ac_role(self, interaction: discord.Interaction, current: str):
        return await ac.panel_ac(interaction, current)

    @panel_send.autocomplete("panel")
    async def ac_send(self, interaction: discord.Interaction, current: str):
        return await ac.panel_ac(interaction, current)

    @panel_preview.autocomplete("panel")
    async def ac_preview(self, interaction: discord.Interaction, current: str):
        return await ac.panel_ac(interaction, current)

    @panel_delete.autocomplete("panel")
    async def ac_delete(self, interaction: discord.Interaction, current: str):
        return await ac.panel_ac(interaction, current)

    @panel_show.autocomplete("panel")
    async def ac_show(self, interaction: discord.Interaction, current: str):
        return await ac.panel_ac(interaction, current)

    # ================================================================== /multipanel (Premium)
    multipanel = app_commands.Group(name="multipanel", description="Мульти-панели: несколько панелей в одном сообщении (Premium)",
                                    guild_only=True)

    async def _get_multi(self, interaction: discord.Interaction, name: str) -> Optional[dict]:
        row = await self.bot.db.one("SELECT * FROM multipanels WHERE guild_id = ? AND lower(name) = lower(?)",
                                    (interaction.guild_id, name.strip()))
        if row is None:
            await utils.reply(interaction, self.bot.t(interaction.guild_id, "err_multi_missing"))
        return row

    @multipanel.command(name="create", description="Создать мульти-панель")
    @app_commands.describe(name="Имя мульти-панели", panels="Панели через запятую", style="Кнопки или выпадающий список",
                           title="Заголовок", description="Описание", channel="Канал для публикации")
    @app_commands.choices(style=[app_commands.Choice(name="Buttons / кнопки", value="buttons"),
                                 app_commands.Choice(name="Dropdown / список", value="select")])
    @admin_only()
    @premium_only("multi-panels")
    async def multi_create(self, interaction: discord.Interaction, name: str, panels: str,
                           style: Optional[app_commands.Choice[str]] = None, title: Optional[str] = None,
                           description: Optional[str] = None, channel: Optional[discord.TextChannel] = None) -> None:
        gid = interaction.guild_id
        name = name.strip()
        if not name or len(name) > 60:
            return await utils.reply(interaction, self.bot.t(gid, "err_bad_name"))
        if await self.bot.db.one("SELECT 1 FROM multipanels WHERE guild_id = ? AND lower(name) = lower(?)", (gid, name)):
            return await utils.reply(interaction, self.bot.t(gid, "err_panel_exists"))
        ids = []
        for part in [p.strip() for p in panels.split(",") if p.strip()]:
            p = await self.svc.panel_by_name(gid, part)
            if p is None:
                return await utils.reply(interaction, self.bot.t(gid, "err_panel_missing_named", name=part))
            if p["id"] not in ids:
                ids.append(p["id"])
        if not ids or len(ids) > 25:
            return await utils.reply(interaction, self.bot.t(gid, "err_multi_count"))
        await interaction.response.defer(ephemeral=True)
        mid = await self.bot.db.execute(
            "INSERT INTO multipanels(guild_id, name, title, description, style, panel_ids) VALUES(?,?,?,?,?,?)",
            (gid, name, title, description, style.value if style else "buttons", json.dumps(ids)))
        msg = self.bot.t(gid, "multi_created", name=name)
        if channel is not None:
            multi = await self.bot.db.one("SELECT * FROM multipanels WHERE id = ?", (mid,))
            try:
                sent = await self.publish_multi(interaction.guild, multi, channel)
                msg += "\n" + self.bot.t(gid, "panel_published", url=sent.jump_url)
            except discord.HTTPException:
                msg += "\n" + self.bot.t(gid, "err_forbidden")
        await utils.reply(interaction, msg)

    @multipanel.command(name="edit", description="Изменить оформление мульти-панели ('-' очищает поле)")
    @app_commands.describe(multipanel="Мульти-панель", title="Заголовок", description="Описание", style="Кнопки или список",
                           placeholder="Подсказка в списке", color="Цвет (hex)")
    @app_commands.choices(style=[app_commands.Choice(name="Buttons / кнопки", value="buttons"),
                                 app_commands.Choice(name="Dropdown / список", value="select")])
    @admin_only()
    @premium_only("multi-panels")
    async def multi_edit(self, interaction: discord.Interaction, multipanel: str, title: Optional[str] = None,
                         description: Optional[str] = None, style: Optional[app_commands.Choice[str]] = None,
                         placeholder: Optional[str] = None, color: Optional[str] = None) -> None:
        gid = interaction.guild_id
        multi = await self._get_multi(interaction, multipanel)
        if multi is None:
            return
        updates: dict = {}
        for key, val in (("title", title), ("description", description), ("placeholder", placeholder)):
            if val is not None:
                updates[key] = _clear(val)
        if style is not None:
            updates["style"] = style.value
        if color is not None:
            parsed = None if color.strip() == "-" else utils.parse_color(color)
            if color.strip() != "-" and parsed is None:
                return await utils.reply(interaction, self.bot.t(gid, "err_bad_color"))
            updates["color"] = parsed
        if not updates:
            return await utils.reply(interaction, self.bot.t(gid, "err_nothing_to_edit"))
        await interaction.response.defer(ephemeral=True)
        cols = ", ".join(f"{k} = ?" for k in updates)
        await self.bot.db.update(f"UPDATE multipanels SET {cols} WHERE id = ?", (*updates.values(), multi["id"]))
        multi = await self.bot.db.one("SELECT * FROM multipanels WHERE id = ?", (multi["id"],))
        if multi["message_id"]:
            try:
                await self.publish_multi(interaction.guild, multi)
            except (ValueError, discord.HTTPException):
                pass
        await utils.reply(interaction, self.bot.t(gid, "done"))

    @multipanel.command(name="add-panel", description="Добавить панель в мульти-панель")
    @app_commands.describe(multipanel="Мульти-панель", panel="Панель")
    @admin_only()
    @premium_only("multi-panels")
    async def multi_add(self, interaction: discord.Interaction, multipanel: str, panel: str) -> None:
        await self._multi_change(interaction, multipanel, panel, add=True)

    @multipanel.command(name="remove-panel", description="Убрать панель из мульти-панели")
    @app_commands.describe(multipanel="Мульти-панель", panel="Панель")
    @admin_only()
    @premium_only("multi-panels")
    async def multi_remove(self, interaction: discord.Interaction, multipanel: str, panel: str) -> None:
        await self._multi_change(interaction, multipanel, panel, add=False)

    async def _multi_change(self, interaction, multipanel: str, panel: str, *, add: bool) -> None:
        gid = interaction.guild_id
        multi = await self._get_multi(interaction, multipanel)
        if multi is None:
            return
        p = await self._get_panel(interaction, panel)
        if p is None:
            return
        ids = utils.jl(multi["panel_ids"])
        if add and p["id"] not in ids:
            if len(ids) >= 25:
                return await utils.reply(interaction, self.bot.t(gid, "err_multi_count"))
            ids.append(p["id"])
        elif not add and p["id"] in ids:
            ids.remove(p["id"])
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.update("UPDATE multipanels SET panel_ids = ? WHERE id = ?", (json.dumps(ids), multi["id"]))
        if multi["message_id"]:
            try:
                await self.publish_multi(interaction.guild, {**multi, "panel_ids": json.dumps(ids)})
            except (ValueError, discord.HTTPException):
                pass
        await utils.reply(interaction, self.bot.t(gid, "done"))

    @multipanel.command(name="send", description="Опубликовать (или обновить) мульти-панель")
    @app_commands.describe(multipanel="Мульти-панель", channel="Канал")
    @admin_only()
    @premium_only("multi-panels")
    async def multi_send(self, interaction: discord.Interaction, multipanel: str, channel: Optional[discord.TextChannel] = None) -> None:
        gid = interaction.guild_id
        multi = await self._get_multi(interaction, multipanel)
        if multi is None:
            return
        target = channel or interaction.guild.get_channel(multi["channel_id"] or 0)
        if not isinstance(target, discord.TextChannel):
            target = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
        if target is None:
            return await utils.reply(interaction, self.bot.t(gid, "err_need_channel"))
        await interaction.response.defer(ephemeral=True)
        try:
            msg = await self.publish_multi(interaction.guild, multi, target)
        except discord.HTTPException:
            return await utils.reply(interaction, self.bot.t(gid, "err_forbidden"))
        await utils.reply(interaction, self.bot.t(gid, "panel_published", url=msg.jump_url))

    @multipanel.command(name="delete", description="Удалить мульти-панель")
    @app_commands.describe(multipanel="Мульти-панель")
    @admin_only()
    async def multi_delete(self, interaction: discord.Interaction, multipanel: str) -> None:
        gid = interaction.guild_id
        multi = await self._get_multi(interaction, multipanel)
        if multi is None:
            return
        await interaction.response.defer(ephemeral=True)
        if multi["message_id"] and multi["channel_id"]:
            ch = interaction.guild.get_channel(multi["channel_id"])
            if ch is not None:
                try:
                    await (await ch.fetch_message(multi["message_id"])).delete()
                except discord.HTTPException:
                    pass
        await self.bot.db.update("DELETE FROM multipanels WHERE id = ?", (multi["id"],))
        await utils.reply(interaction, self.bot.t(gid, "panel_deleted", name=multi["name"]))

    @multipanel.command(name="list", description="Список мульти-панелей")
    @admin_only()
    async def multi_list(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        rows = await self.bot.db.all("SELECT * FROM multipanels WHERE guild_id = ? ORDER BY id", (gid,))
        if not rows:
            return await utils.reply(interaction, self.bot.t(gid, "err_no_multis"))
        lines = []
        for r in rows:
            names = []
            for pid in utils.jl(r["panel_ids"]):
                p = await self.svc.panel(pid)
                if p:
                    names.append(p["name"])
            where = f"<#{r['channel_id']}>" if r["channel_id"] else "—"
            lines.append(f"**{r['name']}** ({r['style']}) → {where}\n└ {', '.join(names) or '—'}")
        await utils.reply(interaction, embed=self.bot.embed(gid, title=self.bot.t(gid, "multis_title"), description="\n".join(lines)))

    @multi_edit.autocomplete("multipanel")
    async def ac_m_edit(self, interaction: discord.Interaction, current: str):
        return await ac.multipanel_ac(interaction, current)

    @multi_add.autocomplete("multipanel")
    async def ac_m_add(self, interaction: discord.Interaction, current: str):
        return await ac.multipanel_ac(interaction, current)

    @multi_add.autocomplete("panel")
    async def ac_m_add_p(self, interaction: discord.Interaction, current: str):
        return await ac.panel_ac(interaction, current)

    @multi_remove.autocomplete("multipanel")
    async def ac_m_rem(self, interaction: discord.Interaction, current: str):
        return await ac.multipanel_ac(interaction, current)

    @multi_remove.autocomplete("panel")
    async def ac_m_rem_p(self, interaction: discord.Interaction, current: str):
        return await ac.panel_ac(interaction, current)

    @multi_send.autocomplete("multipanel")
    async def ac_m_send(self, interaction: discord.Interaction, current: str):
        return await ac.multipanel_ac(interaction, current)

    @multi_delete.autocomplete("multipanel")
    async def ac_m_del(self, interaction: discord.Interaction, current: str):
        return await ac.multipanel_ac(interaction, current)

    # ================================================================== /form
    form = app_commands.Group(name="form", description="Формы с вопросами перед открытием тикета", guild_only=True)

    async def _get_form(self, interaction: discord.Interaction, name: str) -> Optional[dict]:
        row = await self.bot.db.one("SELECT * FROM forms WHERE guild_id = ? AND lower(name) = lower(?)",
                                    (interaction.guild_id, name.strip()))
        if row is None:
            await utils.reply(interaction, self.bot.t(interaction.guild_id, "err_form_missing"))
        return row

    @form.command(name="create", description="Создать пустую форму")
    @app_commands.describe(name="Имя формы")
    @admin_only()
    async def form_create(self, interaction: discord.Interaction, name: str) -> None:
        gid = interaction.guild_id
        name = name.strip()
        if not name or len(name) > 60:
            return await utils.reply(interaction, self.bot.t(gid, "err_bad_name"))
        if await self.bot.db.one("SELECT 1 FROM forms WHERE guild_id = ? AND lower(name) = lower(?)", (gid, name)):
            return await utils.reply(interaction, self.bot.t(gid, "err_form_exists"))
        await self.bot.db.execute("INSERT INTO forms(guild_id, name) VALUES(?, ?)", (gid, name))
        await utils.reply(interaction, self.bot.t(gid, "form_created", name=name))

    @form.command(name="add-question", description="Добавить вопрос в форму")
    @app_commands.describe(form="Форма", label="Текст вопроса (до 45 символов)", style="Короткий ответ или абзац",
                           placeholder="Подсказка в поле", required="Обязательный ответ", min_length="Мин. длина",
                           max_length="Макс. длина")
    @app_commands.choices(style=STYLE_CHOICES)
    @admin_only()
    async def form_add_question(self, interaction: discord.Interaction, form: str, label: app_commands.Range[str, 1, 45],
                                style: Optional[app_commands.Choice[str]] = None, placeholder: Optional[str] = None,
                                required: bool = True, min_length: Optional[app_commands.Range[int, 0, 4000]] = None,
                                max_length: Optional[app_commands.Range[int, 1, 4000]] = None) -> None:
        gid = interaction.guild_id
        row = await self._get_form(interaction, form)
        if row is None:
            return
        count = await self.bot.db.val("SELECT COUNT(*) FROM form_questions WHERE form_id = ?", (row["id"],), 0)
        if count >= 25:
            return await utils.reply(interaction, self.bot.t(gid, "err_form_full"))
        if count >= self.bot.cfg.free_form_questions and not self.bot.is_premium(gid):
            return await utils.reply(interaction, self.bot.t(gid, "err_premium", feature=self.bot.t(
                gid, "feat_multistep", n=self.bot.cfg.free_form_questions)))
        if min_length and max_length and min_length > max_length:
            return await utils.reply(interaction, self.bot.t(gid, "err_bad_length"))
        await self.bot.db.execute(
            "INSERT INTO form_questions(form_id, position, label, style, placeholder, required, min_length, max_length) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (row["id"], count + 1, label, style.value if style else "short", placeholder, 1 if required else 0,
             min_length or None, max_length or None))
        await utils.reply(interaction, self.bot.t(gid, "question_added", n=count + 1, steps=(count // 5) + 1))

    @form.command(name="remove-question", description="Удалить вопрос по номеру")
    @app_commands.describe(form="Форма", number="Номер вопроса (см. /form show)")
    @admin_only()
    async def form_remove_question(self, interaction: discord.Interaction, form: str, number: app_commands.Range[int, 1, 25]) -> None:
        gid = interaction.guild_id
        row = await self._get_form(interaction, form)
        if row is None:
            return
        questions = await self.svc.questions(row["id"])
        if number > len(questions):
            return await utils.reply(interaction, self.bot.t(gid, "err_question_missing"))
        await self.bot.db.update("DELETE FROM form_questions WHERE id = ?", (questions[number - 1]["id"],))
        rest = [q["id"] for i, q in enumerate(questions) if i != number - 1]
        await self.bot.db.many("UPDATE form_questions SET position = ? WHERE id = ?", [(i + 1, qid) for i, qid in enumerate(rest)])
        await utils.reply(interaction, self.bot.t(gid, "done"))

    @form.command(name="show", description="Показать вопросы формы")
    @app_commands.describe(form="Форма")
    @admin_only()
    async def form_show(self, interaction: discord.Interaction, form: str) -> None:
        gid = interaction.guild_id
        row = await self._get_form(interaction, form)
        if row is None:
            return
        questions = await self.svc.questions(row["id"])
        if not questions:
            return await utils.reply(interaction, self.bot.t(gid, "form_empty"))
        lines = [f"**{i}.** {q['label']} — `{q['style']}`{'' if q['required'] else ' (' + self.bot.t(gid, 'optional') + ')'}"
                 for i, q in enumerate(questions, 1)]
        await utils.reply(interaction, embed=self.bot.embed(gid, title=f"📝 {row['name']}", description="\n".join(lines)))

    @form.command(name="list", description="Список форм")
    @admin_only()
    async def form_list(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        rows = await self.bot.db.all(
            "SELECT f.name, (SELECT COUNT(*) FROM form_questions q WHERE q.form_id = f.id) AS n FROM forms f "
            "WHERE f.guild_id = ? ORDER BY f.id", (gid,))
        if not rows:
            return await utils.reply(interaction, self.bot.t(gid, "err_no_forms"))
        await utils.reply(interaction, embed=self.bot.embed(
            gid, title=self.bot.t(gid, "forms_title"), description="\n".join(f"📝 **{r['name']}** — {r['n']}" for r in rows)))

    @form.command(name="delete", description="Удалить форму")
    @app_commands.describe(form="Форма")
    @admin_only()
    async def form_delete(self, interaction: discord.Interaction, form: str) -> None:
        row = await self._get_form(interaction, form)
        if row is None:
            return
        await self.bot.db.update("DELETE FROM forms WHERE id = ?", (row["id"],))
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "done"))

    @form_add_question.autocomplete("form")
    async def ac_f_add(self, interaction: discord.Interaction, current: str):
        return await ac.form_ac(interaction, current)

    @form_remove_question.autocomplete("form")
    async def ac_f_rem(self, interaction: discord.Interaction, current: str):
        return await ac.form_ac(interaction, current)

    @form_show.autocomplete("form")
    async def ac_f_show(self, interaction: discord.Interaction, current: str):
        return await ac.form_ac(interaction, current)

    @form_delete.autocomplete("form")
    async def ac_f_del(self, interaction: discord.Interaction, current: str):
        return await ac.form_ac(interaction, current)


async def setup(bot) -> None:
    await bot.add_cog(Panels(bot))
