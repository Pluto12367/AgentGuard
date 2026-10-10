"""agentflow advance：产物齐备时进入下一阶段。"""

from __future__ import annotations

import typer

from agentflow.cli.commands._common import load_config_or_exit
from agentflow.cli.commands.check_cmd import _print_check
from agentflow.core.artifacts import DEFAULT_ARTIFACT_SPECS, ArtifactValidator
from agentflow.core.state_machine import Phase, WorkflowStateMachine
from agentflow.core.session import SessionEvent
from agentflow.core.state_store import append_event, load_state, save_state


def register(app: typer.Typer) -> None:
    @app.command(help="尝试进入下一阶段（当前阶段产物齐备才放行）")
    def advance() -> None:
        _config, config_path = load_config_or_exit()
        root = config_path.parent

        state = load_state(root)
        if state is None:
            typer.secho("[无任务] 先运行 agentflow start 启动任务", fg=typer.colors.YELLOW)
            raise typer.Exit(code=1)

        validator = ArtifactValidator(root, DEFAULT_ARTIFACT_SPECS)
        machine = WorkflowStateMachine(
            phases=[Phase(p) for p in state.phases],
            artifact_specs=DEFAULT_ARTIFACT_SPECS,
            validator=validator,
            start_index=state.index,
        )

        result = machine.advance()
        if not result.allowed:
            typer.secho(f"[拦截] {result.reason}", fg=typer.colors.RED)
            _print_check(validator, result.from_phase)
            for item in result.missing_artifacts:
                typer.echo(f"  缺失：{item}")
            append_event(
                root,
                SessionEvent.now(
                    state.current_phase, "agentflow", "advance_blocked", "; ".join(result.missing_artifacts)
                ),
            )
            raise typer.Exit(code=1)

        if state.is_finished:
            typer.echo("[OK] 任务已完成（done），没有后续阶段。")
            raise typer.Exit()

        state.index += 1
        state.touch()
        save_state(root, state)
        append_event(
            root,
            SessionEvent.now(state.current_phase, "agentflow", "phase_advanced", result.reason),
        )
        typer.secho(f"[OK] 进入阶段：{state.current_phase}", fg=typer.colors.GREEN)
        if state.is_finished:
            typer.secho(f"[完成] 任务「{state.description}」全部阶段完成。", fg=typer.colors.GREEN)
