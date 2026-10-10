"""核心模块：流程状态机、产物校验、任务路由、会话日志。"""

from agentflow.core.state_machine import (
    CANONICAL_PHASES,
    ArtifactSpec,
    Phase,
    TransitionResult,
    WorkflowStateMachine,
)

__all__ = [
    "CANONICAL_PHASES",
    "ArtifactSpec",
    "Phase",
    "TransitionResult",
    "WorkflowStateMachine",
]
