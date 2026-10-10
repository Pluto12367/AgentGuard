"""危险命令拦截规则。"""

from __future__ import annotations

from typing import Sequence

from agentflow.models.config import DEFAULT_BLOCKED_COMMAND_PATTERNS


class CommandRuleSet:
    """按子串模式（不区分大小写）匹配 shell 命令。"""

    def __init__(self, patterns: Sequence[str] = DEFAULT_BLOCKED_COMMAND_PATTERNS) -> None:
        self._patterns = tuple(patterns)

    @property
    def patterns(self) -> tuple[str, ...]:
        return self._patterns

    def match(self, command: str) -> str | None:
        """返回命中的第一条模式；未命中返回 None。"""
        lowered = command.lower()
        for pattern in self._patterns:
            if pattern.lower() in lowered:
                return pattern
        return None
