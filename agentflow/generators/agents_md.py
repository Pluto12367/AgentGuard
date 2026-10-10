"""AGENTS.md 生成器。

基础版（P0）：扫描画像 + 配置 → 渲染内置模板，写入项目根。
模板位于 agentflow/templates/agents_md.md.j2，随包分发。
"""

from __future__ import annotations

from datetime import date
from importlib import resources
from pathlib import Path

from jinja2 import Template

from agentflow import __version__
from agentflow.core.artifacts import DEFAULT_ARTIFACT_SPECS
from agentflow.core.state_machine import Phase
from agentflow.generators.scanner import ProjectProfile
from agentflow.models.config import AgentFlowConfig, ProjectConfig

TEMPLATE_NAME = "agents_md.md.j2"


def _load_template_source() -> str:
    return resources.files("agentflow.templates").joinpath(TEMPLATE_NAME).read_text("utf-8")


class AgentsMdGenerator:
    """渲染 AGENTS.md（六段式：概述/技术栈/规范/阶段产物/安全约束/测试要求）。"""

    def __init__(
        self,
        profile: ProjectProfile,
        config: AgentFlowConfig | None = None,
    ) -> None:
        self._profile = profile
        self._config = config

    def _context(self) -> dict[str, object]:
        cfg = self._config or AgentFlowConfig(
            project=ProjectConfig(name=self._profile.project_name)
        )
        guard = cfg.guardrails

        phases_ctx: list[dict[str, object]] = []
        for phase in cfg.workflow.medium:
            descriptions = [spec.description for spec in DEFAULT_ARTIFACT_SPECS if spec.phase is phase]
            phases_ctx.append(
                {
                    "name": phase.value,
                    "artifacts": descriptions or ["（无强制产物）"],
                }
            )

        languages = list(self._profile.languages) or [cfg.project.language]
        return {
            "project_name": self._profile.project_name,
            "agentflow_version": __version__,
            "generated_at": date.today().isoformat(),
            "language": cfg.project.language,
            "languages": languages,
            "package_managers": list(self._profile.package_managers),
            "test_frameworks": list(self._profile.test_frameworks),
            "build_tools": list(self._profile.build_tools),
            "phases": phases_ctx,
            "protected_files": guard.protected_files,
            "deny_paths": guard.deny_paths,
            "allow_paths": guard.allow_paths,
            "forbid_new_dependencies": guard.forbid_new_dependencies,
            "require_diff_preview": guard.require_diff_preview,
            "blocked_commands_sample": guard.blocked_commands[:5],
            "test_command": cfg.testing.command,
            "max_retries": cfg.workflow.max_retries,
        }

    def render(self) -> str:
        """渲染完整 AGENTS.md 文本。"""
        template = Template(
            _load_template_source(), trim_blocks=True, lstrip_blocks=True
        )
        text = template.render(**self._context())
        return text if text.endswith("\n") else text + "\n"

    def write_to(self, target: Path, *, overwrite: bool = False) -> Path:
        """写入目标路径（默认项目根的 AGENTS.md），返回写入的文件。

        目标已存在且未指定 overwrite 时抛 FileExistsError（避免覆盖
        手工维护的规则文件；增量更新属 P1）。
        """
        if target.exists() and not overwrite:
            raise FileExistsError(f"{target} 已存在；overwrite=True 覆盖，或手工合并后重试")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render(), encoding="utf-8")
        return target
