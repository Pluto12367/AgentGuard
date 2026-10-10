"""AgentFlow P0 行为测试。

覆盖：模块导入、配置模型、glob 匹配、护栏（文件/命令）、产物校验、
状态机流转、任务路由、测试执行器与重试闭环、会话/状态持久化、
生成器渲染、剩余桩契约，以及 CLI 端到端流程。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

MODULES = [
    "agentflow",
    "agentflow.core",
    "agentflow.core.artifacts",
    "agentflow.core.session",
    "agentflow.core.state_machine",
    "agentflow.core.state_store",
    "agentflow.core.task_router",
    "agentflow.models",
    "agentflow.models.config",
    "agentflow.guard",
    "agentflow.guard.command_rules",
    "agentflow.guard.diff_preview",
    "agentflow.guard.engine",
    "agentflow.guard.file_rules",
    "agentflow.testing",
    "agentflow.testing.retry_loop",
    "agentflow.testing.runner",
    "agentflow.generators",
    "agentflow.generators.agents_md",
    "agentflow.generators.cursor_rules",
    "agentflow.generators.scanner",
    "agentflow.plugins",
    "agentflow.plugins.bridge",
    "agentflow.cli",
    "agentflow.cli.commands._common",
    "agentflow.cli.commands.advance_cmd",
    "agentflow.cli.commands.check_cmd",
    "agentflow.cli.commands.guard_cmd",
    "agentflow.cli.commands.init_cmd",
    "agentflow.cli.commands.start_cmd",
    "agentflow.cli.commands.status_cmd",
    "agentflow.cli.commands.test_cmd",
]


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- 配置模型


def test_all_modules_importable() -> None:
    for name in MODULES:
        importlib.import_module(name)


import importlib  # noqa: E402  (供上方测试使用)


def test_example_config_parses(repo_root: Path) -> None:
    from agentflow.core.state_machine import Phase
    from agentflow.models.config import AgentFlowConfig

    config = AgentFlowConfig.load(repo_root / "examples" / "agentflow.yaml")

    assert config.version == 1
    assert config.project.name == "my-project"
    assert config.workflow.small == [Phase.IMPLEMENT, Phase.TEST, Phase.DONE]
    assert config.workflow.medium[-1] is Phase.DONE
    assert config.workflow.max_retries == 3
    assert "git push --force" in config.guardrails.blocked_commands
    assert config.guardrails.forbid_new_dependencies is True
    assert config.testing.command == "pytest -q"
    assert config.testing.timeout_seconds == 600


def test_default_config_roundtrip(tmp_path: Path) -> None:
    from agentflow.models.config import AgentFlowConfig, ProjectConfig

    config = AgentFlowConfig(project=ProjectConfig(name="demo"))
    target = tmp_path / "agentflow.yaml"
    config.save(target)

    assert AgentFlowConfig.load(target) == config


def test_discover_finds_config_in_parent(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    from agentflow.models.config import CONFIG_FILENAME, AgentFlowConfig, ProjectConfig

    AgentFlowConfig(project=ProjectConfig(name="demo")).save(tmp_path / CONFIG_FILENAME)
    nested = tmp_path / "src" / "app"
    nested.mkdir(parents=True)

    assert AgentFlowConfig.discover(nested) == tmp_path / CONFIG_FILENAME

    elsewhere = tmp_path_factory.mktemp("elsewhere")
    assert AgentFlowConfig.discover(elsewhere) is None


def test_workflow_config_rejects_bad_sequences() -> None:
    from agentflow.core.state_machine import Phase
    from agentflow.models.config import WorkflowConfig

    with pytest.raises(ValidationError):  # 不以 done 结尾
        WorkflowConfig(small=[Phase.ANALYZE, Phase.IMPLEMENT])
    with pytest.raises(ValidationError):  # 重复阶段
        WorkflowConfig(medium=[Phase.ANALYZE, Phase.ANALYZE, Phase.DONE])
    with pytest.raises(ValidationError):  # 空序列
        WorkflowConfig(large=[])


# ---------------------------------------------------------------- glob 匹配与文件规则


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        (".git/**", ".git/config", True),
        (".git/**", "a/.git/config", False),  # 含斜杠的模式锚定在根
        ("*.pem", "certs/server.pem", True),  # 无斜杠：任意深度
        ("*.pem", "certs/server.crt", False),
        (".env.*", ".env.local", True),
        ("**/*.py", "src/app.py", True),
        ("**/*.py", "app.py", True),  # ** 可匹配零层
        ("src/*.py", "src/a/b.py", False),  # * 不跨目录
        ("src/**/*.py", "src/a/b.py", True),
        ("docs/design*.md", "docs/design.md", True),
    ],
)
def test_glob_match(pattern: str, path: str, expected: bool) -> None:
    from agentflow.guard.file_rules import glob_match

    assert glob_match(pattern, path) is expected


def test_file_rules_classify() -> None:
    from agentflow.guard.file_rules import FileRuleSet
    from agentflow.models.config import GuardrailConfig

    rules = FileRuleSet(GuardrailConfig())

    assert rules.classify(".git/config") == "denied"
    assert rules.classify(".env") == "protected"
    assert rules.classify("src/main.py") == "allowed"

    # 白名单模式：allow_paths 非空后，未命中的路径一律拒绝
    whitelist = FileRuleSet(GuardrailConfig(allow_paths=["src/**"]))
    assert whitelist.classify("src/a.py") == "allowed"
    assert whitelist.classify("docs/x.md") == "denied"


def test_dependency_manifest_detection() -> None:
    from agentflow.guard.file_rules import FileRuleSet
    from agentflow.models.config import GuardrailConfig

    rules = FileRuleSet(GuardrailConfig())
    assert rules.is_dependency_manifest("pyproject.toml")
    assert rules.is_dependency_manifest("requirements-dev.txt")
    assert rules.is_dependency_manifest("package.json")
    assert not rules.is_dependency_manifest("src/main.py")


# ---------------------------------------------------------------- 命令规则与护栏引擎


def test_command_rules_match() -> None:
    from agentflow.guard.command_rules import CommandRuleSet

    rules = CommandRuleSet()
    assert rules.match("cd / && git push --force origin main") == "git push --force"
    assert rules.match("RM -RF /tmp") == "rm -rf /"  # 大小写不敏感
    assert rules.match("git status") is None


def test_guard_engine_file_changes(tmp_path: Path) -> None:
    from agentflow.guard.engine import FileChange, GuardrailEngine
    from agentflow.models.config import GuardrailConfig

    engine = GuardrailEngine(tmp_path, GuardrailConfig())

    assert engine.check_file_change(FileChange(Path(".git/config"), "modify")).allowed is False
    assert (
        engine.check_file_change(FileChange(Path(".git/config"), "modify")).rule_id
        == "deny_paths"
    )
    assert engine.check_file_change(FileChange(Path(".env"), "delete")).allowed is False
    assert engine.check_file_change(FileChange(Path(".env"), "modify")).allowed is True
    assert engine.check_file_change(FileChange(Path(".env"), "modify")).rule_id == "protected_files"
    assert engine.check_file_change(FileChange(Path("src/a.py"), "create")).rule_id == "ok"
    assert engine.check_file_change(FileChange(Path("pyproject.toml"), "modify")).allowed is False


def test_guard_engine_commands(tmp_path: Path) -> None:
    from agentflow.guard.engine import GuardrailEngine
    from agentflow.models.config import GuardrailConfig

    engine = GuardrailEngine(tmp_path, GuardrailConfig())
    assert engine.check_command("echo hello").allowed is True
    blocked = engine.check_command("git push -f")
    assert blocked.allowed is False
    assert blocked.rule_id == "blocked_commands"


# ---------------------------------------------------------------- 产物校验


def test_artifact_validator(tmp_path: Path) -> None:
    from agentflow.core.artifacts import DEFAULT_ARTIFACT_SPECS, ArtifactValidator
    from agentflow.core.state_machine import Phase

    validator = ArtifactValidator(tmp_path, DEFAULT_ARTIFACT_SPECS)
    result = validator.check(Phase.ANALYZE)
    assert not result.satisfied
    assert len(result.missing) == 1

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "analysis.md").write_text("# 分析", encoding="utf-8")
    result = validator.check(Phase.ANALYZE)
    assert result.satisfied
    key = next(iter(result.matched))
    assert result.matched[key] == (Path("docs/analysis.md"),)


def test_artifact_validator_ignores_excluded_dirs(tmp_path: Path) -> None:
    from agentflow.core.artifacts import DEFAULT_ARTIFACT_SPECS, ArtifactValidator
    from agentflow.core.state_machine import Phase

    venv_file = tmp_path / ".venv" / "lib" / "x.py"
    venv_file.parent.mkdir(parents=True)
    venv_file.write_text("x = 1", encoding="utf-8")

    validator = ArtifactValidator(tmp_path, DEFAULT_ARTIFACT_SPECS)
    assert not validator.check(Phase.IMPLEMENT).satisfied


# ---------------------------------------------------------------- 状态机与任务路由


def test_state_machine_contract() -> None:
    from agentflow.core.state_machine import Phase, WorkflowStateMachine

    with pytest.raises(ValueError):
        WorkflowStateMachine(phases=[])
    with pytest.raises(ValueError):
        WorkflowStateMachine(phases=[Phase.ANALYZE, Phase.IMPLEMENT])
    with pytest.raises(ValueError):
        WorkflowStateMachine(phases=[Phase.TEST, Phase.TEST, Phase.DONE])
    with pytest.raises(ValueError):
        WorkflowStateMachine(phases=[Phase.IMPLEMENT, Phase.TEST, Phase.DONE], start_index=3)

    sm = WorkflowStateMachine(phases=[Phase.IMPLEMENT, Phase.TEST, Phase.DONE])
    assert sm.current_phase is Phase.IMPLEMENT
    assert sm.phases == (Phase.IMPLEMENT, Phase.TEST, Phase.DONE)
    assert not sm.is_finished


def test_state_machine_advance_blocks_on_missing_artifacts(tmp_path: Path) -> None:
    from agentflow.core.artifacts import DEFAULT_ARTIFACT_SPECS, ArtifactValidator
    from agentflow.core.state_machine import Phase, WorkflowStateMachine

    validator = ArtifactValidator(tmp_path, DEFAULT_ARTIFACT_SPECS)
    sm = WorkflowStateMachine(
        phases=[Phase.ANALYZE, Phase.DESIGN, Phase.DONE],
        artifact_specs=DEFAULT_ARTIFACT_SPECS,
        validator=validator,
    )

    blocked = sm.advance()
    assert blocked.allowed is False
    assert blocked.to_phase is Phase.DESIGN
    assert blocked.missing_artifacts
    assert sm.current_phase is Phase.ANALYZE  # 未推进

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "analysis.md").write_text("# 分析", encoding="utf-8")
    allowed = sm.advance()
    assert allowed.allowed is True
    assert sm.current_phase is Phase.DESIGN


def test_state_machine_done_is_terminal(tmp_path: Path) -> None:
    from agentflow.core.state_machine import Phase, WorkflowStateMachine

    sm = WorkflowStateMachine(
        phases=[Phase.DONE], validator=None, start_index=0
    )
    result = sm.advance()
    assert result.allowed is False
    assert sm.is_finished


def test_task_router() -> None:
    from agentflow.core.task_router import TaskProfile, TaskRouter
    from agentflow.models.config import WorkflowConfig

    router = TaskRouter(WorkflowConfig())
    size = router.size_of

    assert size(TaskProfile(description="t", estimated_files=1)) == "small"
    assert size(TaskProfile(description="t", estimated_files=5)) == "medium"
    assert size(TaskProfile(description="t", estimated_files=12)) == "large"
    # 放大信号：动公共 API / 新依赖，至少 medium
    assert size(TaskProfile(description="t", estimated_files=1, touches_public_api=True)) == "medium"
    assert (
        size(TaskProfile(description="t", estimated_files=1, requires_new_dependency=True))
        == "medium"
    )
    # 大规模优先于其他信号
    assert size(TaskProfile(description="t", estimated_files=12, touches_public_api=True)) == "large"

    small_phases = router.route(TaskProfile(description="t", estimated_files=1))
    assert [p.value for p in small_phases] == ["implement", "test", "done"]


# ---------------------------------------------------------------- 测试执行器与重试闭环


def _report(command: str, passed: bool, output: str = "") -> object:
    from agentflow.testing.runner import TestReport

    return TestReport(
        command=command,
        passed=passed,
        exit_code=0 if passed else 1,
        duration_seconds=0.01,
        output=output,
    )


def test_test_runner_pass_and_fail(tmp_path: Path) -> None:
    from agentflow.models.config import TestConfig
    from agentflow.testing.runner import TestRunner

    good = TestRunner(tmp_path, TestConfig(command=f'"{sys.executable}" --version', timeout_seconds=60))
    report = good.run()
    assert report.passed and report.exit_code == 0 and not report.timed_out

    bad = TestRunner(
        tmp_path,
        TestConfig(
            command=f'"{sys.executable}" -c "import sys; print(\'boom\'); sys.exit(3)"',
            timeout_seconds=60,
        ),
    )
    report = bad.run()
    assert not report.passed and report.exit_code == 3
    assert report.failure_excerpt is not None
    assert "boom" in report.failure_excerpt


def test_repair_loop_retries_then_passes() -> None:
    from agentflow.testing.retry_loop import RepairLoop

    class FakeRunner:
        def __init__(self, reports: list[object]) -> None:
            self._reports = reports
            self.calls = 0

        def run(self):  # noqa: ANN201
            report = self._reports[min(self.calls, len(self._reports) - 1)]
            self.calls += 1
            return report

    reports = [_report("x", False, "FAIL a"), _report("x", False, "FAIL b"), _report("x", True)]
    runner = FakeRunner(reports)
    fixes: list[str] = []
    attempts: list[int] = []

    outcome = RepairLoop(runner, max_retries=3).run(  # type: ignore[arg-type]
        lambda rep: fixes.append(rep.output),  # type: ignore[attr-defined]
        on_attempt=lambda rep, n: attempts.append(n),
    )

    assert outcome.fixed is True
    assert outcome.attempts == 3
    assert len(fixes) == 2  # 第 1、2 次失败后各打回一次
    assert attempts == [1, 2, 3]


def test_repair_loop_exhausts_retries() -> None:
    from agentflow.testing.retry_loop import RepairLoop

    class FakeRunner:
        def __init__(self) -> None:
            self.calls = 0

        def run(self):  # noqa: ANN201
            self.calls += 1
            return _report("x", False, "FAIL")

    fixes: list[object] = []
    outcome = RepairLoop(FakeRunner(), max_retries=2).run(  # type: ignore[arg-type]
        lambda rep: fixes.append(rep),
    )
    assert outcome.fixed is False
    assert outcome.attempts == 3  # 1 + max_retries
    assert len(fixes) == 2  # 最后一次失败已无重试预算，不再打回


# ---------------------------------------------------------------- 持久化


def test_session_log_records_and_saves(tmp_path: Path) -> None:
    from agentflow.core.session import SessionEvent, SessionLog

    log = SessionLog()
    log.record(SessionEvent.now("setup", "user", "init", "生成配置"))
    log.record(SessionEvent.now("implement", "agent", "phase_advanced", "ok"))
    target = tmp_path / "session.jsonl"

    assert log.save(target) == target
    lines = target.read_text(encoding="utf-8").strip().splitlines()
    payload = [json.loads(line) for line in lines]
    assert [e["action"] for e in payload] == ["init", "phase_advanced"]
    assert all(e["timestamp"] for e in payload)


def test_state_store_roundtrip(tmp_path: Path) -> None:
    from agentflow.core.state_store import TaskState, load_state, save_state

    assert load_state(tmp_path) is None

    state = TaskState.create("demo", "small", ["implement", "test", "done"])
    save_state(tmp_path, state)
    loaded = load_state(tmp_path)

    assert loaded is not None
    assert loaded.current_phase == "implement"
    assert not loaded.is_finished
    loaded.index = 2
    assert loaded.is_finished


# ---------------------------------------------------------------- 生成器


def test_scanner_basic(tmp_path: Path) -> None:
    from agentflow.generators.scanner import ProjectScanner

    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    profile = ProjectScanner().scan(tmp_path)
    assert profile.project_name == tmp_path.name
    assert "python" in profile.languages and "typescript" in profile.languages
    assert "pytest" in profile.test_frameworks
    assert set(profile.key_files) == {"pyproject.toml", "package.json"}
    assert profile.is_git_repo is False


def test_agents_md_render_and_write(tmp_path: Path) -> None:
    from agentflow.generators.agents_md import AgentsMdGenerator
    from agentflow.generators.scanner import ProjectProfile
    from agentflow.models.config import AgentFlowConfig, ProjectConfig

    profile = ProjectProfile(
        root=tmp_path,
        project_name="demo",
        languages=("python",),
        test_frameworks=("pytest",),
    )
    config = AgentFlowConfig(project=ProjectConfig(name="demo"))
    generator = AgentsMdGenerator(profile, config)

    text = generator.render()
    for fragment in ("demo", "安全约束", "测试要求", "pytest -q", "重试 3 次", "implement"):
        assert fragment in text, fragment

    target = tmp_path / "AGENTS.md"
    assert generator.write_to(target) == target
    assert target.read_text(encoding="utf-8").startswith("# AGENTS.md")
    with pytest.raises(FileExistsError):  # 已存在时拒绝覆盖
        generator.write_to(target)


# ---------------------------------------------------------------- 剩余桩契约（P1/P2）


def test_remaining_stubs_raise_not_implemented(tmp_path: Path) -> None:
    from agentflow.generators.cursor_rules import CursorRulesGenerator
    from agentflow.generators.scanner import ProjectProfile
    from agentflow.models.config import TestConfig
    from agentflow.plugins.bridge import PluginBridge
    from agentflow.testing.runner import TestRunner

    profile = ProjectProfile(root=tmp_path, project_name="demo")
    stubs: list[object] = [
        lambda: CursorRulesGenerator(profile).render(),
        lambda: CursorRulesGenerator(profile).write_to(tmp_path / "x.mdc"),
        lambda: TestRunner(tmp_path, TestConfig()).run_with_coverage(),
        lambda: PluginBridge().start(),
        lambda: PluginBridge().stop(),
    ]
    for call in stubs:
        with pytest.raises(NotImplementedError, match=r"TODO\((?:P[012]/?)+\)"):
            call()


# ---------------------------------------------------------------- 模板与 CLI


def test_templates_are_bundled() -> None:
    from importlib import resources

    base = resources.files("agentflow.templates")
    assert (base / "agents_md.md.j2").is_file()
    assert (base / "cursor_rules.mdc.j2").is_file()


def test_cli_help_lists_all_commands() -> None:
    from typer.testing import CliRunner

    from agentflow.cli.main import app

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("init", "start", "check", "advance", "status", "guard", "test"):
        assert command in result.output


def test_cli_version() -> None:
    from typer.testing import CliRunner

    from agentflow import __version__
    from agentflow.cli.main import app

    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_full_workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """端到端：init → start → check(拦截) → 补产物 → advance → test → advance → done。"""
    from typer.testing import CliRunner

    from agentflow.cli.main import app
    from agentflow.core.state_store import load_state
    from agentflow.models.config import AgentFlowConfig

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    # init：配置 + AGENTS.md
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "agentflow.yaml").exists()
    assert (tmp_path / "AGENTS.md").exists()
    result = runner.invoke(app, ["init"])  # 重复 init 被拒绝
    assert result.exit_code == 1

    # 把测试命令换成必过的命令，便于流程演练
    config = AgentFlowConfig.load(tmp_path / "agentflow.yaml")
    config.testing.command = f'"{sys.executable}" --version'
    config.save(tmp_path / "agentflow.yaml")

    # start：自动路由 small
    result = runner.invoke(app, ["start", "修复登录超时"])
    assert result.exit_code == 0, result.output
    state = load_state(tmp_path)
    assert state is not None and state.size == "small"
    assert state.phases == ["implement", "test", "done"]

    # check：implement 阶段缺代码 → 拦截
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1
    assert "缺失" in result.output

    # advance 在产物缺失时同样拦截
    result = runner.invoke(app, ["advance"])
    assert result.exit_code == 1

    # 补上代码产物 → check 通过 → advance 进入 test
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    assert runner.invoke(app, ["check"]).exit_code == 0
    result = runner.invoke(app, ["advance"])
    assert result.exit_code == 0, result.output
    assert load_state(tmp_path).current_phase == "test"

    # test：执行并留下证据
    result = runner.invoke(app, ["test"])
    assert result.exit_code == 0, result.output
    report = json.loads((tmp_path / ".agentflow" / "test-report.json").read_text("utf-8"))
    assert report["passed"] is True
    assert (tmp_path / ".agentflow" / "session.jsonl").exists()

    # test 阶段证据齐备 → advance 到 done
    result = runner.invoke(app, ["advance"])
    assert result.exit_code == 0, result.output
    assert load_state(tmp_path).is_finished

    # status 展示已完成任务
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "已完成" in result.output


def test_cli_guard_blocks_dangerous_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from agentflow.cli.main import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0

    result = runner.invoke(app, ["guard", "--command", "cd / && git push --force origin main"])
    assert result.exit_code == 1
    assert "blocked_commands" in result.output

    result = runner.invoke(app, ["guard", "--file", ".env", "--delete"])
    assert result.exit_code == 1
    assert "protected_files" in result.output

    result = runner.invoke(app, ["guard", "--file", "src/new.py"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["guard"])  # 无参数 → 用法错误
    assert result.exit_code == 2
