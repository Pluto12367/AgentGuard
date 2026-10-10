"""护栏引擎：文件保护、危险命令拦截、diff 预览确认的统一入口。

对应 MVP P0「安全护栏」。Agent 的所有写操作与命令执行都应先经过本引擎裁决。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Sequence

from agentflow.guard.command_rules import CommandRuleSet
from agentflow.guard.file_rules import FileRuleSet
from agentflow.models.config import GuardrailConfig

if TYPE_CHECKING:  # 仅类型标注，避免与 diff_preview 循环导入
    from agentflow.guard.diff_preview import ApprovalResult

ChangeType = Literal["create", "modify", "delete"]


@dataclass(frozen=True)
class FileChange:
    """一次待执行的文件改动（path 相对项目根）。"""

    path: Path
    change_type: ChangeType


@dataclass(frozen=True)
class GuardResult:
    """护栏裁决结果。

    rule_id：命中规则的标识（如 "deny_paths" / "blocked_commands"），
    放行且无特别提示时为 "ok"。
    """

    allowed: bool
    rule_id: str
    reason: str

    @classmethod
    def ok(cls, reason: str = "") -> GuardResult:
        return cls(allowed=True, rule_id="ok", reason=reason)


class GuardrailEngine:
    """组合文件规则、命令规则与 diff 预览的统一裁决入口。"""

    def __init__(self, root: Path, config: GuardrailConfig) -> None:
        self._root = Path(root)
        self._config = config
        self._files = FileRuleSet(config)
        self._commands = CommandRuleSet(config.blocked_commands)

    def check_file_change(self, change: FileChange) -> GuardResult:
        """裁决一次文件改动（按优先级）：

        1. deny_paths 命中 → 拦截；
        2. delete 且 protected_files 命中 → 拦截；
        3. allow_paths 非空且未命中 → 拦截（白名单模式）；
        4. forbid_new_dependencies 且改动的是依赖清单 → 拦截（需用户确认）；
        5. protected 的 create/modify → 放行但标记 rule_id=protected_files
           （强确认由 diff 预览环节承担）；
        6. 其余 → 放行。
        """
        rel = change.path
        rules = self._files

        if rules.matches_any(rel, self._config.deny_paths):
            return GuardResult(False, "deny_paths", f"路径在黑名单中，禁止改动：{rel.as_posix()}")

        if change.change_type == "delete" and rules.matches_any(rel, self._config.protected_files):
            return GuardResult(
                False, "protected_files", f"受保护文件禁止删除：{rel.as_posix()}"
            )

        if self._config.allow_paths and not rules.matches_any(rel, self._config.allow_paths):
            return GuardResult(
                False,
                "allow_paths",
                f"白名单模式：仅允许改动 {self._config.allow_paths}，未命中 {rel.as_posix()}",
            )

        if self._config.forbid_new_dependencies and rules.is_dependency_manifest(rel):
            return GuardResult(
                False,
                "forbid_new_dependencies",
                f"依赖清单改动需用户确认（如确需新增依赖，在 agentflow.yaml 中调整 "
                f"forbid_new_dependencies 后放行）：{rel.as_posix()}",
            )

        if rules.matches_any(rel, self._config.protected_files):
            return GuardResult(
                True,
                "protected_files",
                f"受保护文件将被{ {'create': '创建', 'modify': '修改', 'delete': '删除'}[change.change_type] }，"
                f"diff 预览时需强确认：{rel.as_posix()}",
            )

        return GuardResult.ok()

    def check_command(self, command: str) -> GuardResult:
        """裁决一条 shell 命令（子串匹配 blocked_commands，不区分大小写）。"""
        hit = self._commands.match(command)
        if hit is not None:
            return GuardResult(False, "blocked_commands", f"命中危险命令模式：{hit!r}")
        return GuardResult.ok()

    def preview_and_confirm(self, changes: Sequence[FileChange]) -> ApprovalResult:
        """对一组改动生成 diff 预览并请求确认。

        require_diff_preview=false 时直接放行（method=skipped）。
        """
        if not self._config.require_diff_preview:
            from agentflow.guard.diff_preview import ApprovalResult

            return ApprovalResult(approved=True, method="skipped")

        from agentflow.guard.diff_preview import DiffPreviewer

        previewer = DiffPreviewer(self._root)
        preview = previewer.build_preview(changes)
        return previewer.request_approval(preview)
