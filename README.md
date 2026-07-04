# Cool Code

一个用 Python 构建的终端 AI 编程助手，架构对齐 Claude Code。

## 这是什么

Cool Code 是一个运行在终端里的 AI 编程 Agent。它能：

- **执行 shell 命令** — 运行测试、构建项目、Git 操作
- **读写文件** — 理解代码库、精确编辑文件
- **搜索代码** — 正则搜索、文件发现、内容定位
- **自主循环** — 调用工具、处理结果、继续推理，直到任务完成
- **多 Agent 协作** — 主 Agent 派生子 Agent 并行执行任务
- **上下文管理** — 预算制 token 组织、滑动窗口压缩、分层记忆系统
- **鲁棒性保护** — 重复拦截、路径逃逸防护、重试上限
- **可观测性** — Trace 事件、断点续传、会话持久化

技术栈：Python 3.12+ / mimo v2.5pro 模型 / rich 终端 UI / prompt_toolkit 交互

## 架构

```
src/agent/
├── core/               # 核心层
│   ├── model.py        #   模型客户端（mimo API，流式输出）
│   ├── model_adapter.py #   ModelAdapter 协议 + ToolCall
│   ├── loop.py         #   Agent 主循环（调用→解析→执行→循环）
│   ├── types.py        #   基础类型定义
│   ├── context.py      #   工具执行上下文
│   └── adapters/       #   模型适配器（mimo/deepseek）
│
├── tools/              # 工具层（8 个工具）
│   ├── base.py         #   Tool Protocol（对齐 Claude Code）
│   ├── registry.py     #   工具注册中心
│   ├── bash.py         #   Bash 工具
│   ├── file_read.py    #   文件读取（文本 + Notebook）
│   ├── file_write.py   #   文件写入
│   ├── file_edit.py    #   文件编辑（局部替换）
│   ├── grep.py         #   代码搜索（ripgrep 封装）
│   ├── glob.py         #   文件发现（pathlib glob）
│   └── subagent.py     #   子 Agent 工具（阻塞/后台模式）
│
├── orchestration/      # 多 Agent 编排
│   ├── agent_type.py   #   Agent 类型系统（类型注册表）
│   ├── sub_agent.py    #   子 Agent 数据结构（约束/结果/任务）
│   └── message_bus.py  #   后台任务管理（TaskManager）
│
├── memory/             # 分层记忆系统
│   ├── working.py      #   工作记忆（LRU 文件访问）
│   ├── file_summaries.py #  文件摘要（180 字符 + freshness）
│   ├── episodic.py     #   事件笔记（12 条 + 去重）
│   ├── durable.py      #   持久记忆（跨 session）
│   ├── retrieval.py    #   检索（标签 + 关键词）
│   ├── renderer.py     #   记忆渲染（紧凑格式）
│   └── manager.py      #   统一接口
│
├── context/            # 上下文管理
│   ├── token_counter.py #  Token 精确计数
│   ├── manager.py      #   ContextManager 预算制组装
│   └── compressor.py   #   滑动窗口 + LLM 摘要压缩
│
├── robustness/         # 工具鲁棒性
│   ├── task_state.py   #   任务状态机
│   ├── repeat_detector.py # 重复调用检测
│   ├── path_guard.py   #   路径逃逸防护
│   └── retry_limiter.py #  重试上限
│
├── observability/      # 可观测性
│   ├── trace.py        #   TraceEmitter 事件发射器
│   ├── reporter.py     #   RunReporter 运行报告
│   ├── checkpoint.py   #   断点续传 + freshness 检测
│   ├── redactor.py     #   敏感信息脱敏
│   └── workspace.py    #   工作区快照
│
├── persistence/        # 持久化
│   ├── session_store.py #  会话持久化
│   └── run_store.py    #   运行工件存储
│
├── permissions/        # 权限层
│   └── checker.py      #   权限检查器（default/plan 模式）
│
├── evaluation/         # 评测框架
│   ├── benchmark.py    #   BenchmarkTask
│   ├── evaluator.py    #   Evaluator
│   ├── fake_client.py  #   FakeModelClient
│   ├── metrics.py      #   Metrics + RegressionReport
│   └── recovery_experiment.py # Recovery Ablation 实验
│
└── cli/                # 交互层
    └── app.py          #   终端 UI（Markdown 渲染、工具面板、流式输出）
```

**核心流程**：用户输入 → 模型推理 → 生成工具调用 → 执行工具 → 结果注入 → 继续推理 → 循环

## 路线图

### P0：评测框架 + 基础能力 ✅

让 Agent 能跑起来的最小可用版本。

| 功能 | 模块 | 状态 |
|------|------|------|
| 模型层 | `core/model.py` | ✅ |
| CLI 框架 | `cli/app.py` | ✅ |
| Tool Protocol | `tools/base.py` + `tools/registry.py` | ✅ |
| Agent 主循环 | `core/loop.py` | ✅ |
| Bash 工具 | `tools/bash.py` | ✅ |
| 文件读取 | `tools/file_read.py` | ✅ |
| 文件写入 | `tools/file_write.py` + `tools/file_edit.py` | ✅ |
| 搜索工具 | `tools/grep.py` + `tools/glob.py` | ✅ |
| 权限检查 | `permissions/checker.py` | ✅ |
| 上下文压缩 | `context/compressor.py` | ✅ |
| 评测框架 | `evaluation/` | ✅ |

### P1：上下文工程 ✅

Token 精确计数 + 预算制组装 + 优先级裁剪。

| 功能 | 模块 | 状态 |
|------|------|------|
| TokenCounter | `context/token_counter.py` | ✅ |
| ContextManager | `context/manager.py` | ✅ |
| AgentLoop 集成 | `core/loop.py` | ✅ |

### P2：分层记忆系统 ✅

工作记忆 → 事件笔记 → 持久记忆，三级记忆协同。读路径（注入 prompt）+ 写路径（自动回写）完整闭环。

| 功能 | 模块 | 状态 |
|------|------|------|
| WorkingMemory | `memory/working.py` | ✅ |
| FileSummaries | `memory/file_summaries.py` | ✅ |
| EpisodicNotes | `memory/episodic.py` | ✅ |
| DurableMemory | `memory/durable.py` | ✅ |
| Retrieval | `memory/retrieval.py` | ✅ |
| MemoryManager | `memory/manager.py` | ✅ |
| 写路径闭环 | `core/loop.py`（set_task / touch_file / update_file_summary / append_note / save） | ✅ |
| memory_enabled 开关 | `core/loop.py`（支持 memory_on/off 对照实验） | ✅ |
| tool_history | `core/loop.py`（结构化工具执行历史，支撑评测统计） | ✅ |
| 真实评测 | `evaluation/memory_experiment.py`（correct / repeated_reads / memory_hit 真实统计） | ✅ |

### P3：工具鲁棒性 ✅

错误恢复 + 重复拦截 + 安全防护。

| 功能 | 模块 | 状态 |
|------|------|------|
| TaskState | `robustness/task_state.py` | ✅ |
| RepeatDetector | `robustness/repeat_detector.py` | ✅ |
| PathGuard | `robustness/path_guard.py` | ✅ |
| RetryLimiter | `robustness/retry_limiter.py` | ✅ |

### P4：可观测性 ✅

Trace 事件 + 断点续传 + 会话持久化。

| 功能 | 模块 | 状态 |
|------|------|------|
| TraceEmitter | `observability/trace.py` | ✅ |
| RunReporter | `observability/reporter.py` | ✅ |
| CheckpointManager | `observability/checkpoint.py` | ✅ |
| Redactor | `observability/redactor.py` | ✅ |
| SessionStore | `persistence/session_store.py` | ✅ |
| RunStore | `persistence/run_store.py` | ✅ |

### P5：多 Agent 路由 ✅

子 Agent 派生 + 类型系统 + 后台执行 + worktree 隔离。

| 功能 | 模块 | 状态 |
|------|------|------|
| SubAgentTool | `tools/subagent.py` | ✅ |
| AgentTypeRegistry | `orchestration/agent_type.py` | ✅ |
| SubAgentConstraints | `orchestration/sub_agent.py` | ✅ |
| TaskManager | `orchestration/message_bus.py` | ✅ |

### P6：意图识别与 Prompt 工程 ✅

System Prompt 优化 + 意图分类 + Plan Mode。

| 功能 | 模块 | 状态 |
|------|------|------|
| SystemPromptBuilder | `prompts/builder.py` | ✅ |
| Plan Mode | `core/loop.py` + `permissions/checker.py` | ✅ |
| Prompt Ablation 实验 | `experiments/prompt_ablation.py` | ✅ |

**验证结果**：Identity 贡献 +333%，avg_attempts -35%

### 安全加固 ✅

| 功能 | 模块 | 状态 |
|------|------|------|
| Shell 环境变量白名单 | `tools/bash.py` | ✅ |
| CLI 入口点 | `pyproject.toml` | ✅ |

## 快速开始

```bash
# 克隆
git clone https://github.com/L-congliang/python-agent.git
cd python-agent

# 环境（uv 自动创建虚拟环境）
uv sync

# 启动
agent                    # 直接启动 CLI
# 或
python -m agent.main     # 等效方式

# 运行测试
uv run pytest tests/ -x -v

# 完整验证（类型检查 + 测试）
uv run make check
```

## 技术栈

- **模型**: mimo v2.5pro（小米），通过 Anthropic 兼容 API 调用
- **终端 UI**: rich（渲染）+ prompt_toolkit（输入交互）
- **数据验证**: pydantic
- **测试**: pytest + mypy --strict
- **Python**: 3.12+

## License

MIT

## Contributing

Contributions are welcome! Please open an issue first.
