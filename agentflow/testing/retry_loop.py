"""测试闭环：失败自动打回 Agent 修复，直至通过或达到最大重试。

对应 MVP P0「测试闭环——失败重试」。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agentflow.testing.runner import TestReport, TestRunner

#: request_fix 回调：收到失败报告，负责把「失败证据 + 修复指令」交给 Agent。
FixRequester = Callable[[TestReport], None]

#: 每次执行后的回调（用于写证据 / 记日志）；参数为 (报告, 第几次执行)。
AttemptHook = Callable[[TestReport, int], None]


@dataclass(frozen=True)
class RetryOutcome:
    """闭环的整体结果。"""

    attempts: int  # 总执行次数（含首次）
    fixed: bool  # 是否最终通过
    final_report: TestReport | None


class RepairLoop:
    """「执行 → 失败打回 → 再执行」的驱动循环。"""

    def __init__(self, runner: TestRunner, max_retries: int) -> None:
        self._runner = runner
        self._max_retries = max_retries

    @property
    def max_retries(self) -> int:
        return self._max_retries

    def run(
        self,
        request_fix: FixRequester,
        on_attempt: AttemptHook | None = None,
    ) -> RetryOutcome:
        """驱动闭环直至通过或重试耗尽。

        首次执行失败后，每次将失败报告交给 request_fix（由上层转述给
        Agent），随后重新执行；总执行次数不超过 1 + max_retries。
        on_attempt 在每次执行后立即调用（写证据 / 记日志），早于 request_fix。
        """
        attempts = 0
        while True:
            report = self._runner.run()
            attempts += 1
            if on_attempt is not None:
                on_attempt(report, attempts)
            if report.passed:
                return RetryOutcome(attempts=attempts, fixed=True, final_report=report)
            if attempts >= self._max_retries + 1:
                return RetryOutcome(attempts=attempts, fixed=False, final_report=report)
            request_fix(report)
