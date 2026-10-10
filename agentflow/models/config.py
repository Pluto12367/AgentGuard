"""agentflow.yaml 的配置模型与加载/保存逻辑。

这是骨架阶段的真实实现：配置 schema 即各模块的契约来源，
guard / testing / generators 的默认行为均以此处默认值为准。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentflow.core.state_machine import (
    CANONICAL_PHASES,
    Phase,
    validate_phase_sequence,
)

#: 约定的配置文件名（位于项目根目录）。
CONFIG_FILENAME = "agentflow.yaml"

#: 危险命令默认拦截清单（子串匹配，不区分大小写）。
#: 命令护栏与配置默认值共用此单一来源。
DEFAULT_BLOCKED_COMMAND_PATTERNS: tuple[str, ...] = (
    "rm -rf /",
    "rm -rf ~",
    "rm -rf /*",
    "git push --force",
    "git push -f",
    "git branch -D main",
    "git clean -fdx",
    "curl | sh",
    "curl | bash",
    "wget | sh",
    "del /s /q",
    "rd /s /q",
    "format c:",
    ":(){ :|:& };:",
)

TaskSize = Literal["small", "medium", "large"]


class ProjectConfig(BaseModel):
    """项目基本信息。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="项目名，`agentflow init` 默认取目录名")
    language: str = Field(default="python", description="主语言，影响规则生成的措辞")


class WorkflowConfig(BaseModel):
    """流程配置：三档规模各自走的阶段序列 + 重试上限。"""

    model_config = ConfigDict(extra="forbid")

    small: list[Phase] = Field(
        default_factory=lambda: [Phase.IMPLEMENT, Phase.TEST, Phase.DONE],
        description="小任务流程：直接实现→测试→完成",
    )
    medium: list[Phase] = Field(
        default_factory=lambda: list(CANONICAL_PHASES),
        description="中任务流程：完整六阶段",
    )
    large: list[Phase] = Field(
        default_factory=lambda: list(CANONICAL_PHASES),
        description="大任务流程：完整六阶段（后续版本附加更严格的产物要求）",
    )
    max_retries: int = Field(
        default=3, ge=0, description="测试失败后打回 Agent 修复的最大次数"
    )

    @field_validator("small", "medium", "large")
    @classmethod
    def _validate_sequence(cls, value: list[Phase]) -> list[Phase]:
        validate_phase_sequence(value)
        return value

    def phases_for(self, size: TaskSize) -> list[Phase]:
        """返回指定规模对应的阶段序列。"""
        return list(getattr(self, size))


class GuardrailConfig(BaseModel):
    """安全护栏配置。"""

    model_config = ConfigDict(extra="forbid")

    protected_files: list[str] = Field(
        default_factory=lambda: [".env", ".env.*", "*.pem", "*.key", CONFIG_FILENAME],
        description="受保护文件（glob）：删除一律拦截，修改需强确认",
    )
    allow_paths: list[str] = Field(
        default_factory=list,
        description="写入白名单（glob）：非空时启用白名单模式，仅匹配的路径可改动",
    )
    deny_paths: list[str] = Field(
        default_factory=lambda: [".git/**", ".agentflow/**"],
        description="写入黑名单（glob）：任何情况下都不允许改动",
    )
    forbid_new_dependencies: bool = Field(
        default=True, description="禁止新增第三方依赖（改动依赖清单文件时拦截）"
    )
    require_diff_preview: bool = Field(
        default=True, description="任何文件修改前必须 diff 预览并确认"
    )
    blocked_commands: list[str] = Field(
        default_factory=lambda: list(DEFAULT_BLOCKED_COMMAND_PATTERNS),
        description="危险命令拦截清单（子串匹配，不区分大小写）",
    )


class TestConfig(BaseModel):
    """测试闭环配置。"""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(default="pytest -q", description="项目测试命令（任意 shell 命令）")
    timeout_seconds: int = Field(default=600, ge=1, description="单次执行超时（秒）")
    coverage: bool = Field(default=False, description="生成覆盖率报告（TODO P1）")


class AgentFlowConfig(BaseModel):
    """agentflow.yaml 的顶层模型。"""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = Field(default=1, description="配置格式版本")
    project: ProjectConfig
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    guardrails: GuardrailConfig = Field(default_factory=GuardrailConfig)
    testing: TestConfig = Field(default_factory=TestConfig)

    @classmethod
    def load(cls, path: str | Path) -> AgentFlowConfig:
        """从 YAML 文件加载并校验配置。"""
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"配置文件格式错误：{path} 的顶层应为映射")
        return cls.model_validate(data)

    @classmethod
    def discover(cls, start: str | Path) -> Path | None:
        """自 start 逐级向上查找 agentflow.yaml，找不到返回 None。"""
        current = Path(start).resolve()
        for candidate in (current, *current.parents):
            target = candidate / CONFIG_FILENAME
            if target.is_file():
                return target
        return None

    def save(self, path: str | Path) -> None:
        """将配置序列化为 YAML 写入文件（覆盖）。"""
        Path(path).write_text(
            yaml.safe_dump(
                self.model_dump(mode="json"),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
