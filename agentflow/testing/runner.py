"""测试执行器：按配置命令运行项目测试。

对应 MVP P0「测试闭环——自动执行项目测试命令」。
跨平台注意：命令经 shell 执行（Windows 为 cmd.exe），输出统一按 UTF-8 容错解码。
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from agentflow.models.config import TestConfig

#: 失败证据保留的输出尾部行数。
FAILURE_EXCERPT_LINES = 30


@dataclass(frozen=True)
class TestReport:
    """一次测试执行的完整报告（成功证据 / 失败证据的载体）。"""

    command: str
    passed: bool
    exit_code: int | None  # None 表示超时或未能启动
    duration_seconds: float
    output: str
    timed_out: bool = False

    @property
    def failure_excerpt(self) -> str | None:
        """失败证据：输出尾部摘要，用于打回 Agent 修复。"""
        if self.passed or not self.output:
            return None
        lines = self.output.strip().splitlines()
        return "\n".join(lines[-FAILURE_EXCERPT_LINES:])

    def to_json(self) -> str:
        """序列化为 JSON（写入 .agentflow/test-report.json 时的格式）。"""
        import json

        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


class TestRunner:
    """subprocess 执行配置中的测试命令并产出报告。"""

    def __init__(self, root: Path, config: TestConfig) -> None:
        self._root = Path(root)
        self._config = config

    @property
    def root(self) -> Path:
        return self._root

    def run(self) -> TestReport:
        """执行测试命令。

        在项目根目录执行 config.command；超时（timeout_seconds）计为失败
        且 timed_out=True；退出码 0 视为通过。输出全文保留在报告中。
        """
        started = time.monotonic()
        try:
            proc = subprocess.run(
                self._config.command,
                shell=True,
                cwd=self._root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._config.timeout_seconds,
            )
            duration = time.monotonic() - started
            output = (proc.stdout or "") + (proc.stderr or "")
            return TestReport(
                command=self._config.command,
                passed=proc.returncode == 0,
                exit_code=proc.returncode,
                duration_seconds=round(duration, 3),
                output=output,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - started
            raw = exc.stdout or b""
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            err = exc.stderr or b""
            if isinstance(err, bytes):
                err = err.decode("utf-8", errors="replace")
            return TestReport(
                command=self._config.command,
                passed=False,
                exit_code=None,
                duration_seconds=round(duration, 3),
                output=str(raw) + str(err) + f"\n[agentflow] 超时（>{self._config.timeout_seconds}s）",
                timed_out=True,
            )

    def run_with_coverage(self) -> TestReport:
        """执行测试并生成覆盖率报告（TODO P1）。"""
        raise NotImplementedError("TODO(P1): 覆盖率报告")
