# Claude Code Bridge

Bridge Claude Code to chat platforms — use your Claude Code sessions from Telegram, Discord, or both. Supports single-user mobile access and multi-user team collaboration.

## What it does

```
Your Machine (laptop/server)
┌─────────────────────────────────────┐
│  Claude Code sessions               │
│  ~/.claude/projects/...             │
│                                     │
│  Bridge (main.py)                   │
│    ├─ Telegram bot adapter          │
│    ├─ Discord bot adapter           │
│    ├─ GitHub webhook listener       │
│    └─ claude --resume ID --print    │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       ▼               ▼
  Telegram          Discord
  (mobile)       (team collab)
```

The bot wraps the `claude` CLI directly — no extra LLM calls, no separate agent. Messages go to real Claude Code sessions and responses stream back.

## Features

### Core
- Streaming responses with adaptive rate limiting
- Message splitting at natural boundaries (no truncation)
- Reaction-based status: ⏳ thinking, 🔧 tool, 🔐 permission, 📦 compact, ✅ done, ❌ error
- File/photo attachments
- Session discovery with live-process filtering
- Cost tracking with threshold alerts ($1/$5/$10/$25)
- Cancel support via `/cancel`
- Permission relay with inline Allow/Deny buttons
- Message queue for concurrent messages

### Multi-User Collaboration (Discord)
- **Forum channels** — one channel per project, each task gets its own thread
- **Git worktree isolation** — each spawned task works on its own branch, no file conflicts
- **Shared context** — `CLAUDE.md`, `STATUS.md`, `NOTES.md` keep everyone in sync
- **Any channel member can contribute** — no per-user setup needed
- **Auto PR workflow** — agents push branches and submit PRs, never commit to main
- **Project dashboard** — `/board` shows tasks, PRs, status, and notes in one view
- **GitHub webhooks** — auto-spawn paper updates when code merges to main

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your tokens:

```env
# Telegram (optional)
TELEGRAM_BOT_TOKEN=your-token
ALLOWED_USER_ID=your-telegram-user-id

# Discord (optional)
DISCORD_BOT_TOKEN=your-token
DISCORD_ALLOWED_USER_ID=your-discord-user-id

# Claude Code
CLAUDE_BIN=claude
CLAUDE_PERMISSION_MODE=bypassPermissions

# GitHub webhook (optional, for paper auto-update)
# GITHUB_WEBHOOK_SECRET=your-secret
# WEBHOOK_PORT=8787
```

### 3. Run

```bash
# Telegram only
python main.py telegram

# Discord only
python main.py discord

# Both platforms
python main.py both
```

## Telegram Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Get your user ID from [@userinfobot](https://t.me/userinfobot)
3. Set `TELEGRAM_BOT_TOKEN` and `ALLOWED_USER_ID` in `.env`
4. Run `python main.py telegram`

### Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Show help |
| `/sessions` | List live sessions (tap to connect) |
| `/current` | Show active session info |
| `/detach` | Disconnect from session |
| `/new /path/to/dir` | Start a new session |
| `/cancel` | Cancel running operation |
| `/cost` | Show session cost |
| *(any text)* | Send message to active session |

## Discord Setup

### Single-User Mode

1. Create a Discord app at [discord.com/developers](https://discord.com/developers/applications)
2. Bot settings: enable **Message Content Intent**
3. Generate an invite URL with scopes: `bot`, `applications.commands`
4. Permissions: Send Messages, Read Message History, Add Reactions, Manage Messages, Use Slash Commands
5. Invite the bot to your server
6. Set `DISCORD_BOT_TOKEN` and `DISCORD_ALLOWED_USER_ID` in `.env`
7. Run `python main.py discord`

Use `/sessions` in any channel to pick a session, then chat.

### Multi-User Team Mode

For team collaboration, use Discord Forum channels:

**1. Create a Forum channel** in your Discord server (e.g., `#project-alpha`)

**2. Bind it to a project:**
```
/setup project_dir:/path/to/project code_repo:org/repo paper_repo:org/paper-repo
```

This creates `CLAUDE.md`, `STATUS.md`, `NOTES.md` in the repo with workflow rules.

**3. Invite your team** to the Discord server — anyone in the channel can use the bot.

**4. Start working:**
```
/spawn implement the data loader with sharding support
```

Each `/spawn` creates a forum post thread with its own git worktree branch and Claude session. The agent reads project context, works on the task, and submits a PR when done.

### Discord Commands

| Command | Where | Description |
|---------|-------|-------------|
| `/setup` | Forum channel | Bind channel to a project (one-time) |
| `/spawn <task>` | Forum channel | Create a task with isolated branch |
| `/status` | Forum channel | List active agent tasks |
| `/board` | Forum channel | Full dashboard: status + tasks + PRs + notes |
| `/note <text>` | Forum channel | Add to NOTES.md and push |
| `/notes` | Forum channel | Display NOTES.md |
| `/sessions` | Regular channel | List and pick live sessions |
| `/current` | Any | Show current session/task info |
| `/detach` | Regular channel | Disconnect from session |
| `/cancel` | Any | Cancel running operation |
| `/cost` | Any | Show session cost |
| `/new <dir>` | Regular channel | Start a new session |

## Multi-User Workflow

```
/setup (one-time)
    ↓
Creates CLAUDE.md, STATUS.md, NOTES.md in repo
    ↓
/spawn "implement feature X"
    ↓
Creates: forum post + git worktree + branch + Claude session
    ↓
Agent reads CLAUDE.md, STATUS.md, NOTES.md for context
    ↓
Agent works → commits → pushes branch → creates PR → updates STATUS.md
    ↓
Team reviews PR on GitHub
    ↓
(If paper_repo configured) Merge triggers auto paper update
```

### Shared Project Files

| File | Purpose | Updated by |
|------|---------|------------|
| `CLAUDE.md` | Agent instructions, workflow rules | Team leads |
| `STATUS.md` | Active tasks, blockers, decisions | Agent after each task |
| `NOTES.md` | Related work, discussion notes, resources | Anyone via `/note` |

## Architecture

```
main.py              — Entry point: telegram|discord|both
bridge.py            — Claude CLI subprocess wrapper, streaming, permission relay
sessions.py          — Session discovery from ~/.claude/projects/
formatter.py         — Message splitting, Telegram HTML, Discord markdown
message_queue.py     — Per-chat async message queue
telegram_bot.py      — Telegram adapter
discord_bot.py       — Discord adapter with forum channel support
project_config.py    — Channel-project bindings, task tracking
project_scaffold.py  — CLAUDE.md/STATUS.md/NOTES.md generation
worktree.py          — Git worktree management
webhook.py           — GitHub webhook listener
```

## Requirements

- Python 3.11+
- `claude` CLI installed and authenticated
- `gh` CLI installed and authenticated (for PR creation and `/board`)
- Bot must run on the same machine as your Claude Code sessions
