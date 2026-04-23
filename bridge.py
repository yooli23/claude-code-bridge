"""Bridge to Claude Code CLI — send messages to sessions and stream responses."""

import asyncio
import json
import logging
import os
import re
import signal
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

COST_THRESHOLDS = [1.0, 5.0, 10.0, 25.0]

_XML_ATTR_ESCAPE = str.maketrans({
    "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;",
})


def wrap_channel_message(
    content: str,
    source: str,
    user: str = "",
    chat_id: str = "",
    **extra_meta: str,
) -> str:
    attrs = f'source="{source.translate(_XML_ATTR_ESCAPE)}"'
    if user:
        attrs += f' user="{user.translate(_XML_ATTR_ESCAPE)}"'
    if chat_id:
        attrs += f' chat_id="{chat_id.translate(_XML_ATTR_ESCAPE)}"'
    for k, v in extra_meta.items():
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", k):
            attrs += f' {k}="{str(v).translate(_XML_ATTR_ESCAPE)}"'
    return f"<channel {attrs}>{content}</channel>"


@dataclass
class PermissionRequest:
    """A permission prompt from Claude waiting for user approval."""
    request_id: str
    tool_name: str
    tool_input: dict
    tool_use_id: str
    description: str = ""

    @property
    def preview(self) -> str:
        """Human-readable preview of what the tool wants to do."""
        desc = self.tool_input.get("description", "")
        cmd = self.tool_input.get("command", "")
        path = self.tool_input.get("file_path", "")
        content = desc or cmd or path
        if content and len(content) > 200:
            content = content[:197] + "..."
        return content or self.tool_name


@dataclass
class SessionCostTracker:
    costs: dict[str, float] = field(default_factory=dict)
    alerted: dict[str, set] = field(default_factory=dict)

    def add(self, session_id: str, cost: float) -> float | None:
        if session_id not in self.costs:
            self.costs[session_id] = 0.0
            self.alerted[session_id] = set()

        prev = self.costs[session_id]
        self.costs[session_id] += cost

        for threshold in COST_THRESHOLDS:
            if prev < threshold <= self.costs[session_id]:
                if threshold not in self.alerted[session_id]:
                    self.alerted[session_id].add(threshold)
                    return threshold
        return None

    def get(self, session_id: str) -> float:
        return self.costs.get(session_id, 0.0)


class ClaudeBridge:
    def __init__(
        self,
        claude_bin: str = "claude",
        permission_mode: str = "bypassPermissions",
    ):
        self.claude_bin = claude_bin
        self.permission_mode = permission_mode
        self.cost_tracker = SessionCostTracker()
        self._active_processes: dict[int, asyncio.subprocess.Process] = {}
        self._pending_permissions: dict[str, PermissionRequest] = {}

    async def cancel(self, chat_id: int) -> bool:
        proc = self._active_processes.get(chat_id)
        if proc and proc.returncode is None:
            try:
                proc.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    proc.kill()
            except ProcessLookupError:
                pass
            self._active_processes.pop(chat_id, None)
            return True
        return False

    def is_busy(self, chat_id: int) -> bool:
        proc = self._active_processes.get(chat_id)
        return proc is not None and proc.returncode is None

    async def respond_permission(self, chat_id: int, request_id: str, allow: bool, message: str = "") -> bool:
        """Send a permission response to a pending permission request."""
        proc = self._active_processes.get(chat_id)
        if not proc or proc.returncode is not None or not proc.stdin:
            return False

        perm = self._pending_permissions.pop(request_id, None)
        if not perm:
            return False

        if allow:
            response = {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "request_id": request_id,
                    "response": {
                        "behavior": "allow",
                        "updatedInput": {},
                        "toolUseID": perm.tool_use_id,
                    },
                },
            }
        else:
            response = {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "request_id": request_id,
                    "response": {
                        "behavior": "deny",
                        "message": message or "Denied by user",
                        "toolUseID": perm.tool_use_id,
                    },
                },
            }

        try:
            line = json.dumps(response) + "\n"
            proc.stdin.write(line.encode())
            await proc.stdin.drain()
            logger.info(f"Permission {'allowed' if allow else 'denied'} for {perm.tool_name} ({request_id})")
            return True
        except Exception as e:
            logger.error(f"Failed to send permission response: {e}")
            return False

    def _uses_interactive_permissions(self) -> bool:
        return self.permission_mode not in ("bypassPermissions", "plan", "dontAsk")

    async def send_message(
        self,
        session_id: str,
        message: str,
        cwd: str | None = None,
        chat_id: int | None = None,
        on_delta: callable = None,
        on_cost_threshold: callable = None,
        on_compaction: callable = None,
        on_permission_request: callable = None,
    ) -> str:
        """Send a message to a Claude Code session and return the full response.

        on_delta(text_so_far, tool_status)
        on_cost_threshold(total, threshold)
        on_compaction()
        on_permission_request(PermissionRequest) — called when Claude needs permission
        """
        interactive_perms = self._uses_interactive_permissions() and on_permission_request is not None
        use_stdin = interactive_perms

        if use_stdin:
            cmd = [
                self.claude_bin,
                "--resume", session_id,
                "--permission-mode", self.permission_mode,
                "--output-format", "stream-json",
                "--input-format", "stream-json",
                "--verbose",
                "--print",
            ]
        else:
            cmd = [
                self.claude_bin,
                "--resume", session_id,
                "--permission-mode", self.permission_mode,
                "--output-format", "stream-json",
                "--verbose",
                "--include-partial-messages",
                "--print",
                message,
            ]

        if self.permission_mode == "bypassPermissions":
            cmd.insert(1, "--allow-dangerously-skip-permissions")

        logger.info(f"Running: {' '.join(cmd[:6])}... (interactive_perms={interactive_perms})")

        env = os.environ.copy()
        env["IS_SANDBOX"] = "1"

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if use_stdin else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=cwd,
        )

        if chat_id is not None:
            self._active_processes[chat_id] = process

        # If using stdin mode, send the user message via stdin
        if use_stdin and process.stdin:
            user_msg = {
                "type": "user",
                "session_id": session_id,
                "message": {
                    "role": "user",
                    "content": message,
                },
                "parent_tool_use_id": None,
            }
            try:
                line = json.dumps(user_msg) + "\n"
                process.stdin.write(line.encode())
                await process.stdin.drain()
            except Exception as e:
                logger.error(f"Failed to write message to stdin: {e}")

        full_text = ""
        result_text = ""
        tool_status = ""

        try:
            async for line in process.stdout:
                line = line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                if event_type == "stream_event":
                    inner = event.get("event", {})
                    inner_type = inner.get("type", "")

                    if inner_type == "content_block_start":
                        block = inner.get("content_block", {})
                        if block.get("type") == "tool_use":
                            tool_name = block.get("name", "tool")
                            tool_status = f"Running {tool_name}..."
                            if on_delta:
                                await on_delta(full_text, tool_status)

                    elif inner_type == "content_block_delta":
                        delta = inner.get("delta", {})
                        if delta.get("type") == "text_delta":
                            full_text += delta["text"]
                            if on_delta:
                                await on_delta(full_text, tool_status)

                elif event_type == "assistant":
                    content = event.get("message", {}).get("content", [])
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            tool_name = block.get("name", "tool")
                            tool_input = block.get("input", {})
                            desc = tool_input.get("description", "")
                            cmd_str = tool_input.get("command", "")
                            detail = desc or cmd_str
                            if detail and len(detail) > 80:
                                detail = detail[:77] + "..."
                            tool_status = (
                                f"{tool_name}: {detail}" if detail
                                else f"Running {tool_name}..."
                            )
                            if on_delta:
                                await on_delta(full_text, tool_status)
                        elif block.get("type") == "text":
                            text = block.get("text", "")
                            if text and not full_text:
                                full_text = text

                elif event_type == "user":
                    tool_status = ""
                    if on_delta and full_text:
                        await on_delta(full_text, "")

                elif event_type == "result":
                    result_text = event.get("result", full_text)
                    cost = event.get("cost_usd")
                    if cost is not None:
                        logger.info(f"Cost: ${cost:.4f}")
                        threshold = self.cost_tracker.add(session_id, cost)
                        if threshold is not None and on_cost_threshold:
                            total = self.cost_tracker.get(session_id)
                            await on_cost_threshold(total, threshold)

                elif event_type == "control_request":
                    request = event.get("request", {})
                    if request.get("subtype") == "can_use_tool" and on_permission_request:
                        perm = PermissionRequest(
                            request_id=event.get("request_id", ""),
                            tool_name=request.get("tool_name", "unknown"),
                            tool_input=request.get("input", {}),
                            tool_use_id=request.get("tool_use_id", ""),
                            description=request.get("description", ""),
                        )
                        self._pending_permissions[perm.request_id] = perm
                        tool_status = f"Permission needed: {perm.tool_name}"
                        if on_delta:
                            await on_delta(full_text, tool_status)
                        await on_permission_request(perm)

                elif event_type == "system":
                    sys_type = event.get("subtype", "")
                    if sys_type in ("compact", "compaction", "context_compaction"):
                        logger.info("Context compaction detected")
                        if on_compaction:
                            await on_compaction()
                    sys_msg = event.get("message", "")
                    if "compact" in sys_msg.lower():
                        logger.info(f"Compaction event: {sys_msg}")
                        if on_compaction:
                            await on_compaction()

        except Exception as e:
            logger.error(f"Error reading stream: {e}")

        finally:
            if chat_id is not None:
                self._active_processes.pop(chat_id, None)

        await process.wait()

        if process.returncode != 0:
            stderr = await process.stderr.read()
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            if err_msg:
                logger.error(f"Claude stderr: {err_msg}")
            if process.returncode == -signal.SIGTERM:
                return "(cancelled)"
            if not result_text and not full_text:
                return f"Error: Claude exited with code {process.returncode}\n{err_msg}"

        return result_text or full_text or "(no response)"
