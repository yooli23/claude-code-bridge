"""Unified entry point — run Telegram, Discord, or both."""

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def run_telegram():
    from telegram_bot import main as tg_main
    tg_main()


def run_discord():
    from discord_bot import main as dc_main
    dc_main()


async def run_both():
    """Run both bots concurrently in the same event loop."""
    from telegram_bot import create_telegram_app
    from discord_bot import create_discord_client

    tg_app = create_telegram_app()
    dc_client = create_discord_client()

    import os
    dc_token = os.environ.get("DISCORD_BOT_TOKEN", "")

    async with tg_app:
        await tg_app.start()
        await tg_app.updater.start_polling()
        logger.info("Telegram bot started")

        try:
            await dc_client.start(dc_token)
        finally:
            await tg_app.updater.stop()
            await tg_app.stop()


def main():
    parser = argparse.ArgumentParser(description="Claude Code Chat Bridge")
    parser.add_argument(
        "platform",
        nargs="?",
        default="telegram",
        choices=["telegram", "discord", "both"],
        help="Which platform to run (default: telegram)",
    )
    args = parser.parse_args()

    if args.platform == "telegram":
        logger.info("Starting Telegram bot...")
        run_telegram()
    elif args.platform == "discord":
        logger.info("Starting Discord bot...")
        run_discord()
    elif args.platform == "both":
        logger.info("Starting both Telegram and Discord bots...")
        asyncio.run(run_both())


if __name__ == "__main__":
    main()
