# AgentFlow 架构说明

> v0.1.0：P0 四大能力（流程状态机、安全护栏、测试闭环、init 生成）已全部实现。
> 本文描述模块职责与数据流，并标注剩余 P1/P2 待办。

## 模块职责

| 模块 | 职责 | 状态 |
|------|------|------|
| `agentflow/models/` | `agentflow.yaml` 的 Pydantic schema：加载/校验/保存/向上查找，配置默认值的单一来源 | ✅ 已实现 |
| `agentflow/core/state_machine.py` | `Phase` 枚举、`ArtifactSpec`/`TransitionResult`、`WorkflowStateMachine`（只进不退，advance 前强制产物检查） | ✅ 已实现 |
| `agentflow/core/artifacts.py` | `ArtifactValidator`：os.walk + gitignore 风格 glob 检查产物齐备性；`DEFAULT_ARTIFACT_SPECS` 默认产物规格 | ✅ 已实现 |
| `agentflow/core/task_router.py` | `TaskRouter`：按 `TaskProfile`（文件数/公共 API/新依赖）路由 small/medium/large | ✅ 已实现 |
| `agentflow/core/state_store.py` | `.agentflow/state.json` 任务状态持久化 + `session.jsonl` 事件追加 | ✅ 已实现 |
| `agentflow/core/session.py` | `SessionEvent`/`SessionLog`：操作与证据记录（JSONL） | ✅ 基础版；分析/回放待做 |
| `agentflow/guard/engine.py` | `GuardrailEngine` 统一裁决入口（文件/命令/diff 确认） | ✅ 已实现 |
| `agentflow/guard/file_rules.py` | gitignore 风格 glob（`**` 跨目录、`*` 单段）、白/黑/保护三态裁决、依赖清单识别 | ✅ 已实现 |
| `agentflow/guard/command_rules.py` | 危险命令子串匹配（大小写不敏感） | ✅ 已实现 |
| `agentflow/guard/diff_preview.py` | diff 生成（GitPython 优先，非 git 退化内容摘要）+ y/n/a 交互确认 | ✅ 已实现 |
| `agentflow/testing/runner.py` | `TestRunner`：subprocess 执行测试命令 → `TestReport`（含超时与失败摘要） | ✅ 已实现 |
| `agentflow/testing/retry_loop.py` | `RepairLoop`：失败打回重试闭环（≤ 1 + max_retries 次） | ✅ 已实现 |
| `agentflow/generators/scanner.py` | 特征文件识别技术栈 → `ProjectProfile` | ✅ 基础版；内容级智能分析属 P1 |
| `agentflow/generators/agents_md.py` | Jinja2 渲染 `AGENTS.md`（六段式），已存在时拒绝覆盖 | ✅ 已实现；增量更新属 P1 |
| `agentflow/generators/cursor_rules.py` | `.cursor/rules/agentflow.mdc` 生成 | 模板就绪，逻辑待实现（P1） |
| `agentflow/plugins/bridge.py` | Cursor/VS Code 插件的本地 HTTP 桥 | P2 占位 |
| `agentflow/cli/` | Typer 命令树：init/start/check/advance/status/guard/test | ✅ 已实现 |
| `agentflow/templates/` | Jinja2 模板（随包分发，importlib.resources 读取） | ✅ 已交付 |

## 数据流

### 1. init（规则生成）

```
agentflow init
  ├─ AgentFlowConfig(默认值) ──save()──> agentflow.yaml
  └─ ProjectScanner.scan(cwd) ──> ProjectProfile
       └─ AgentsMdGenerator ──渲染 templates/agents_md.md.j2──> AGENTS.md
            （已存在时跳过；.cursor/rules 生成属 P1）
```

### 2. start → advance（流程状态机）

```
agentflow start "任务描述" [--size]
  ├─ TaskRouter.route(TaskProfile) ──> 阶段序列（来自 workflow.{small,medium,large}）
  └─ TaskState.create ──> .agentflow/state.json；事件追加 session.jsonl

agentflow advance
  └─ WorkflowStateMachine(phases, DEFAULT_ARTIFACT_SPECS, validator, start_index=state.index)
       ├─ advance() ──> ArtifactValidator.check(当前阶段)
       │                  ├─ 齐备 → state.index += 1，写回 state.json，记 phase_advanced
       │                  └─ 缺失 → TransitionResult(allowed=False, missing_artifacts)，记 advance_blocked
       └─ done 为终态，不可再推进
```

### 3. guard（安全护栏）

```
agentflow guard --command "..." / --file path [--delete]
  └─ GuardrailEngine
       ├─ check_file_change：deny_paths → delete×protected → allow 白名单
       │                     → forbid_new_dependencies×依赖清单 → protected 提示 → 放行
       ├─ check_command：CommandRuleSet（子串、大小写不敏感）
       └─ preview_and_confirm（供编程调用）：require_diff_preview=true 时强制
          DiffPreviewer（git diff vs HEAD，非 git 退化内容摘要）→ y/n/a 确认
       拦截结果记入 session.jsonl（guard_denied）
```

### 4. test（测试闭环）

```
agentflow test
  └─ RepairLoop(TestRunner, workflow.max_retries)
       ├─ TestRunner.run()：shell 执行 testing.command（cwd=项目根，UTF-8 容错解码，
       │   超时计失败）→ TestReport
       ├─ 每次执行后 on_attempt：写 .agentflow/test-report.json + 记 session 事件
       ├─ 失败 → request_fix：输出 failure_excerpt（尾部 30 行），
       │   交互环境按回车重试 / q 放弃；非交互环境直接停止
       └─ 通过 → 提示可 advance（test 阶段的产物证据即 test-report.json）
```

## 依赖方向（禁止反向）

```
cli ──> core / guard / testing / generators ──> models ──> core.state_machine（枚举与校验函数）
core.artifacts ──> guard.file_rules（复用 glob_match）
```

`models.config` 是配置 schema 的单一来源：guard / testing / generators 的默认行为
全部引用 `models.config` 中的默认值（如 `DEFAULT_BLOCKED_COMMAND_PATTERNS`），
不允许各模块私藏一份默认配置。产物规格的默认值统一在 `core.artifacts.DEFAULT_ARTIFACT_SPECS`。

## 关键设计决策

- **只进不退**：状态机不允许回退；测试失败的「打回」由 RepairLoop 在 implement↔test
  语义层完成，表现为 test 阶段多次执行，而非状态回退。
- **glob 语义自实现**（`guard.file_rules.glob_match`）：`Path.glob`/`fnmatch` 对
  `**` 的跨版本行为不一致，自行编译正则保证 `**` 跨目录、`*` 单段、无斜杠模式
  匹配任意深度的 gitignore 风格语义；产物校验与文件护栏共用同一实现。
- **产物排除目录**（`core.artifacts.EXCLUDED_DIRS`）：`.venv`/`node_modules` 等
  不算「代码改动」；`.agentflow` 不排除——test-report.json 是 test 阶段合法产物。
- **护栏预演与执行分离**：`agentflow guard` 只裁决不执行；`preview_and_confirm`
  供编程调用（未来 Agent 桥/插件复用同一入口）。

## 下一步（P1 建议顺序）

1. `guard/diff_preview` 接入文件写入路径：提供「受控写入 API」，Agent 桥写文件前强制走预览确认
2. `generators/cursor_rules.py` 渲染 `.mdc` + AGENTS.md 增量更新（区块标记合并）
3. 产物规格支持在 `agentflow.yaml` 中按项目自定义（当前用代码内默认值）
4. 会话日志分析：`agentflow log` 命令回放 / 统计
