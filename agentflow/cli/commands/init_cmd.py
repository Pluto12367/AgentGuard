"""agentflow init：扫描项目并生成 agentflow.yaml + AGENTS.md。"""

from __future__ import annotations

from pathlib import Path

import typer

from agentflow.generators.agents_md import AgentsMdGenerator
from agentflow.generators.scanner import ProjectScanner
from agentflow.models.config import CONFIG_FILENAME, AgentFlowConfig, ProjectConfig


def register(app: typer.Typer) -> None:
    @app.command(help="初始化项目：生成 agentflow.yaml + AGENTS.md")
    def init(
        force: bool = typer.Option(False, "--force", help="覆盖已存在的配置文件"),
        skip_agents_md: bool = typer.Option(False, "--skip-agents-md", help="跳过 AGENTS.md 生成"),
    ) -> None:
        cwd = Path.cwd()
        target = cwd / CONFIG_FILENAME
        if target.exists() and not force:
            typer.secho(
                f"[跳过] {CONFIG_FILENAME} 已存在（使用 --force 覆盖）",
                fg=typer.colors.YELLOW,
            )
            raise typer.Exit(code=1)

        config = AgentFlowConfig(project=ProjectConfig(name=cwd.name))
        config.save(target)
        typer.secho(f"[OK] 已生成 {target}", fg=typer.colors.GREEN)

        profile = ProjectScanner().scan(cwd)
        stack = "、".join(profile.languages) if profile.languages else "未识别"
        typer.echo(f"[扫描] 技术栈：{stack}；特征文件：{', '.join(profile.key_files) or '无'}")

        if not skip_agents_md:
            generator = AgentsMdGenerator(profile, config)
            try:
                agents_md = generator.write_to(cwd / "AGENTS.md")
                typer.secho(f"[OK] 已生成 {agents_md}", fg=typer.colors.GREEN)
            except FileExistsError:
                typer.secho(
                    "[跳过] AGENTS.md 已存在，未覆盖（可手工合并或删除后重新 init）",
                    fg=typer.colors.YELLOW,
                )

        typer.echo("按需调整 agentflow.yaml；完整配置项参考仓库内 examples/agentflow.yaml。")
        typer.echo("下一步：agentflow start \"任务描述\" 开启流程管控。")
