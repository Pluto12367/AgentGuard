"""AgentFlow CLI 入口：命令树注册与全局选项。"""

from __future__ import annotations

import typer

from agentflow import __version__
from agentflow.cli.commands import (
    advance_cmd,
    check_cmd,
    guard_cmd,
    init_cmd,
    start_cmd,
    status_cmd,
    test_cmd,
)

app = typer.Typer(
    name="agentflow",
    help=(
        "让 AI Agent 开发更高效、更规范、更少出错："
        "规则生成 + 流程强制 + 安全护栏 + 测试闭环。"
    ),
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"agentflow {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="显示版本号并退出。",
    ),
) -> None:
    """AgentFlow —— AI Agent 开发流程守卫。"""


def _register_commands() -> None:
    for module in (
        init_cmd,
        start_cmd,
        check_cmd,
        advance_cmd,
        status_cmd,
        guard_cmd,
        test_cmd,
    ):
        module.register(app)


_register_commands()


if __name__ == "__main__":
    app()
