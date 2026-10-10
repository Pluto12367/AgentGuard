"""agentflow start：启动任务，自动路由规模并进入流程状态机。"""

from __future__ import annotations

from typing import Optional

import typer

from agentflow.cli.commands._common import load_config_or_exit
from agentflow.core.session import SessionEvent
from agentflow.core.state_machine import Phase, WorkflowStateMachine
from agentflow.core.state_store import TaskState, append_event, load_state, save_state
from agentflow.core.task_router import TaskProfile, TaskRouter


def register(app: typer.Typer) -> None:
    @app.command(help="启动任务：自动路由规模并进入流程状态机")
    def start(
        task: str = typer.Argument(..., help="任务描述"),
        size: Optional[str] = typer.Option(
            None, "--size", help="强制指定规模：small / medium / large（默认自动路由）"
        ),
    ) -> None:
        if size is not None and size not in ("small", "medium", "large"):
            typer.secho(
                f"[错误] 无效的 size：{size}（可选 small/medium/large）", fg=typer.colors.RED
            )
            raise typer.Exit(code=2)

        config, config_path = load_config_or_exit()
        root = config_path.parent

        existing = load_state(root)
        if existing is not None and not existing.is_finished:
            typer.secho(
                f"[进行中] 已有活动任务：{existing.description!r}（当前 {existing.current_phase}）。"
                f"先完成或删除 {root / '.agentflow' / 'state.json'}。",
                fg=typer.colors.YELLOW,
            )
            raise typer.Exit(code=1)

        router = TaskRouter(config.workflow)
        chosen_size = size or router.size_of(TaskProfile(description=task))
        phases = (
            config.workflow.phases_for(chosen_size)
            if size is not None
            else router.route(TaskProfile(description=task))
        )
        WorkflowStateMachine(phases=phases)  # 校验阶段序列合法性

        state = TaskState.create(task, chosen_size, [p.value for p in phases])
        save_state(root, state)
        append_event(
            root,
            SessionEvent.now("setup", "user", "task_started", f"{chosen_size}: {task}"),
        )

        typer.secho(
            f"[OK] 任务已启动（{chosen_size}）：{task}", fg=typer.colors.GREEN
        )
        typer.echo("  流程：" + " → ".join(state.phases))
        typer.echo(f"  当前阶段：{state.current_phase}")
        typer.echo("用 agentflow check 查看产物要求；agentflow advance 尝试进入下一阶段。")
