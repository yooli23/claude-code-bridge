"""Git worktree management for isolated agent sessions."""

import asyncio
import logging
import os
import re
import shutil

logger = logging.getLogger(__name__)


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


async def create_worktree(project_dir: str, task_description: str, user_name: str) -> tuple[str, str]:
    """Create a git worktree for an isolated task.

    Returns (worktree_path, branch_name).
    """
    slug = _slugify(task_description)
    user_slug = _slugify(user_name, max_len=15)
    branch_name = f"task/{user_slug}/{slug}"

    worktree_base = os.path.join(project_dir, ".worktrees")
    os.makedirs(worktree_base, exist_ok=True)
    worktree_path = os.path.join(worktree_base, f"{user_slug}-{slug}")

    if os.path.exists(worktree_path):
        counter = 2
        while os.path.exists(f"{worktree_path}-{counter}"):
            counter += 1
        worktree_path = f"{worktree_path}-{counter}"
        branch_name = f"{branch_name}-{counter}"

    # Clean up stale branch if it exists (from a previous failed attempt)
    proc = await asyncio.create_subprocess_exec(
        "git", "branch", "-D", branch_name,
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    await asyncio.create_subprocess_exec(
        "git", "worktree", "prune",
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "add", "-b", branch_name, worktree_path,
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"Failed to create worktree: {err}")

    logger.info(f"Created worktree at {worktree_path} on branch {branch_name}")
    return worktree_path, branch_name


async def remove_worktree(project_dir: str, worktree_path: str):
    """Remove a git worktree and its branch."""
    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "remove", worktree_path, "--force",
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    if proc.returncode != 0:
        if os.path.exists(worktree_path):
            shutil.rmtree(worktree_path, ignore_errors=True)
        await asyncio.create_subprocess_exec(
            "git", "worktree", "prune",
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    logger.info(f"Removed worktree at {worktree_path}")


async def list_worktrees(project_dir: str) -> list[dict]:
    """List all worktrees for a project."""
    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "list", "--porcelain",
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return []

    worktrees = []
    current = {}
    for line in stdout.decode().splitlines():
        if not line.strip():
            if current:
                worktrees.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line[9:]
        elif line.startswith("branch "):
            current["branch"] = line[7:]
        elif line == "bare":
            current["bare"] = True

    if current:
        worktrees.append(current)

    return worktrees
