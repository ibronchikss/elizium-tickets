from __future__ import annotations

import html
import re
import zlib
from datetime import datetime, timezone
from typing import Iterable, Optional

CSS = """
body{margin:0;background:#313338;color:#dbdee1;font:15px/1.4 'Segoe UI',Arial,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 6px;color:#fff}
.meta{background:#2b2d31;border-radius:8px;padding:12px 16px;margin:12px 0 20px;font-size:13px}
.meta b{color:#fff}
.msg{display:flex;gap:12px;padding:6px 0}
.ava{width:40px;height:40px;border-radius:50%;flex:none;background:#5865f2}
.hd{font-size:14px}.hd .n{color:#fff;font-weight:600}.hd .t{color:#949ba4;font-size:12px;margin-left:6px}
.bot{background:#5865f2;color:#fff;font-size:10px;border-radius:3px;padding:1px 4px;margin-left:4px}
.body{white-space:pre-wrap;word-wrap:break-word}
.body code{background:#1e1f22;border-radius:3px;padding:1px 4px}
.body pre{background:#1e1f22;border-radius:6px;padding:8px;margin:4px 0;overflow:auto}
a{color:#00a8fc}
.att{margin-top:4px;font-size:13px}
.emb{border-left:4px solid #5865f2;background:#2b2d31;border-radius:4px;padding:8px 12px;margin-top:4px;max-width:520px}
.emb .et{font-weight:600;color:#fff}.emb .ef{margin-top:6px;font-size:13px}
.sys{color:#949ba4;font-size:13px;padding:4px 0 4px 52px}
"""


def md(text: str) -> str:
    """Экранирование + минимальный markdown Discord."""
    t = html.escape(text or "")
    t = re.sub(r"```(?:\w+\n)?(.*?)```", lambda m: f"<pre>{m.group(1)}</pre>", t, flags=re.S)
    t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"__(.+?)__", r"<u>\1</u>", t)
    t = re.sub(r"~~(.+?)~~", r"<s>\1</s>", t)
    t = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', t)
    return t


def _embed_html(e) -> str:
    parts = []
    if e.title:
        parts.append(f'<div class="et">{html.escape(e.title)}</div>')
    if e.description:
        parts.append(f'<div class="body">{md(e.description)}</div>')
    for f in e.fields:
        parts.append(f'<div class="ef"><b>{html.escape(f.name)}</b><br>{md(f.value)}</div>')
    if not parts:
        return ""
    color = f"#{e.color.value:06x}" if e.color else "#5865f2"
    return f'<div class="emb" style="border-left-color:{color}">{"".join(parts)}</div>'


def render_html(title: str, meta: Iterable[tuple[str, str]], messages: list) -> str:
    """messages — список discord.Message."""
    rows = []
    for m in messages:
        mtype = getattr(m.type, "name", "default")
        if mtype not in ("default", "reply"):
            text = html.escape(m.system_content or "")
            if text:
                rows.append(f'<div class="sys">{text}</div>')
            continue
        when = m.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        author = html.escape(getattr(m.author, "display_name", str(m.author)))
        avatar = html.escape(str(m.author.display_avatar.url)) if getattr(m.author, "display_avatar", None) else ""
        bot_tag = '<span class="bot">BOT</span>' if getattr(m.author, "bot", False) else ""
        body = md(m.clean_content) if m.clean_content else ""
        att = "".join(
            f'<div class="att">📎 <a href="{html.escape(a.url)}">{html.escape(a.filename)}</a></div>' for a in m.attachments
        )
        emb = "".join(_embed_html(e) for e in m.embeds)
        rows.append(
            f'<div class="msg"><img class="ava" src="{avatar}" alt=""><div>'
            f'<div class="hd"><span class="n">{author}</span>{bot_tag}<span class="t">{when}</span></div>'
            f'<div class="body">{body}</div>{att}{emb}</div></div>'
        )
    meta_html = "".join(f"<div><b>{html.escape(k)}:</b> {html.escape(v)}</div>" for k, v in meta)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
        f"<style>{CSS}</style></head><body><div class=\"wrap\"><h1>{html.escape(title)}</h1>"
        f'<div class="meta">{meta_html}<div><b>Generated:</b> {generated}</div></div>{"".join(rows)}</div></body></html>'
    )


async def render(channel, *, title: str, meta: Iterable[tuple[str, str]], limit: int = 10000) -> tuple[str, int]:
    messages = []
    async for m in channel.history(limit=limit, oldest_first=True):
        messages.append(m)
    return render_html(title, meta, messages), len(messages)


def pack(html_text: str) -> bytes:
    return zlib.compress(html_text.encode("utf-8"), 6)


def unpack(blob: Optional[bytes]) -> Optional[str]:
    if not blob:
        return None
    return zlib.decompress(blob).decode("utf-8")
