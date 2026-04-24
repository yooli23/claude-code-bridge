"""GitHub webhook listener — auto-spawns paper update tasks on main merge."""

import hashlib
import hmac
import json
import logging
import os

from aiohttp import web

logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "8787"))


class WebhookServer:
    def __init__(self, on_main_push=None):
        self.on_main_push = on_main_push
        self.app = web.Application()
        self.app.router.add_post("/webhook/github", self.handle_github)
        self.app.router.add_get("/health", self.handle_health)

    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        if not WEBHOOK_SECRET:
            return True
        expected = "sha256=" + hmac.new(
            WEBHOOK_SECRET.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def handle_github(self, request: web.Request) -> web.Response:
        payload = await request.read()

        signature = request.headers.get("X-Hub-Signature-256", "")
        if WEBHOOK_SECRET and not self._verify_signature(payload, signature):
            logger.warning("Invalid webhook signature")
            return web.Response(status=401, text="Invalid signature")

        event_type = request.headers.get("X-GitHub-Event", "")
        if event_type != "push":
            return web.json_response({"status": "ignored", "event": event_type})

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")

        ref = data.get("ref", "")
        if ref not in ("refs/heads/main", "refs/heads/master"):
            return web.json_response({"status": "ignored", "ref": ref})

        repo_full_name = data.get("repository", {}).get("full_name", "")
        commits = data.get("commits", [])
        head_commit = data.get("head_commit", {})

        commit_messages = []
        for c in commits:
            msg = c.get("message", "").split("\n")[0]
            sha = c.get("id", "")[:8]
            commit_messages.append(f"{sha}: {msg}")

        pr_info = ""
        head_msg = head_commit.get("message", "")
        if "Merge pull request #" in head_msg:
            pr_info = head_msg.split("\n")[0]

        summary = {
            "repo": repo_full_name,
            "ref": ref,
            "commits": commit_messages,
            "pr_info": pr_info,
            "pusher": data.get("pusher", {}).get("name", "unknown"),
        }

        logger.info(f"Main push detected on {repo_full_name}: {len(commits)} commit(s)")

        if self.on_main_push:
            try:
                await self.on_main_push(summary)
            except Exception as e:
                logger.error(f"Error in on_main_push callback: {e}")

        return web.json_response({"status": "processed", "commits": len(commits)})

    async def start(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
        await site.start()
        logger.info(f"Webhook server listening on port {WEBHOOK_PORT}")
        return runner
