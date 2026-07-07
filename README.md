# Python Code Agent

一个参考 Claude Code / Codex 思路实现的本地 Python code agent demo，重点在多轮 agent loop、工具调用闭环、权限确认、文件编辑安全和回归测试，而不是完整复刻生产级 AI IDE。

## 项目简介

这个项目的目标是让 agent 在本地 workspace 内完成：

- 多轮对话
- 工具调用与结果回注
- 文件读取 / 写入 / 编辑
- shell 执行与代码搜索
- 高风险操作的用户确认
- 基本的 workspace 安全边界

当前状态更适合定义为：

`Demo / 展示级（可现场演示，安全边界较清晰）`

## 当前能力

- 多轮 `AgentLoop`
- `ToolRegistry` 统一管理工具注册、校验和执行
- 基础工具：
  - `bash`
  - `read`
  - `write`
  - `edit`
  - `grep`
  - `glob`
- `ALLOW / ASK / DENY` 权限系统
- CLI confirmation handler
- `file_edit` unified diff preview
- `file_edit` 原子写入失败保护
- workspace path guard
- 任务级 e2e regression
- **Observation Budget 契约**：工具输出的 preview + artifact 双层机制
- **统一截断逻辑**：bash/read/grep/glob/edit 的长输出统一处理
- **CLI 截断提示**：用户能看到"输出已截断，完整结果在 xxx"
- **Backup / Rollback / Edit History**：write/edit 前备份，支持 /history 和 /rollback latest
- **Session 级 Permission Policy**：减少重复 ASK，支持 allow-once / allow-session
- **真实远程 LLM Smoke**：验证真实 API 链路没断（需 RUN_REAL_LLM_SMOKE=1 + MIMO_API_KEY）
- 中文文档包，适合 demo、复习和面试准备

## 架构概览

核心链路：

`user input -> AgentLoop -> model -> tool call -> ToolRegistry -> tool execution -> tool result -> next turn / final answer`

主要模块：

- `src/agent/main.py`
  - 默认入口装配
- `src/agent/core/loop.py`
  - 多轮调度、权限检查、工具执行
- `src/agent/tools/registry.py`
  - 工具注册与统一执行入口
- `src/agent/tools/`
  - 文件、shell、搜索工具
- `src/agent/permissions/checker.py`
  - 权限策略
- `src/agent/cli/app.py`
  - 终端 UI 和确认交互

更详细的代码地图见：

- `docs/agent-improvement/02-code-map.md`

## 快速开始

### 1. 环境要求

- Python `>=3.11`
- 推荐使用 `uv`

安装 `uv`：

```bash
pip install uv
```

### 2. 安装依赖

```bash
git clone https://github.com/L-congliang/python-agent.git
cd python-agent
uv sync
```

## 配置方式

真实 CLI 运行需要配置：

```bash
MIMO_API_KEY=your_api_key
```

可选环境变量：

```bash
MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/anthropic
MIMO_MODEL=mimo-v2.5-pro
```

如果没有 API key，仍然可以跑本地 smoke test、模块测试和 fake-model e2e。

## 运行 CLI

```bash
uv run python -m agent.main
```

或：

```bash
uv run agent
```

CLI 支持：

- `/help`
- `/clear`
- `/reset`
- `/compact`

高风险工具调用在 CLI 中会触发确认面板：

- `bash`
- `write`
- `edit`

## 运行测试

推荐先跑入口 smoke test 和任务级 e2e：

```bash
uv run pytest tests/test_main_smoke.py -q
uv run pytest tests/test_e2e_agent_workflow.py -q
```

常用测试：

```bash
uv run pytest tests/test_agent_loop.py -q
uv run pytest tests/test_cli.py -q
uv run pytest tests -q
```

## Demo Walkthrough

推荐阅读：

- `docs/agent-improvement/08-demo-walkthrough.md`

最短演示路径：

1. 跑 `tests/test_e2e_agent_workflow.py`
2. 解释它证明了什么
3. 说明这一步不需要 API key，使用的是 fake-model e2e
4. 配好 API key 后启动 CLI
5. 演示一次 `edit` 的 diff preview + 用户确认
6. 再展示 workspace guard 和默认拒绝覆盖

## 安全设计

- `ALLOW / ASK / DENY`
- `ASK` 必须通过 confirmation handler 才能执行
- 无 confirmation handler 时默认 fail closed
- `write` 默认不覆盖已有文件，需显式 `overwrite=true`
- `edit` 支持 diff preview
- `edit` apply 使用原子写入，避免失败时破坏原文件
- `grep / glob / read / write / edit` 都受 workspace guard 限制
- `bash` 具备超时、输出截断和环境变量白名单

## 当前限制

- 还不是 production-ready
- sandbox 不是 OS-level isolation
- `file_edit` 还没有完整 rollback 工作流
- 当前任务级 e2e 使用 fake model，不是远程 LLM e2e
- 真实 CLI 运行仍需要 API key
- 当前不主打 MCP / WebUI / 多 agent 并行 / 长期记忆检索产品化
- artifact 保存是本地文件，没有跨 session 持久化

## Roadmap

短期更值得做的是：

- `main.py` 默认装配 smoke test 之后的 demo polish
- 更清晰的 CLI walkthrough
- 更完整的文件编辑恢复方案
- 更稳定的 integration / smoke coverage

当前 roadmap 见：

- `docs/agent-improvement/07-next-roadmap.md`
