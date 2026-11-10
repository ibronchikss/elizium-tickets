from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import ac, utils
from ..core import admin_only, premium_only, support_only

log = logging.getLogger("ticketbot.cog.tags")


class Tags(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ================================================================== /tag
    tag = app_commands.Group(name="tag", description="Теги — готовые ответы для поддержки", guild_only=True)

    @tag.command(name="use", description="Отправить тег в канал")
    @app_commands.describe(name="Название тега")
    @support_only()
    async def tag_use(self, interaction: discord.Interaction, name: str) -> None:
        gid = interaction.guild_id
        row = await self.bot.db.one("SELECT content FROM tags WHERE guild_id = ? AND lower(name) = lower(?)", (gid, name.strip()))
        if row is None:
            return await utils.reply(interaction, self.bot.t(gid, "err_tag_missing"))
        await interaction.response.send_message(row["content"], allowed_mentions=discord.AllowedMentions.none())

    @tag.command(name="create", description="Создать или обновить тег")
    @app_commands.describe(name="Название (без пробелов)", content="Текст ответа")
    @admin_only()
    async def tag_create(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 40],
                         content: app_commands.Range[str, 1, 2000]) -> None:
        gid = interaction.guild_id
        name = name.strip().lower().replace(" ", "-")
        await self.bot.db.execute(
            "INSERT INTO tags(guild_id, name, content) VALUES(?,?,?) "
            "ON CONFLICT(guild_id, name) DO UPDATE SET content = excluded.content", (gid, name, content))
        await utils.reply(interaction, self.bot.t(gid, "tag_saved", name=name))

    @tag.command(name="delete", description="Удалить тег")
    @app_commands.describe(name="Название тега")
    @admin_only()
    async def tag_delete(self, interaction: discord.Interaction, name: str) -> None:
        gid = interaction.guild_id
        n = await self.bot.db.update("DELETE FROM tags WHERE guild_id = ? AND lower(name) = lower(?)", (gid, name.strip()))
        await utils.reply(interaction, self.bot.t(gid, "done" if n else "err_tag_missing"))

    @tag.command(name="list", description="Список тегов")
    @support_only()
    async def tag_list(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        rows = await self.bot.db.all("SELECT name FROM tags WHERE guild_id = ? ORDER BY name", (gid,))
        if not rows:
            return await utils.reply(interaction, self.bot.t(gid, "tags_none"))
        await utils.reply(interaction, embed=self.bot.embed(
            gid, title=self.bot.t(gid, "tags_title"), description=", ".join(f"`{r['name']}`" for r in rows)))

    @tag_use.autocomplete("name")
    async def ac_tag_use(self, interaction: discord.Interaction, current: str):
        return await ac.tag_ac(interaction, current)

    @tag_delete.autocomplete("name")
    async def ac_tag_delete(self, interaction: discord.Interaction, current: str):
        return await ac.tag_ac(interaction, current)

    # ================================================================== /kb
    kb = app_commands.Group(name="kb", description="База знаний: статьи для участников", guild_only=True)

    @kb.command(name="add", description="Добавить статью в базу знаний")
    @app_commands.describe(title="Заголовок", content="Текст статьи", keywords="Ключевые слова через запятую")
    @admin_only()
    async def kb_add(self, interaction: discord.Interaction, title: app_commands.Range[str, 1, 100],
                     content: app_commands.Range[str, 1, 3000], keywords: Optional[str] = None) -> None:
        gid = interaction.guild_id
        count = await self.bot.db.val("SELECT COUNT(*) FROM kb WHERE guild_id = ?", (gid,), 0)
        if count >= self.bot.cfg.free_kb_limit and not self.bot.is_premium(gid):
            return await utils.reply(interaction, self.bot.t(gid, "err_premium", feature=self.bot.t(
                gid, "feat_kb", n=self.bot.cfg.free_kb_limit)))
        kid = await self.bot.db.execute("INSERT INTO kb(guild_id, title, content, keywords) VALUES(?,?,?,?)",
                                        (gid, title, content, utils.trunc(keywords or "", 300)))
        await utils.reply(interaction, self.bot.t(gid, "kb_added", id=kid))

    @kb.command(name="remove", description="Удалить статью")
    @app_commands.describe(article="Статья")
    @admin_only()
    async def kb_remove(self, interaction: discord.Interaction, article: str) -> None:
        gid = interaction.guild_id
        if not article.isdigit():
            return await utils.reply(interaction, self.bot.t(gid, "err_kb_missing"))
        n = await self.bot.db.update("DELETE FROM kb WHERE guild_id = ? AND id = ?", (gid, int(article)))
        await utils.reply(interaction, self.bot.t(gid, "done" if n else "err_kb_missing"))

    @kb.command(name="list", description="Список статей")
    @admin_only()
    async def kb_list(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        rows = await self.bot.db.all("SELECT id, title FROM kb WHERE guild_id = ? ORDER BY id", (gid,))
        if not rows:
            return await utils.reply(interaction, self.bot.t(gid, "kb_none"))
        await utils.reply(interaction, embed=self.bot.embed(
            gid, title=self.bot.t(gid, "kb_title"), description="\n".join(f"**#{r['id']}** {r['title']}" for r in rows)))

    @kb.command(name="search", description="Найти ответ в базе знаний")
    @app_commands.describe(query="Ваш вопрос")
    async def kb_search(self, interaction: discord.Interaction, query: app_commands.Range[str, 2, 200]) -> None:
        gid = interaction.guild_id
        articles = await self.bot.db.all("SELECT * FROM kb WHERE guild_id = ?", (gid,))
        scored = sorted(((utils.score_article(query, a), a) for a in articles), key=lambda x: -x[0])
        top = [a for s, a in scored if s > 0][:3]
        if not top:
            return await utils.reply(interaction, self.bot.t(gid, "kb_no_results"))
        e = self.bot.embed(gid, title=self.bot.t(gid, "kb_results_title"))
        for a in top:
            e.add_field(name=utils.trunc(a["title"], 256), value=utils.trunc(a["content"], 700), inline=False)
        await utils.reply(interaction, embed=e)

    @kb_remove.autocomplete("article")
    async def ac_kb_remove(self, interaction: discord.Interaction, current: str):
        return await ac.kb_ac(interaction, current)

    # ================================================================== /faq (Premium)
    @app_commands.command(name="faq", description="Мгновенно отправить статью базы знаний в канал (Premium)")
    @app_commands.guild_only()
    @app_commands.describe(article="Статья")
    @support_only()
    @premium_only("/faq")
    async def faq_cmd(self, interaction: discord.Interaction, article: str) -> None:
        gid = interaction.guild_id
        row = await self.bot.db.one("SELECT * FROM kb WHERE guild_id = ? AND id = ?", (gid, int(article))) if article.isdigit() else None
        if row is None:
            return await utils.reply(interaction, self.bot.t(gid, "err_kb_missing"))
        e = self.bot.embed(gid, title=row["title"], description=row["content"])
        await interaction.response.send_message(embed=e)

    @faq_cmd.autocomplete("article")
    async def ac_faq(self, interaction: discord.Interaction, current: str):
        return await ac.kb_ac(interaction, current)


async def setup(bot) -> None:
    await bot.add_cog(Tags(bot))
