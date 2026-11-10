from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from .. import utils

log = logging.getLogger("ticketbot.cog.general")


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Список команд / Command list")
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        e = self.bot.embed(gid, title=self.bot.t(gid, "help_title"), description=self.bot.t(gid, "help_intro"))
        for key in ("help_users", "help_staff", "help_admin", "help_premium"):
            e.add_field(name=self.bot.t(gid, key + "_h"), value=self.bot.t(gid, key), inline=False)
        await utils.reply(interaction, embed=e)

    @app_commands.command(name="about", description="О боте / About the bot")
    async def about_cmd(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        uptime = utils.fmt_duration(time.time() - self.bot.started_at, self.bot.lang(gid))
        open_count = len(self.bot.open_channels)
        e = self.bot.embed(gid, title=self.bot.t(gid, "about_title"), description=self.bot.t(gid, "about_desc"))
        e.add_field(name=self.bot.t(gid, "about_servers"), value=str(len(self.bot.guilds)))
        e.add_field(name=self.bot.t(gid, "about_open"), value=str(open_count))
        e.add_field(name=self.bot.t(gid, "about_uptime"), value=uptime)
        e.add_field(name=self.bot.t(gid, "about_latency"), value=f"{round(self.bot.latency * 1000)} ms")
        await utils.reply(interaction, embed=e)

    @app_commands.command(name="invite", description="Ссылка для приглашения бота / Invite link")
    async def invite_cmd(self, interaction: discord.Interaction) -> None:
        perms = discord.Permissions(
            view_channel=True, send_messages=True, embed_links=True, attach_files=True, read_message_history=True,
            manage_channels=True, manage_roles=True, manage_messages=True, manage_threads=True,
            create_private_threads=True, send_messages_in_threads=True, add_reactions=True, use_external_emojis=True)
        url = discord.utils.oauth_url(self.bot.user.id, permissions=perms, scopes=("bot", "applications.commands"))
        await utils.reply(interaction, self.bot.t(interaction.guild_id, "invite_text", url=url))

    @app_commands.command(name="vote", description="Проголосовать за бота / Vote")
    async def vote_cmd(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        if not self.bot.cfg.vote_url:
            return await utils.reply(interaction, self.bot.t(gid, "vote_none"))
        await utils.reply(interaction, self.bot.t(gid, "vote_text", url=self.bot.cfg.vote_url))

    @app_commands.command(name="support", description="Сервер поддержки / Support server")
    async def support_cmd(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        if not self.bot.cfg.support_url:
            return await utils.reply(interaction, self.bot.t(gid, "support_none"))
        await utils.reply(interaction, self.bot.t(gid, "support_text", url=self.bot.cfg.support_url))

    @app_commands.command(name="gdpr", description="Удалить сохранённые данные о вас (транскрипты, оценки) / GDPR")
    @app_commands.describe(confirm="Подтвердите удаление")
    async def gdpr_cmd(self, interaction: discord.Interaction, confirm: bool = False) -> None:
        gid = interaction.guild_id
        if not confirm:
            return await utils.reply(interaction, self.bot.t(gid, "gdpr_confirm"))
        uid = interaction.user.id
        db = self.bot.db
        await db.update("DELETE FROM transcripts WHERE ticket_id IN (SELECT id FROM tickets WHERE opener_id = ?)", (uid,))
        await db.update("UPDATE tickets SET rating_comment = NULL, subject = NULL WHERE opener_id = ?", (uid,))
        await db.update("DELETE FROM oncall WHERE user_id = ?", (uid,))
        await utils.reply(interaction, self.bot.t(gid, "gdpr_done"))


async def setup(bot) -> None:
    await bot.add_cog(General(bot))
