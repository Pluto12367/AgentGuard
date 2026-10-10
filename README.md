# AgentFlow

> 面向个人开发者的 Python 工具：通过「规则生成 + 流程强制 + 安全护栏 + 测试闭环」，
> 让 AI Agent 开发更高效、更规范、更少出错。支持 CLI + Cursor/VS Code 插件（插件规划中）。

## 核心能力

| 能力 | 说明 |
|------|------|
| 规则生成 | `agentflow init` 扫描技术栈，自动生成 `AGENTS.md` + `agentflow.yaml`；Cursor rules 生成见 P1 |
| 流程强制 | 严格分阶段 `analyze → design → implement → test → review → done`，产物不齐备不放行；Small/Medium/Large 自动路由 |
| 安全护栏 | 文件白名单/黑名单、受保护文件、禁新增依赖、修改前 diff 预览确认、危险命令拦截 |
| 测试闭环 | `agentflow test` 自动跑测试，失败打回修复直至通过或达到最大重试；证据写入 `.agentflow/test-report.json` |

## 快速开始

```bash
# 要求 Python >= 3.11
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 在你的项目中开启流程管控
cd your-project
agentflow init                    # 扫描技术栈 → 生成 agentflow.yaml + AGENTS.md

agentflow start "修复登录超时 bug"  # 启动任务（自动路由 small/medium/large）
agentflow check                   # 当前阶段产物检查（缺失则列出）
agentflow advance                 # 产物齐备时进入下一阶段（否则拦截）
agentflow test                    # 跑测试；失败给出证据，重试直至通过/耗尽
agentflow status                  # 配置摘要 + 任务进度
agentflow guard --command "git push --force"   # 护栏预演：拦截
agentflow guard --file .env --delete           # 护栏预演：受保护文件禁止删除
```

一个完整任务的推进循环就是：`start → 改代码/写文档 → check → advance → … → done`。
在 `test` 阶段，`agentflow test` 通过后留下的测试证据正是 advance 的产物要求。

## 命令一览

| 命令 | 说明 |
|------|------|
| `agentflow init` | 扫描技术栈，生成 `agentflow.yaml` + `AGENTS.md`（`--force` 覆盖配置，`--skip-agents-md` 跳过） |
| `agentflow start <task>` | 启动任务；自动路由规模，`--size` 可强制指定；已有进行中任务时拒绝 |
| `agentflow check` | 检查当前阶段产物是否齐备（齐备 exit 0，缺失 exit 1） |
| `agentflow advance` | 尝试进入下一阶段；产物不齐备时拦截并列出缺失项 |
| `agentflow status` | 配置摘要 + 活动任务进度 |
| `agentflow guard` | 护栏预演：`--command` 校验命令 / `--file`（`--delete`）校验文件改动 |
| `agentflow test` | 运行测试闭环（`--max-retries` 覆盖重试上限）；证据写入 `.agentflow/` |
| `agentflow --version` | 查看版本 |

## 阶段产物要求（默认值，可在代码中调整）

| 阶段 | 必须产出 | 缺失后果 |
|------|----------|----------|
| analyze | `docs/*.md`（分析记录） | 拦截 |
| design | `docs/design*.md` 或 `docs/design/` | 拦截 |
| implement | 任一源码文件（`.py/.ts/.go/...`） | 拦截 |
| test | `.agentflow/test-report.json`（由 `agentflow test` 写入） | 拦截 |
| review | `docs/review*.md`（可选） | 仅提示 |
| done | — | — |

Small 任务默认只走 `implement → test → done`，跳过文档阶段。

## 配置

配置文件为项目根目录的 `agentflow.yaml`，完整注释示例见 [`examples/agentflow.yaml`](examples/agentflow.yaml)。要点：

- `workflow`：三档规模（small/medium/large）各自的阶段序列 + `max_retries` 重试上限
- `guardrails`：`protected_files` / `allow_paths` / `deny_paths` / `forbid_new_dependencies` / `require_diff_preview` / `blocked_commands`
- `testing`：`command` / `timeout_seconds` / `coverage`

运行时数据在 `.agentflow/`：`state.json`（任务状态）、`session.jsonl`（操作与证据日志）、`test-report.json`（最近一次测试证据）。

## 项目结构

```
AgentFlow/
├── agentflow/               # Python 包
│   ├── cli/                 # Typer 命令行入口
│   ├── core/                # 流程状态机、产物校验、任务路由、状态/会话持久化
│   ├── guard/               # 安全护栏：文件规则、命令拦截、diff 预览
│   ├── testing/             # 测试执行器 + 失败重试闭环
│   ├── generators/          # 项目扫描 + AGENTS.md / .cursor/rules 生成器
│   ├── models/              # Pydantic 配置模型（agentflow.yaml）
│   ├── plugins/             # Cursor/VS Code 插件桥（P2）
│   └── templates/           # 内置 Jinja2 模板，随包分发
├── examples/agentflow.yaml  # 全量注释配置示例
├── docs/architecture.md     # 架构说明（模块职责 + 数据流）
└── tests/                   # 行为测试 + CLI 端到端
```

## MVP Roadmap

| 优先级 | 功能 | 状态 |
|--------|------|------|
| P0 | `agentflow init` 扫描生成 | ✅ 已实现（基础技术栈扫描 + AGENTS.md） |
| P0 | 流程状态机（阶段流转 + 产物检查） | ✅ 已实现 |
| P0 | 安全护栏（文件保护 + 修改预览确认） | ✅ 已实现 |
| P0 | 测试闭环（自动跑测试 + 失败重试） | ✅ 已实现 |
| P1 | 规则生成增强（按技术栈智能生成 + `.cursor/rules` + 增量更新） | 模板与接口就绪，逻辑待实现 |
| P1 | 会话日志增强 | ✅ 基础版已实现（JSONL），分析/回放待做 |
| P2 | Cursor 插件基础版 | 规划中（`plugins/bridge.py` 占位） |

## 开发

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
