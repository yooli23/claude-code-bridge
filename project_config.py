"""Project configuration — binds Discord forum channels to project repos."""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(os.path.expanduser("~/.claude-bridge"))
CONFIG_FILE = CONFIG_DIR / "projects.json"


@dataclass
class ProjectBinding:
    channel_id: int
    project_dir: str
    code_repo: str = ""
    paper_repo: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectBinding":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TaskInfo:
    thread_id: int
    session_id: str
    worktree_path: str
    branch_name: str
    user_id: int
    user_name: str
    description: str
    status: str = "active"
    project_dir: str = ""


class ProjectConfigStore:
    def __init__(self):
        self._bindings: dict[int, ProjectBinding] = {}
        self._tasks: dict[int, TaskInfo] = {}
        self._load()

    def _load(self):
        if not CONFIG_FILE.exists():
            return
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            for item in data.get("projects", []):
                binding = ProjectBinding.from_dict(item)
                self._bindings[binding.channel_id] = binding
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load project config: {e}")

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {"projects": [b.to_dict() for b in self._bindings.values()]}
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def bind(self, channel_id: int, project_dir: str, code_repo: str = "", paper_repo: str = "") -> ProjectBinding:
        binding = ProjectBinding(
            channel_id=channel_id,
            project_dir=project_dir,
            code_repo=code_repo,
            paper_repo=paper_repo,
        )
        self._bindings[channel_id] = binding
        self._save()
        return binding

    def get_binding(self, channel_id: int) -> ProjectBinding | None:
        return self._bindings.get(channel_id)

    def get_binding_for_thread(self, thread_parent_id: int) -> ProjectBinding | None:
        return self._bindings.get(thread_parent_id)

    def unbind(self, channel_id: int) -> bool:
        if channel_id in self._bindings:
            del self._bindings[channel_id]
            self._save()
            return True
        return False

    def add_task(self, task: TaskInfo):
        self._tasks[task.thread_id] = task

    def get_task(self, thread_id: int) -> TaskInfo | None:
        return self._tasks.get(thread_id)

    def get_tasks_for_channel(self, channel_id: int) -> list[TaskInfo]:
        binding = self._bindings.get(channel_id)
        if not binding:
            return []
        return [
            t for t in self._tasks.values()
            if t.project_dir == binding.project_dir
        ]

    def update_task_status(self, thread_id: int, status: str):
        task = self._tasks.get(thread_id)
        if task:
            task.status = status

    def remove_task(self, thread_id: int):
        self._tasks.pop(thread_id, None)
