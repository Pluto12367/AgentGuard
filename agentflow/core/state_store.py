"""任务状态持久化：.agentflow/state.json + .agentflow/session.jsonl。

`agentflow start/check/advance/status/test` 通过本模块共享活动任务状态。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from agentflow.core.session import SessionEvent

STATE_DIRNAME = ".agentflow"
STATE_FILENAME = "state.json"
SESSION_FILENAME = "session.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class TaskState:
    """活动任务的持久化状态。"""

    description: str
    size: str  # small / medium / large
    phases: list[str]  # Phase 值序列，如 ["implement", "test", "done"]
    index: int  # 当前所处下标（对应 phases）
    created_at: str
    updated_at: str

    @classmethod
    def create(cls, description: str, size: str, phases: list[str]) -> TaskState:
        now = _now_iso()
        return cls(
            description=description,
            size=size,
            phases=phases,
            index=0,
            created_at=now,
            updated_at=now,
        )

    @property
    def current_phase(self) -> str:
        return self.phases[self.index]

    @property
    def is_finished(self) -> bool:
        return self.current_phase == "done"

    def touch(self) -> None:
        self.updated_at = _now_iso()


def state_dir(root: str | Path) -> Path:
    return Path(root) / STATE_DIRNAME


def state_path(root: str | Path) -> Path:
    return state_dir(root) / STATE_FILENAME


def session_path(root: str | Path) -> Path:
    return state_dir(root) / SESSION_FILENAME


def save_state(root: str | Path, state: TaskState) -> Path:
    """写回 state.json（覆盖），返回文件路径。"""
    target = state_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(asdict(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def load_state(root: str | Path) -> TaskState | None:
    """读取活动任务状态；不存在或损坏时返回 None。"""
    target = state_path(root)
    if not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return TaskState(**data)
    except (json.JSONDecodeError, TypeError):
        return None


def append_event(root: str | Path, event: SessionEvent) -> Path:
    """向 session.jsonl 追加一条事件，返回文件路径。"""
    target = session_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
    return target
