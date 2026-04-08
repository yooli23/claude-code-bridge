"""Telegram bot that bridges to Claude Code sessions."""

import asyncio
import json
import logging
import os
import time

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bridge import ClaudeBridge
from sessions import list_sessions, get_session_by_id

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Config
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_PERMISSION_MODE = os.environ.get("CLAUDE_PERMISSION_MODE", "bypassPermissions")

# Per-chat active session mapping
active_sessions: dict[int, str] = {}  # chat_id -> session_id

bridge = ClaudeBridge(
    claude_bin=CLAUDE_BIN,
    permission_mode=CLAUDE_PERMISSION_MODE,
)

# Telegram message size limit
TG_MAX_LEN = 4096
# Minimum interval between edits (Telegram rate limit)
EDIT_INTERVAL = 1.5


def auth(func):
    """Decorator to restrict access to allowed user only."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
            logger.warning(f"Unauthorized access attempt from user {user_id}")
            await update.effective_message.reply_text("Unauthorized.")
            return
        return await func(update, context)
    return wrapper


def escape_md(text: str) -> str:
    """Minimal escaping — we send as plain text to avoid markdown parse errors."""
    return text


def truncate(text: str, limit: int = TG_MAX_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n\n...(truncated)"


# --- Handlers ---


@auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Claude Code Telegram Bridge\n\n"
        "Commands:\n"
        "/sessions - List and pick a Claude Code session\n"
        "/current - Show current active session\n"
        "/detach - Detach from current session\n"
        "/new <cwd> - Start a new session in a directory\n\n"
        "Once a session is selected, just send messages directly."
    )


@auth
async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List available sessions with inline keyboard for selection."""
    sessions = list_sessions()
    if not sessions:
        await update.message.reply_text("No Claude Code sessions found.")
        return

    # Show up to 20 most recent sessions
    sessions = sessions[:20]

    keyboard = []
    text_lines = ["Pick a session:\n"]
    for i, s in enumerate(sessions):
        label = f"{s.short_id} | {s.display_name}"
        if len(label) > 60:
            label = label[:57] + "..."
        keyboard.append(
            [InlineKeyboardButton(label, callback_data=f"pick:{s.session_id}")]
        )
        cwd_short = s.cwd
        ts = s.timestamp[:16].replace("T", " ") if s.timestamp else "?"
        text_lines.append(f"{i+1}. [{s.short_id}] {cwd_short}\n   {s.display_name}\n   {ts}")

    await update.message.reply_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


@auth
async def cmd_current(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sid = active_sessions.get(chat_id)
    if not sid:
        await update.message.reply_text("No active session. Use /sessions to pick one.")
        return

    session = get_session_by_id(sid)
    if session:
        await update.message.reply_text(
            f"Active session: {session.short_id}\n"
            f"Directory: {session.cwd}\n"
            f"Started: {session.display_name}"
        )
    else:
        await update.message.reply_text(f"Active session: {sid[:8]} (details unavailable)")


@auth
async def cmd_detach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in active_sessions:
        old = active_sessions.pop(chat_id)
        await update.message.reply_text(f"Detached from session {old[:8]}.")
    else:
        await update.message.reply_text("No active session.")


@auth
async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a new Claude Code session in a given directory."""
    args = context.args
    cwd = " ".join(args) if args else os.path.expanduser("~")

    if not os.path.isdir(cwd):
        await update.message.reply_text(f"Directory not found: {cwd}")
        return

    msg = await update.message.reply_text(f"Starting new session in {cwd}...")

    # Start a new session by calling claude without --resume
    cmd = [
        CLAUDE_BIN,
        "--print",
        "--permission-mode", CLAUDE_PERMISSION_MODE,
        "--output-format", "json",
        "-p", "Say 'Session started. Ready for instructions.' and nothing else.",
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await process.communicate()

    try:
        result = json.loads(stdout.decode())
        session_id = result.get("session_id", "")
        if session_id:
            active_sessions[update.effective_chat.id] = session_id
            await msg.edit_text(
                f"New session created: {session_id[:8]}\n"
                f"Directory: {cwd}\n\n"
                "Send messages to start working."
            )
            return
    except (json.JSONDecodeError, KeyError):
        pass

    await msg.edit_text(
        f"Session started in {cwd} but couldn't capture session ID.\n"
        "Use /sessions to find and select it."
    )


@auth
async def callback_pick_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard session selection."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("pick:"):
        return

    session_id = data[5:]
    chat_id = update.effective_chat.id
    active_sessions[chat_id] = session_id

    session = get_session_by_id(session_id)
    if session:
        await query.edit_message_text(
            f"Connected to session {session.short_id}\n"
            f"Directory: {session.cwd}\n"
            f"Topic: {session.display_name}\n\n"
            "Send messages to continue this session."
        )
    else:
        await query.edit_message_text(
            f"Connected to session {session_id[:8]}.\nSend messages to continue."
        )


@auth
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward user message to active Claude Code session."""
    chat_id = update.effective_chat.id
    session_id = active_sessions.get(chat_id)

    if not session_id:
        await update.message.reply_text(
            "No active session. Use /sessions to pick one, or /new <dir> to start fresh."
        )
        return

    user_text = update.message.text
    if not user_text:
        await update.message.reply_text("Only text messages are supported.")
        return

    # Send typing indicator
    await update.effective_chat.send_action(ChatAction.TYPING)

    # Send a placeholder that we'll edit with streaming content
    reply = await update.message.reply_text("thinking...")

    last_edit_time = 0.0
    last_edit_text = ""

    async def on_delta(text_so_far: str):
        nonlocal last_edit_time, last_edit_text
        now = time.time()

        # Rate-limit edits to avoid Telegram API throttling
        if now - last_edit_time < EDIT_INTERVAL:
            return

        display = truncate(text_so_far)
        if display == last_edit_text:
            return

        try:
            await reply.edit_text(display)
            last_edit_time = now
            last_edit_text = display
        except Exception:
            pass  # Telegram edit errors (message not modified, etc.)

    # Keep sending typing action in background
    typing_task = asyncio.create_task(_keep_typing(update.effective_chat))

    # Resolve session cwd so claude runs in the right directory
    session = get_session_by_id(session_id)
    session_cwd = session.cwd if session else None

    try:
        response = await bridge.send_message(
            session_id=session_id,
            message=user_text,
            cwd=session_cwd,
            on_delta=on_delta,
        )
    finally:
        typing_task.cancel()

    # Final edit with complete response
    final = truncate(response)
    if final != last_edit_text:
        try:
            await reply.edit_text(final)
        except Exception:
            # If edit fails, send as new message
            await update.message.reply_text(final)


async def _keep_typing(chat, interval: float = 8.0):
    """Send typing action periodically while Claude is working."""
    try:
        while True:
            await chat.send_action(ChatAction.TYPING)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass


def main():
    if not BOT_TOKEN or BOT_TOKEN == "your-bot-token-here":
        print("Error: Set TELEGRAM_BOT_TOKEN in .env")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("sessions", cmd_sessions))
    app.add_handler(CommandHandler("current", cmd_current))
    app.add_handler(CommandHandler("detach", cmd_detach))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CallbackQueryHandler(callback_pick_session, pattern=r"^pick:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
