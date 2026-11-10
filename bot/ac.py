"""Автодополнение (autocomplete) для слеш-команд."""
from __future__ import annotations

import discord
from discord import app_commands


def _filter(names: list[str], current: str) -> list[app_commands.Choice[str]]:
    cur = (current or "").lower()
    out = [app_commands.Choice(name=n[:100], value=n[:100]) for n in names if cur in n.lower()]
    return out[:25]


async def panel_ac(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    rows = await interaction.client.db.all("SELECT name FROM panels WHERE guild_id = ? ORDER BY id", (interaction.guild_id,))
    return _filter([r["name"] for r in rows], current)


async def multipanel_ac(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    rows = await interaction.client.db.all("SELECT name FROM multipanels WHERE guild_id = ? ORDER BY id", (interaction.guild_id,))
    return _filter([r["name"] for r in rows], current)


async def form_ac(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    rows = await interaction.client.db.all("SELECT name FROM forms WHERE guild_id = ? ORDER BY id", (interaction.guild_id,))
    return _filter([r["name"] for r in rows], current)


async def tag_ac(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    rows = await interaction.client.db.all("SELECT name FROM tags WHERE guild_id = ? ORDER BY name", (interaction.guild_id,))
    return _filter([r["name"] for r in rows], current)


async def kb_ac(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    rows = await interaction.client.db.all("SELECT id, title FROM kb WHERE guild_id = ? ORDER BY id", (interaction.guild_id,))
    cur = (current or "").lower()
    out = [app_commands.Choice(name=f"#{r['id']} {r['title']}"[:100], value=str(r["id"]))
           for r in rows if cur in r["title"].lower() or cur in str(r["id"])]
    return out[:25]
