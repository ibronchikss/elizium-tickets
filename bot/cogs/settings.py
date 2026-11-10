from __future__ import annotations

import logging
from typing import Optional, Union

import discord
from discord import app_commands
from discord.ext import commands

from .. import utils
from ..core import admin_only, support_only

log = logging.getLogger("ticketbot.cog.settings")

TOGGLES = {
    "use-threads": ("use_threads", False),
    "close-confirm": ("close_confirm", False),
    "delete-on-close": ("delete_on_close", False),
    "dm-transcript": ("dm_transcript", False),
    "close-on-leave": ("close_on_leave", False),
    "survey": ("survey", True),
    "keepalive": ("keepalive", True),
}
TOGGLE_CHOICES = [
    app_commands.Choice(name="use-threads — тикеты в приватных тредах", value="use-threads"),
    app_commands.Choice(name="close-confirm — подтверждение закрытия", value="close-confirm"),
    app_commands.Choice(name="delete-on-close — удалять канал после закрытия", value="delete-on-close"),
    app_commands.Choice(name="dm-transcript — отправлять транскрипт автору в ЛС", value="dm-transcript"),
    app_commands.Choice(name="close-on-leave — закрывать тикет, если автор вышел", value="close-on-leave"),
    app_commands.Choice(name="survey — оценка после закрытия (Premium)", value="survey"),
    app_commands.Choice(name="keepalive — не архивировать треды (Premium)", value="keepalive"),
]


class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.svc = bot.tickets

    # ================================================================== /setup
    setup = app_commands.Group(name="setup", description="Настройка системы тикетов", guild_only=True)

    @setup.command(name="auto", description="Автонастройка: категория, лог-канал и первая панель")
    @admin_only()
    async def setup_auto(self, interaction: discord.Interaction) -> None:
        guild, gid = interaction.guild, interaction.guild_id
        await interaction.response.defer(ephemeral=True)
        try:
            category = guild.get_channel(self.bot.get(gid, "category_id") or 0)
            if not isinstance(category, discord.CategoryChannel):
                category = await guild.create_category("Tickets", reason="/setup auto")
                await self.bot.set(gid, "category_id", category.id)
            log_ch = guild.get_channel(self.bot.get(gid, "log_channel_id") or 0)
            if log_ch is None:
                log_ch = await guild.create_text_channel(
                    "ticket-logs", reason="/setup auto",
                    overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False),
                                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                                      embed_links=True, attach_files=True)})
                await self.bot.set(gid, "log_channel_id", log_ch.id)
            open_ch = await guild.create_text_channel(
                "open-a-ticket", reason="/setup auto",
                overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False,
                                                                            add_reactions=False),
                            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True)})
        except discord.HTTPException:
            return await utils.reply(interaction, self.bot.t(gid, "err_forbidden"))

        panel = await self.svc.panel_by_name(gid, "support")
        link = ""
        count = await self.bot.db.val("SELECT COUNT(*) FROM panels WHERE guild_id = ?", (gid,), 0)
        if panel is None and (self.bot.is_premium(gid) or count < self.bot.cfg.free_panel_limit):
            pid = await self.bot.db.execute(
                "INSERT INTO panels(guild_id, name, title, description, button_label, button_emoji, category_id) VALUES(?,?,?,?,?,?,?)",
                (gid, "support", self.bot.t(gid, "auto_panel_title"), self.bot.t(gid, "auto_panel_desc"),
                 self.bot.t(gid, "btn_open_default"), "🎫", category.id))
            panel = await self.svc.panel(pid)
        if panel is not None:
            panels_cog = self.bot.get_cog("Panels")
            try:
                sent = await panels_cog.publish_panel(guild, panel, open_ch)
                link = "\n" + self.bot.t(gid, "panel_published", url=sent.jump_url)
            except discord.HTTPException:
                pass
        await utils.reply(interaction, self.bot.t(gid, "setup_auto_done", category=category.mention, log=log_ch.mention) + link)

    @setup.command(name="limit", description="Сколько тикетов может быть открыто у одного пользователя (0 — без лимита)")
    @app_commands.describe(amount="Количество")
    @admin_only()
    async def setup_limit(self, interaction: discord.Interaction, amount: app_commands.Range[int, 0, 50]) -> None:
        await self.bot.set(interaction.guild_id, "ticket_limit", amount)
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "done"))

    @setup.command(name="toggle", description="Включить или выключить опцию")
    @app_commands.describe(option="Опция", enabled="Включена")
    @app_commands.choices(option=TOGGLE_CHOICES)
    @admin_only()
    async def setup_toggle(self, interaction: discord.Interaction, option: app_commands.Choice[str], enabled: bool) -> None:
        gid = interaction.guild_id
        key, premium = TOGGLES[option.value]
        if premium and not self.bot.is_premium(gid):
            return await utils.reply(interaction, self.bot.t(gid, "err_premium", feature=option.value))
        await self.bot.set(gid, key, bool(enabled))
        await utils.reply(interaction, self.bot.t(gid, "toggle_set", option=option.value,
                                                  state=self.bot.t(gid, "on" if enabled else "off")))

    @setup.command(name="category", description="Категория для каналов тикетов по умолчанию")
    @app_commands.describe(category="Категория (пусто — сбросить)")
    @admin_only()
    async def setup_category(self, interaction: discord.Interaction, category: Optional[discord.CategoryChannel] = None) -> None:
        await self.bot.set(interaction.guild_id, "category_id", category.id if category else None)
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "done"))

    @setup.command(name="thread-parent", description="Канал, в котором создаются треды-тикеты по умолчанию")
    @app_commands.describe(channel="Канал (пусто — сбросить)")
    @admin_only()
    async def setup_thread_parent(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        await self.bot.set(interaction.guild_id, "thread_parent_id", channel.id if channel else None)
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "done"))

    @setup.command(name="log-channel", description="Канал логов тикетов")
    @app_commands.describe(channel="Канал (пусто — сбросить)")
    @admin_only()
    async def setup_log(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        await self.bot.set(interaction.guild_id, "log_channel_id", channel.id if channel else None)
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "done"))

    @setup.command(name="transcripts-channel", description="Канал для транскриптов (по умолчанию — канал логов)")
    @app_commands.describe(channel="Канал (пусто — сбросить)")
    @admin_only()
    async def setup_transcripts(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        await self.bot.set(interaction.guild_id, "transcript_channel_id", channel.id if channel else None)
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "done"))

    @setup.command(name="naming", description="Шаблон имени тикета: {number} {user} {username} {panel}")
    @app_commands.describe(pattern="Шаблон, напр. ticket-{number} ('-' — сбросить)")
    @admin_only()
    async def setup_naming(self, interaction: discord.Interaction, pattern: app_commands.Range[str, 1, 60]) -> None:
        await self.bot.set(interaction.guild_id, "naming", None if pattern.strip() == "-" else pattern.strip())
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "done"))

    @setup.command(name="welcome", description="Приветствие в тикете: {user} {username} {number} {panel} {staff} {guild} {date}")
    @app_commands.describe(message="Текст ('-' — сбросить)")
    @admin_only()
    async def setup_welcome(self, interaction: discord.Interaction, message: app_commands.Range[str, 1, 2000]) -> None:
        await self.bot.set(interaction.guild_id, "welcome", None if message.strip() == "-" else message)
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "done"))

    @setup.command(name="autoclose", description="Автозакрытие неактивных тикетов (Premium)")
    @app_commands.describe(hours="Через сколько часов без сообщений закрывать (0 — выключить)",
                           warn_before="За сколько часов до закрытия предупредить автора")
    @admin_only()
    async def setup_autoclose(self, interaction: discord.Interaction, hours: app_commands.Range[int, 0, 720],
                              warn_before: app_commands.Range[int, 0, 168] = 0) -> None:
        gid = interaction.guild_id
        if not self.bot.is_premium(gid):
            return await utils.reply(interaction, self.bot.t(gid, "err_premium", feature="autoclose"))
        if hours and warn_before >= hours:
            return await utils.reply(interaction, self.bot.t(gid, "err_warn_gt_hours"))
        await self.bot.set(gid, "autoclose_hours", hours)
        await self.bot.set(gid, "autoclose_warn_hours", warn_before)
        await utils.reply(interaction, self.bot.t(gid, "done"))

    @setup.command(name="sla", description="SLA: уведомлять, если тикет без ответа поддержки (Premium)")
    @app_commands.describe(minutes="Целевое время первого ответа в минутах (0 — выключить)",
                           channel="Куда слать уведомления (по умолчанию — канал логов)", role="Кого упоминать")
    @admin_only()
    async def setup_sla(self, interaction: discord.Interaction, minutes: app_commands.Range[int, 0, 10080],
                        channel: Optional[discord.TextChannel] = None, role: Optional[discord.Role] = None) -> None:
        gid = interaction.guild_id
        if not self.bot.is_premium(gid):
            return await utils.reply(interaction, self.bot.t(gid, "err_premium", feature="SLA"))
        await self.bot.set(gid, "sla_minutes", minutes)
        await self.bot.set(gid, "sla_channel_id", channel.id if channel else None)
        await self.bot.set(gid, "sla_role_id", role.id if role else None)
        await utils.reply(interaction, self.bot.t(gid, "done"))

    @setup.command(name="branding", description="Свой цвет и подпись в сообщениях бота (Premium)")
    @app_commands.describe(color="Цвет hex, напр. #FF8800 ('-' — сбросить)", footer="Подпись ('-' — сбросить)")
    @admin_only()
    async def setup_branding(self, interaction: discord.Interaction, color: Optional[str] = None, footer: Optional[str] = None) -> None:
        gid = interaction.guild_id
        if not self.bot.is_premium(gid):
            return await utils.reply(interaction, self.bot.t(gid, "err_premium", feature="branding"))
        if color is None and footer is None:
            return await utils.reply(interaction, self.bot.t(gid, "err_nothing_to_edit"))
        if color is not None:
            if color.strip() == "-":
                await self.bot.set(gid, "embed_color", None)
            else:
                parsed = utils.parse_color(color)
                if parsed is None:
                    return await utils.reply(interaction, self.bot.t(gid, "err_bad_color"))
                await self.bot.set(gid, "embed_color", parsed)
        if footer is not None:
            await self.bot.set(gid, "footer", None if footer.strip() == "-" else utils.trunc(footer, 100))
        await utils.reply(interaction, self.bot.t(gid, "done"))

    # ---- часы поддержки
    @setup.command(name="hours-add", description="Добавить окно часов поддержки")
    @app_commands.describe(days="Дни: mon-fri, пн-пт, sat,sun, daily", start="Начало, напр. 09:00", end="Конец, напр. 18:00")
    @admin_only()
    async def setup_hours_add(self, interaction: discord.Interaction, days: str, start: str, end: str) -> None:
        gid = interaction.guild_id
        parsed_days, s, e = utils.parse_days(days), utils.parse_time_of_day(start), utils.parse_time_of_day(end)
        if parsed_days is None or s is None or e is None or e <= s:
            return await utils.reply(interaction, self.bot.t(gid, "err_bad_hours"))
        existing = await self.bot.db.val("SELECT COUNT(*) FROM hours WHERE guild_id = ?", (gid,), 0)
        if existing >= 1 and not self.bot.is_premium(gid):
            return await utils.reply(interaction, self.bot.t(gid, "err_premium", feature=self.bot.t(gid, "feat_hours")))
        await self.bot.db.execute("INSERT INTO hours(guild_id, days, start_min, end_min) VALUES(?,?,?,?)",
                                  (gid, ",".join(map(str, parsed_days)), s, e))
        await utils.reply(interaction, self.bot.t(gid, "hours_added"))

    @setup.command(name="hours-clear", description="Удалить все часы поддержки")
    @admin_only()
    async def setup_hours_clear(self, interaction: discord.Interaction) -> None:
        await self.bot.db.update("DELETE FROM hours WHERE guild_id = ?", (interaction.guild_id,))
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "done"))

    @setup.command(name="hours-show", description="Показать часы поддержки")
    @admin_only()
    async def setup_hours_show(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        windows = await self.svc.hours_windows(gid)
        if not windows:
            return await utils.reply(interaction, self.bot.t(gid, "hours_none"))
        await utils.reply(interaction, embed=self.bot.embed(gid, title=self.bot.t(gid, "hours_title"),
                                                            description=self.svc.format_hours(gid, windows)))

    @setup.command(name="timezone", description="Часовой пояс для часов поддержки (напр. Europe/Moscow)")
    @app_commands.describe(name="Название зоны IANA")
    @admin_only()
    async def setup_timezone(self, interaction: discord.Interaction, name: str) -> None:
        gid = interaction.guild_id
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(name.strip())
        except Exception:
            return await utils.reply(interaction, self.bot.t(gid, "err_bad_timezone"))
        await self.bot.set(gid, "timezone", name.strip())
        await utils.reply(interaction, self.bot.t(gid, "done"))

    @setup.command(name="show", description="Показать текущие настройки")
    @admin_only()
    async def setup_show(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        g = lambda k: self.bot.get(gid, k)  # noqa: E731
        onoff = lambda v: self.bot.t(gid, "on" if v else "off")  # noqa: E731
        ch = lambda v: f"<#{v}>" if v else "—"  # noqa: E731
        premium = self.bot.is_premium(gid)
        e = self.bot.embed(gid, title=self.bot.t(gid, "settings_title"))
        e.add_field(name="Premium", value=("✅" if premium else "❌"))
        e.add_field(name=self.bot.t(gid, "f_language"), value=self.bot.lang(gid))
        e.add_field(name=self.bot.t(gid, "f_limit"), value=str(g("ticket_limit")))
        e.add_field(name="use-threads", value=onoff(g("use_threads")))
        e.add_field(name="close-confirm", value=onoff(g("close_confirm")))
        e.add_field(name="delete-on-close", value=onoff(g("delete_on_close")))
        e.add_field(name="dm-transcript", value=onoff(g("dm_transcript")))
        e.add_field(name="close-on-leave", value=onoff(g("close_on_leave")))
        e.add_field(name="survey", value=onoff(g("survey") and premium))
        e.add_field(name="keepalive", value=onoff(g("keepalive") and premium))
        e.add_field(name=self.bot.t(gid, "f_category"), value=ch(g("category_id")))
        e.add_field(name=self.bot.t(gid, "f_log_channel"), value=ch(g("log_channel_id")))
        e.add_field(name=self.bot.t(gid, "f_transcripts_channel"), value=ch(g("transcript_channel_id")))
        e.add_field(name="autoclose", value=(f"{g('autoclose_hours')}h" if g("autoclose_hours") else self.bot.t(gid, "off")))
        e.add_field(name="SLA", value=(f"{g('sla_minutes')}m" if g("sla_minutes") else self.bot.t(gid, "off")))
        e.add_field(name=self.bot.t(gid, "f_timezone"), value=str(g("timezone")))
        e.add_field(name=self.bot.t(gid, "f_naming"), value=f"`{g('naming')}`", inline=False)
        await utils.reply(interaction, embed=e)

    # ================================================================== персонал
    async def _add_staff(self, interaction: discord.Interaction, target, level: str) -> None:
        gid = interaction.guild_id
        is_role = isinstance(target, discord.Role)
        await self.bot.db.execute("INSERT OR IGNORE INTO staff(guild_id, target_id, is_role, level) VALUES(?,?,?,?)",
                                  (gid, target.id, 1 if is_role else 0, level))
        await utils.reply(interaction, self.bot.t(gid, "staff_added", target=target.mention, level=level))

    async def _remove_staff(self, interaction: discord.Interaction, target, level: str) -> None:
        gid = interaction.guild_id
        n = await self.bot.db.update("DELETE FROM staff WHERE guild_id = ? AND target_id = ? AND level = ?", (gid, target.id, level))
        await utils.reply(interaction, self.bot.t(gid, "staff_removed" if n else "staff_not_found", target=target.mention, level=level))

    @app_commands.command(name="addadmin", description="Выдать пользователю или роли права админа бота")
    @app_commands.guild_only()
    @app_commands.describe(user_or_role="Пользователь или роль")
    @admin_only()
    async def addadmin(self, interaction: discord.Interaction, user_or_role: Union[discord.Member, discord.Role]) -> None:
        await self._add_staff(interaction, user_or_role, "admin")

    @app_commands.command(name="addsupport", description="Выдать пользователю или роли права поддержки (видят и ведут тикеты)")
    @app_commands.guild_only()
    @app_commands.describe(user_or_role="Пользователь или роль")
    @admin_only()
    async def addsupport(self, interaction: discord.Interaction, user_or_role: Union[discord.Member, discord.Role]) -> None:
        await self._add_staff(interaction, user_or_role, "support")

    @app_commands.command(name="removeadmin", description="Убрать права админа бота")
    @app_commands.guild_only()
    @app_commands.describe(user_or_role="Пользователь или роль")
    @admin_only()
    async def removeadmin(self, interaction: discord.Interaction, user_or_role: Union[discord.Member, discord.Role]) -> None:
        await self._remove_staff(interaction, user_or_role, "admin")

    @app_commands.command(name="removesupport", description="Убрать права поддержки")
    @app_commands.guild_only()
    @app_commands.describe(user_or_role="Пользователь или роль")
    @admin_only()
    async def removesupport(self, interaction: discord.Interaction, user_or_role: Union[discord.Member, discord.Role]) -> None:
        await self._remove_staff(interaction, user_or_role, "support")

    @app_commands.command(name="staff", description="Показать админов и поддержку бота")
    @app_commands.guild_only()
    @admin_only()
    async def staff_list(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        rows = await self.bot.db.all("SELECT * FROM staff WHERE guild_id = ? ORDER BY level, is_role", (gid,))
        if not rows:
            return await utils.reply(interaction, self.bot.t(gid, "staff_none"))
        groups: dict[str, list[str]] = {"admin": [], "support": []}
        for r in rows:
            groups[r["level"]].append(f"<@&{r['target_id']}>" if r["is_role"] else f"<@{r['target_id']}>")
        e = self.bot.embed(gid, title=self.bot.t(gid, "staff_title"))
        e.add_field(name="Admin", value=" ".join(groups["admin"]) or "—", inline=False)
        e.add_field(name="Support", value=" ".join(groups["support"]) or "—", inline=False)
        await utils.reply(interaction, embed=e)

    @app_commands.command(name="blacklist", description="Запретить/разрешить пользователю или роли пользоваться тикетами (переключатель)")
    @app_commands.guild_only()
    @app_commands.describe(user_or_role="Пользователь или роль")
    @support_only()
    async def blacklist_cmd(self, interaction: discord.Interaction, user_or_role: Union[discord.Member, discord.Role]) -> None:
        gid = interaction.guild_id
        removed = await self.bot.db.update("DELETE FROM blacklist WHERE guild_id = ? AND target_id = ?", (gid, user_or_role.id))
        if removed:
            return await utils.reply(interaction, self.bot.t(gid, "blacklist_off", target=user_or_role.mention))
        if isinstance(user_or_role, discord.Member) and await self.bot.is_support(user_or_role):
            return await utils.reply(interaction, self.bot.t(gid, "err_blacklist_staff"))
        await self.bot.db.execute("INSERT OR IGNORE INTO blacklist(guild_id, target_id, is_role) VALUES(?,?,?)",
                                  (gid, user_or_role.id, 1 if isinstance(user_or_role, discord.Role) else 0))
        await utils.reply(interaction, self.bot.t(gid, "blacklist_on", target=user_or_role.mention))

    @app_commands.command(name="language", description="Язык сообщений бота / Bot language")
    @app_commands.guild_only()
    @app_commands.describe(language="Язык")
    @app_commands.choices(language=[app_commands.Choice(name="Русский", value="ru"), app_commands.Choice(name="English", value="en")])
    @admin_only()
    async def language_cmd(self, interaction: discord.Interaction, language: app_commands.Choice[str]) -> None:
        await self.bot.set(interaction.guild_id, "language", language.value)
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "language_set"))


async def setup(bot) -> None:
    await bot.add_cog(Settings(bot))
