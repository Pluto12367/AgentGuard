"""CLI 子命令的公共辅助：配置发现/加载。"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from agentflow.models.config import AgentFlowConfig


def load_config_or_exit() -> tuple[AgentFlowConfig, Path]:
    """向上查找并加载 agentflow.yaml；找不到或文件非法时提示并退出（exit 1）。

    返回 (配置, 配置文件路径)；项目根 = 配置文件所在目录。
    """
    path = AgentFlowConfig.discover(Path.cwd())
    if path is None:
        typer.secho(
            "[未找到] 当前目录及上级目录中没有 agentflow.yaml，先运行 agentflow init",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)
    try:
        return AgentFlowConfig.load(path), path
    except yaml.YAMLError as exc:
        typer.secho(f"[配置错误] YAML 语法有问题：{path}\n{exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    except (ValidationError, ValueError) as exc:
        typer.secho(f"[配置错误] 内容校验未通过：{path}\n{exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
