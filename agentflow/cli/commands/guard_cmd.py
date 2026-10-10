"""agentflow guard：校验文件改动或命令是否被护栏放行。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from agentflow.cli.commands._common import load_config_or_exit
from agentflow.core.session import SessionEvent
from agentflow.core.state_store import append_event, load_state
from agentflow.guard.engine import FileChange, GuardrailEngine


def _to_rel(path: Path, root: Path) -> Path:
    """把用户给的路径转成相对项目根的 posix 路径；根外路径原样保留。"""
    resolved = path if path.is_absolute() else Path.cwd() / path
    try:
        return resolved.resolve().relative_to(root.resolve())
    except ValueError:
        return Path(resolved.as_posix())


def register(app: typer.Typer) -> None:
    @app.command(help="校验一次命令或文件改动是否会被护栏放行（预演，不执行）")
    def guard(
        command: Optional[str] = typer.Option(None, "--command", help="要校验的 shell 命令"),
        file_path: Optional[Path] = typer.Option(None, "--file", help="要校验的文件路径"),
        delete: bool = typer.Option(False, "--delete", help="按删除操作校验（默认按创建/修改）"),
    ) -> None:
        if command is None and file_path is None:
            typer.secho("[错误] 至少提供 --command 或 --file 之一", fg=typer.colors.RED)
            raise typer.Exit(code=2)

        config, config_path = load_config_or_exit()
        root = config_path.parent
        engine = GuardrailEngine(root, config.guardrails)

        if command is not None:
            result = engine.check_command(command)
            target_desc = f"命令 {command!r}"
        else:
            assert file_path is not None
            rel = _to_rel(file_path, root)
            exists = (root / rel).exists()
            change_type = "delete" if delete else ("create" if not exists else "modify")
            result = engine.check_file_change(FileChange(rel, change_type))
            target_desc = f"文件 {rel.as_posix()}（{change_type}）"

        state = load_state(root)
        phase = state.current_phase if state is not None else "setup"

        if result.allowed:
            typer.secho(f"[放行] {target_desc}", fg=typer.colors.GREEN)
            if result.reason:
                typer.echo(f"  提示：{result.reason}")
            raise typer.Exit()

        typer.secho(f"[拦截] {target_desc}", fg=typer.colors.RED)
        typer.echo(f"  规则：{result.rule_id}")
        typer.echo(f"  原因：{result.reason}")
        append_event(
            root,
            SessionEvent.now(phase, "agentflow", "guard_denied", f"{result.rule_id}: {target_desc}"),
        )
        raise typer.Exit(code=1)
