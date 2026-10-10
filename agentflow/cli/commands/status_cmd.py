"""agentflow status：显示配置摘要与活动任务状态。"""

from __future__ import annotations

from datetime import datetime

import typer

from agentflow.cli.commands._common import load_config_or_exit
from agentflow.core.state_store import load_state


def _fmt_ts(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return ts


def register(app: typer.Typer) -> None:
    @app.command(help="显示当前配置摘要与活动任务状态")
    def status() -> None:
        config, config_path = load_config_or_exit()
        root = config_path.parent

        typer.secho(f"[配置] {config_path}", fg=typer.colors.GREEN)
        typer.echo(f"  项目：{config.project.name}（{config.project.language}）")
        for size in ("small", "medium", "large"):
            phases = " → ".join(p.value for p in config.workflow.phases_for(size))
            typer.echo(f"  {size:<7}: {phases}")
        typer.echo(f"  重试上限：{config.workflow.max_retries} 次")
        g = config.guardrails
        typer.echo(
            f"  护栏：保护 {len(g.protected_files)} 类文件 / "
            f"黑名单 {len(g.deny_paths)} 类 / 禁新增依赖={g.forbid_new_dependencies} / "
            f"diff 预览={g.require_diff_preview} / 拦截命令 {len(g.blocked_commands)} 条"
        )
        typer.echo(f"  测试：`{config.testing.command}`（超时 {config.testing.timeout_seconds}s）")

        state = load_state(root)
        if state is None:
            typer.echo("[任务] 无活动任务（agentflow start 启动）")
            return

        typer.secho(f"[任务] {state.description}", fg=typer.colors.CYAN)
        typer.echo(
            f"  规模：{state.size}；启动：{_fmt_ts(state.created_at)}；"
            f"更新：{_fmt_ts(state.updated_at)}"
        )
        progress = " → ".join(
            f"[{name}]" if i == state.index else name for i, name in enumerate(state.phases)
        )
        typer.echo(f"  进度：{progress}")
        if state.is_finished:
            typer.secho("  状态：已完成", fg=typer.colors.GREEN)
