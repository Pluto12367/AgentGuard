"""CLI 子命令模块：每个模块通过 register(app) 注册自己的命令。"""

from agentflow.cli.commands import (
    advance_cmd,
    check_cmd,
    guard_cmd,
    init_cmd,
    start_cmd,
    status_cmd,
    test_cmd,
)

__all__ = [
    "advance_cmd",
    "check_cmd",
    "guard_cmd",
    "init_cmd",
    "start_cmd",
    "status_cmd",
    "test_cmd",
]
