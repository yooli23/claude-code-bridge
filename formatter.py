"""Format Claude Code output for chat platforms (Telegram HTML, Discord Markdown)."""

import re
from dataclasses import dataclass

TELEGRAM_MAX_LEN = 4096
DISCORD_MAX_LEN = 2000


@dataclass
class FormattedChunk:
    text: str
    parse_mode: str | None = None


def _find_split_point(text: str, limit: int) -> int:
    """Find a natural split point (paragraph, line, or word boundary) before limit."""
    if len(text) <= limit:
        return len(text)

    # Try splitting at a double newline (paragraph boundary)
    idx = text.rfind("\n\n", 0, limit)
    if idx > limit // 2:
        return idx + 2

    # Try splitting at a single newline
    idx = text.rfind("\n", 0, limit)
    if idx > limit // 2:
        return idx + 1

    # Try splitting at a space (word boundary)
    idx = text.rfind(" ", 0, limit)
    if idx > limit // 2:
        return idx + 1

    # Hard cut
    return limit


def split_message(text: str, limit: int) -> list[str]:
    """Split text into chunks that fit within the platform's message size limit."""
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = _find_split_point(remaining, limit)
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]

    return chunks


_HTML_ESCAPE = str.maketrans({"<": "&lt;", ">": "&gt;", "&": "&amp;"})


def _escape_html(text: str) -> str:
    return text.translate(_HTML_ESCAPE)


def format_telegram_html(text: str) -> list[FormattedChunk]:
    """Convert Claude's markdown-ish output to Telegram HTML chunks.

    Handles code blocks (``` → <pre>), inline code (` → <code>),
    bold (** → <b>), and escapes HTML entities in normal text.
    """
    result = []
    parts = re.split(r"(```[\s\S]*?```)", text)

    converted = []
    for part in parts:
        if part.startswith("```") and part.endswith("```"):
            inner = part[3:-3]
            # Strip optional language tag on first line
            if "\n" in inner:
                first_line, rest = inner.split("\n", 1)
                if first_line.strip().isalnum():
                    inner = rest
                else:
                    inner = inner
            converted.append(f"<pre>{_escape_html(inner.strip())}</pre>")
        else:
            escaped = _escape_html(part)
            # Inline code
            escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
            # Bold
            escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
            converted.append(escaped)

    full_html = "".join(converted)

    for chunk in split_message(full_html, TELEGRAM_MAX_LEN):
        result.append(FormattedChunk(text=chunk, parse_mode="HTML"))

    return result


def format_discord(text: str) -> list[FormattedChunk]:
    """Split Claude output for Discord. Markdown passes through natively."""
    chunks = split_message(text, DISCORD_MAX_LEN)
    return [FormattedChunk(text=c) for c in chunks]


def format_plain(text: str, limit: int) -> list[FormattedChunk]:
    """Plain text fallback — split only."""
    return [FormattedChunk(text=c) for c in split_message(text, limit)]


def format_tool_status(tool_name: str, detail: str = "") -> str:
    """Format a tool execution status line."""
    if detail:
        if len(detail) > 80:
            detail = detail[:77] + "..."
        return f"[{tool_name}: {detail}]"
    return f"[Running {tool_name}...]"
