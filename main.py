"""Точка входа: python main.py"""
from __future__ import annotations

import logging
import sys

from bot.config import Config
from bot.core import TicketBot


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    cfg = Config.load()
    if not cfg.token:
        print("Не задан DISCORD_TOKEN. Скопируйте .env.example в .env и впишите токен бота.", file=sys.stderr)
        return 1
    bot = TicketBot(cfg)
    bot.run(cfg.token, log_handler=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
