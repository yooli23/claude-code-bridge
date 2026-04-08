# Claude Code Telegram Bridge

A lightweight Telegram bot that lets you continue your Claude Code sessions from your phone.

When you step away from your laptop, pick up any active Claude Code session on Telegram — same context, same tools, same everything.

## How it works

```
Your Machine (laptop/server)
┌──────────────────────────────┐
│  Claude Code sessions        │
│  ~/.claude/projects/...      │
│                              │
│  This bot (bot.py)           │
│    └─ claude --resume ID -p  │
└──────────────┬───────────────┘
               │ Telegram Bot API
               ▼
┌──────────────────────────────┐
│  Your Phone (Telegram)       │
│    /sessions → pick one      │
│    send messages → get reply │
└──────────────────────────────┘
```

The bot wraps the `claude` CLI directly — no extra LLM calls, no separate agent. Your Telegram messages go to the real Claude Code session and responses come straight back with streaming updates.

## Setup

### 1. Create a Telegram bot

- Open Telegram, talk to [@BotFather](https://t.me/BotFather)
- Send `/newbot`, follow the prompts
- Copy the bot token

### 2. Get your Telegram user ID

- Talk to [@userinfobot](https://t.me/userinfobot) on Telegram
- It replies with your numeric user ID

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```
TELEGRAM_BOT_TOKEN=your-bot-token
ALLOWED_USER_ID=your-telegram-user-id
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Run

```bash
python3 bot.py
```

Or in a tmux/screen session to keep it running:

```bash
tmux new -s telegram-bot
python3 bot.py
```

## Usage

| Command | Description |
|---------|-------------|
| `/start` | Show help |
| `/sessions` | List Claude Code sessions (tap to connect) |
| `/current` | Show active session info |
| `/detach` | Disconnect from current session |
| `/new /path/to/dir` | Start a new session in a directory |
| *(any text)* | Send message to active session |

## Requirements

- Python 3.11+
- `claude` CLI installed and authenticated
- The bot must run on the same machine where your Claude Code sessions live

## Notes

- **Auth**: Only the configured `ALLOWED_USER_ID` can interact with the bot
- **Permissions**: Uses `bypassPermissions` by default since you can't approve prompts on Telegram (configurable in `.env`)
- **Streaming**: Responses are progressively updated in Telegram as Claude types
- **Telegram limit**: Messages over 4096 characters are truncated
