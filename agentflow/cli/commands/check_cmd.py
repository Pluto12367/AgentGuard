"""agentflow check：检查当前阶段产物是否齐备。"""

from __future__ import annotations

import typer

from agentflow.cli.commands._common import load_config_or_exit
from agentflow.core.artifacts import DEFAULT_ARTIFACT_SPECS, ArtifactValidator
from agentflow.core.state_machine import Phase
from agentflow.core.state_store import load_state


def _print_check(validator: ArtifactValidator, phase: Phase) -> bool:
    result = validator.check(phase)
    specs = {s.description: s.required for s in validator.specs_for(phase)}
    typer.echo(f"阶段 [{phase.value}] 产物检查：")
    for description, files in result.matched.items():
        required = specs.get(description, True)
        if files:
            typer.secho(f"  [OK] {description}（{len(files)} 个文件）", fg=typer.colors.GREEN)
        elif required:
            typer.secho(f"  [缺失] {description}", fg=typer.colors.RED)
        else:
            typer.secho(f"  [可选] {description}（未提供）", fg=typer.colors.YELLOW)
    if result.satisfied:
        typer.secho("[OK] 产物齐备，可以 advance。", fg=typer.colors.GREEN)
    else:
        for item in result.missing:
            typer.echo(f"  缺失：{item}")
        typer.secho("[拦截] 产物不齐备，无法进入下一阶段。", fg=typer.colors.RED)
    return result.satisfied


def register(app: typer.Typer) -> None:
    @app.command(help="检查当前阶段的产物是否齐备（不齐备则无法进入下一阶段）")
    def check() -> None:
        _config, config_path = load_config_or_exit()
        root = config_path.parent

        state = load_state(root)
        if state is None:
            typer.secho("[无任务] 先运行 agentflow start 启动任务", fg=typer.colors.YELLOW)
            raise typer.Exit(code=1)
        if state.is_finished:
            typer.echo("[OK] 任务已完成（done）。")
            raise typer.Exit()

        validator = ArtifactValidator(root, DEFAULT_ARTIFACT_SPECS)
        satisfied = _print_check(validator, Phase(state.current_phase))
        if not satisfied:
            raise typer.Exit(code=1)
