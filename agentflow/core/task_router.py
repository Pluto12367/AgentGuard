"""任务规模路由：Small / Medium / Large 自动选择流程。

对应 MVP P0：任务自动路由。规模判定依据 TaskProfile 的信号
（预计改动文件数、是否动公共 API、是否引入新依赖）。
"""

from __future__ import annotations

from dataclasses import dataclass

from agentflow.core.state_machine import Phase
from agentflow.models.config import TaskSize, WorkflowConfig

#: 预计改动文件数 ≤ 该值且无放大信号 → small。
SMALL_MAX_FILES = 2
#: 预计改动文件数 ≥ 该值 → large（优先级高于其他信号）。
LARGE_MIN_FILES = 10


@dataclass(frozen=True)
class TaskProfile:
    """任务画像：路由依据，由调用方（CLI 或 Agent 桥）填写。"""

    description: str
    estimated_files: int = 0
    touches_public_api: bool = False
    requires_new_dependency: bool = False


class TaskRouter:
    """按任务画像选择 small / medium / large 流程。"""

    def __init__(self, workflow: WorkflowConfig) -> None:
        self._workflow = workflow

    def size_of(self, task: TaskProfile) -> TaskSize:
        """判定任务规模。

        规则（从上到下首个命中生效）：
        1. 改动文件数达到 large 阈值 → large；
        2. 动公共 API 或引入新依赖 → 至少 medium（信号未知风险，不路由 small）；
        3. 改动文件数 ≤ small 阈值 → small；
        4. 其余 → medium。
        """
        if task.estimated_files >= LARGE_MIN_FILES:
            return "large"
        if task.touches_public_api or task.requires_new_dependency:
            return "medium"
        if task.estimated_files <= SMALL_MAX_FILES:
            return "small"
        return "medium"

    def route(self, task: TaskProfile) -> list[Phase]:
        """返回该任务应走的阶段序列。

        显式 size 由 CLI 层直接指定，不经过本方法。
        """
        return self._workflow.phases_for(self.size_of(task))
