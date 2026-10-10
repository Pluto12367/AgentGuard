"""会话日志：完整记录每次 Agent 操作与证据。

运行时数据写入项目根的 .agentflow/ 目录（JSONL，一行一个事件）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

Actor = Literal["agent", "user", "agentflow"]


@dataclass(frozen=True)
class SessionEvent:
    """一条不可变的操作记录。"""

    timestamp: str  # ISO 8601 UTC
    phase: str  # 记录发生时所处的阶段（或 "setup"）
    actor: Actor
    action: str  # 如 "advance_request" / "guard_denied" / "test_failed"
    detail: str = ""

    @classmethod
    def now(cls, phase: str, actor: Actor, action: str, detail: str = "") -> SessionEvent:
        """以当前时间构造事件。"""
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            phase=phase,
            actor=actor,
            action=action,
            detail=detail,
        )


class SessionLog:
    """内存中的会话事件序列，可追加持久化为 JSONL。"""

    def __init__(self) -> None:
        self._events: list[SessionEvent] = []

    @property
    def events(self) -> tuple[SessionEvent, ...]:
        return tuple(self._events)

    def record(self, event: SessionEvent) -> None:
        """追加一条事件。"""
        self._events.append(event)

    def save(self, path: Path) -> Path:
        """以追加方式写入 JSONL（每行一个事件），返回文件路径。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for event in self._events:
                f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        self._events.clear()
        return path
