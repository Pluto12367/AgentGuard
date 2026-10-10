"""流程状态机：阶段枚举与流转契约。

对应 MVP P0「流程状态机——强制阶段流转 + 产物检查」。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # 避免与 core.artifacts 的循环导入，仅用于类型标注
    from agentflow.core.artifacts import ArtifactValidator


class Phase(str, Enum):
    """任务生命周期的六个阶段。"""

    ANALYZE = "analyze"
    DESIGN = "design"
    IMPLEMENT = "implement"
    TEST = "test"
    REVIEW = "review"
    DONE = "done"


#: 完整流程的规范阶段顺序（Medium / Large 任务使用）。
CANONICAL_PHASES: tuple[Phase, ...] = (
    Phase.ANALYZE,
    Phase.DESIGN,
    Phase.IMPLEMENT,
    Phase.TEST,
    Phase.REVIEW,
    Phase.DONE,
)


def validate_phase_sequence(phases: Sequence[Phase]) -> None:
    """校验一段阶段序列的合法性，非法则抛 ValueError。

    规则：非空、无重复、必须以 done 结尾。
    配置模型（models.config）与状态机构造共用此校验，保证两处约束一致。
    """
    if not phases:
        raise ValueError("阶段序列不能为空")
    if len(set(phases)) != len(phases):
        raise ValueError("阶段序列存在重复阶段")
    if phases[-1] is not Phase.DONE:
        raise ValueError("阶段序列必须以 done 结尾")


@dataclass(frozen=True)
class ArtifactSpec:
    """某个阶段必须产出的产物规格。

    path_patterns 为相对项目根目录的 glob 模式（如 ``docs/design/*.md``）。
    required 为 False 时缺失只告警、不拦截进入下一阶段。
    """

    phase: Phase
    description: str
    path_patterns: tuple[str, ...] = ()
    required: bool = True


@dataclass(frozen=True)
class TransitionResult:
    """一次阶段流转的裁决结果。"""

    from_phase: Phase
    to_phase: Phase
    allowed: bool
    reason: str
    missing_artifacts: tuple[str, ...] = ()


class WorkflowStateMachine:
    """强制按既定阶段序列推进的状态机。

    只允许顺序前进：不允许跳阶段，也不允许回退（测试失败的打回重试由
    testing.retry_loop 负责，不通过状态机回退实现）。进入下一阶段前，
    若当前阶段配置了产物规格且提供了校验器，必须通过产物检查。
    """

    def __init__(
        self,
        phases: Sequence[Phase],
        artifact_specs: Sequence[ArtifactSpec] = (),
        validator: ArtifactValidator | None = None,
        start_index: int = 0,
    ) -> None:
        validate_phase_sequence(phases)
        if not 0 <= start_index < len(phases):
            raise ValueError(f"start_index 越界：{start_index}（共 {len(phases)} 个阶段）")
        self._phases: list[Phase] = list(phases)
        self._artifact_specs: tuple[ArtifactSpec, ...] = tuple(artifact_specs)
        self._validator = validator
        self._index = start_index

    @property
    def phases(self) -> tuple[Phase, ...]:
        """本任务要走的完整阶段序列。"""
        return tuple(self._phases)

    @property
    def current_phase(self) -> Phase:
        """当前所处阶段。"""
        return self._phases[self._index]

    @property
    def is_finished(self) -> bool:
        return self.current_phase is Phase.DONE

    def specs_for(self, phase: Phase) -> tuple[ArtifactSpec, ...]:
        """返回指定阶段的全部产物规格。"""
        return tuple(spec for spec in self._artifact_specs if spec.phase is phase)

    def advance(self) -> TransitionResult:
        """请求进入下一阶段。

        先校验当前阶段的产物是否齐备（仅当配置了规格且提供了校验器），
        全部满足才放行；拦截时 TransitionResult.allowed 为 False 并列出
        缺失产物。任务已处于 done 时拒绝推进。
        """
        current = self.current_phase
        if self.is_finished:
            return TransitionResult(current, current, False, "任务已完成（done），没有后续阶段")

        next_phase = self._phases[self._index + 1]
        if self._validator is not None:
            specs = self.specs_for(current)
            if specs:
                check = self._validator.check(current)
                if check.missing:
                    return TransitionResult(
                        from_phase=current,
                        to_phase=next_phase,
                        allowed=False,
                        reason="当前阶段产物不齐备",
                        missing_artifacts=check.missing,
                    )

        self._index += 1
        return TransitionResult(
            from_phase=current,
            to_phase=self.current_phase,
            allowed=True,
            reason="阶段产物齐备，放行",
        )
