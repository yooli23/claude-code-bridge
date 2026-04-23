"""Legacy entry point — delegates to telegram_bot.py."""

import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

from telegram_bot import main

if __name__ == "__main__":
    main()
