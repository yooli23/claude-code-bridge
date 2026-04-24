"""Unified entry point — run Telegram, Discord, or both, with optional webhook."""

import argparse
import asyncio
import logging
import os
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


async def _start_webhook(discord_client=None):
    """Start the GitHub webhook server if GITHUB_WEBHOOK_SECRET is set."""
    webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not webhook_secret and not os.environ.get("WEBHOOK_PORT"):
        return None

    from webhook import WebhookServer
    from discord_bot import config_store, bridge, chat_queue, active_sessions
    from discord_bot import wrap_channel_message, CLAUDE_BIN, CLAUDE_PERMISSION_MODE

    async def on_main_push(summary: dict):
        repo = summary["repo"]
        commits = summary.get("commits", [])
        pr_info = summary.get("pr_info", "")

        for binding in config_store._bindings.values():
            if binding.code_repo != repo:
                continue
            if not binding.paper_repo:
                continue

            commit_list = "\n".join(f"- {c}" for c in commits[:10])
            task_desc = (
                f"Update paper for changes merged to {repo} main:\n"
                f"{pr_info}\n\n"
                f"Commits:\n{commit_list}\n\n"
                f"Pull the latest main in the code repo, review the changes, "
                f"then update the paper repo ({binding.paper_repo}) accordingly. "
                f"Submit a PR on the paper repo with the updates."
            )

            if discord_client:
                channel = discord_client.get_channel(binding.channel_id)
                if channel:
                    try:
                        thread_with_msg = await channel.create_thread(
                            name=f"Paper update: {pr_info[:80] or 'main merged'}",
                            content=(
                                f"**Auto-triggered:** code repo `{repo}` main was updated.\n"
                                f"**Commits:**\n{commit_list}"
                            ),
                        )
                        await thread_with_msg.thread.send(
                            f"Spawning agent to update paper repo `{binding.paper_repo}`..."
                        )
                        logger.info(
                            f"Created paper update thread for {repo} in channel {binding.channel_id}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to create paper update thread: {e}")

            logger.info(f"Main push on {repo} — paper update needed for {binding.paper_repo}")

    server = WebhookServer(on_main_push=on_main_push)
    await server.start()
    return server


async def run_both():
    """Run both bots concurrently in the same event loop."""
    from telegram_bot import create_telegram_app
    from discord_bot import create_discord_client

    tg_app = create_telegram_app()
    dc_client = create_discord_client()

    dc_token = os.environ.get("DISCORD_BOT_TOKEN", "")

    async with tg_app:
        await tg_app.start()
        await tg_app.updater.start_polling()
        logger.info("Telegram bot started")

        webhook = await _start_webhook(discord_client=dc_client)

        try:
            await dc_client.start(dc_token)
        finally:
            await tg_app.updater.stop()
            await tg_app.stop()


async def run_discord_with_webhook():
    """Run Discord bot with webhook server."""
    from discord_bot import create_discord_client

    dc_client = create_discord_client()
    dc_token = os.environ.get("DISCORD_BOT_TOKEN", "")

    webhook = await _start_webhook(discord_client=dc_client)

    await dc_client.start(dc_token)


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
        logger.info("Starting Discord bot with webhook...")
        asyncio.run(run_discord_with_webhook())
    elif args.platform == "both":
        logger.info("Starting both Telegram and Discord bots...")
        asyncio.run(run_both())


if __name__ == "__main__":
    main()
