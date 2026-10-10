"""Cursor rules 生成器：产出 .cursor/rules/agentflow.mdc。

对应 MVP P1；模板位于 agentflow/templates/cursor_rules.mdc.j2。
"""

from __future__ import annotations

from pathlib import Path

from agentflow.generators.scanner import ProjectProfile
from agentflow.models.config import AgentFlowConfig


class CursorRulesGenerator:
    """渲染 Cursor 规则文件（MDC 格式：frontmatter + 正文）。"""

    def __init__(
        self,
        profile: ProjectProfile,
        config: AgentFlowConfig | None = None,
    ) -> None:
        self._profile = profile
        self._config = config

    def render(self) -> str:
        """渲染 .mdc 全文。

        契约：frontmatter 含 description / globs / alwaysApply，
        正文与 AGENTS.md 的流程、安全、测试约束保持同源。
        """
        raise NotImplementedError("TODO(P1): Jinja2 渲染 cursor_rules.mdc.j2")

    def write_to(self, target: Path) -> Path:
        """写入目标路径（默认 <root>/.cursor/rules/agentflow.mdc）。"""
        raise NotImplementedError("TODO(P1): 创建目录 + 写盘")
