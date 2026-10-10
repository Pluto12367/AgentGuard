"""agentflow test：运行测试闭环（失败自动打回重试）。"""

from __future__ import annotations

import json
import sys
from typing import Optional

import typer

from agentflow.cli.commands._common import load_config_or_exit
from agentflow.core.session import SessionEvent
from agentflow.core.state_store import append_event, load_state, state_dir
from agentflow.testing.retry_loop import RepairLoop
from agentflow.testing.runner import TestReport, TestRunner


def _save_report(root, report: TestReport) -> None:
    target_dir = state_dir(root)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "test-report.json").write_text(report.to_json(), encoding="utf-8")


def register(app: typer.Typer) -> None:
    @app.command(name="test", help="运行测试闭环：执行测试，失败打回修复直至通过")
    def test_cmd(
        max_retries: Optional[int] = typer.Option(
            None, "--max-retries", help="覆盖配置中的重试上限"
        ),
    ) -> None:
        config, config_path = load_config_or_exit()
        root = config_path.parent
        retries = max_retries if max_retries is not None else config.workflow.max_retries

        state = load_state(root)
        phase = state.current_phase if state is not None else "setup"

        runner = TestRunner(root, config.testing)
        typer.echo(f"测试命令：{config.testing.command!r}（重试上限 {retries}）")

        def on_attempt(report: TestReport, attempt: int) -> None:
            _save_report(root, report)
            append_event(
                root,
                SessionEvent.now(
                    phase,
                    "agentflow",
                    "test_passed" if report.passed else "test_failed",
                    f"第 {attempt} 次执行，exit={report.exit_code}，{report.duration_seconds}s",
                ),
            )

        def request_fix(report: TestReport) -> None:
            typer.secho(f"[失败] 第 {attempt_counter['n']} 次测试未通过：", fg=typer.colors.RED)
            excerpt = report.failure_excerpt or "(无输出)"
            typer.echo(excerpt)
            if sys.stdin.isatty():
                answer = typer.prompt(
                    "修复后按回车重试（输入 q 放弃）", default="", show_default=False
                )
                if answer.strip().lower() == "q":
                    raise typer.Exit(code=1)
            else:
                typer.echo("非交互环境：不再重试。")
                raise typer.Exit(code=1)

        attempt_counter = {"n": 0}

        def counting_fix(report: TestReport) -> None:
            attempt_counter["n"] += 1
            request_fix(report)

        outcome = RepairLoop(runner, retries).run(counting_fix, on_attempt=on_attempt)

        if outcome.fixed:
            report = outcome.final_report
            assert report is not None
            typer.secho(
                f"[OK] 测试通过（第 {outcome.attempts} 次执行，{report.duration_seconds}s）。"
                f"证据：{state_dir(root) / 'test-report.json'}",
                fg=typer.colors.GREEN,
            )
            if state is not None and state.current_phase == "test":
                typer.echo("测试证据已生成，可运行 agentflow advance 进入下一阶段。")
            raise typer.Exit()

        report = outcome.final_report
        typer.secho(
            f"[失败] 重试耗尽（共 {outcome.attempts} 次执行），任务保留在当前阶段。",
            fg=typer.colors.RED,
        )
        if report is not None and report.failure_excerpt:
            typer.echo(report.failure_excerpt)
        raise typer.Exit(code=1)
