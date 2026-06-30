# Cool Code

一个用 Python 构建的终端 AI 编程助手，架构对齐 Claude Code。

## 这是什么

Cool Code 是一个运行在终端里的 AI 编程 Agent。它能：

- **执行 shell 命令** — 运行测试、构建项目、Git 操作
- **读写文件** — 理解代码库、修改文件（开发中）
- **搜索代码** — 在项目中查找内容（开发中）
- **自主循环** — 调用工具、处理结果、继续推理，直到任务完成

技术栈：Python 3.12+ / mimo v2.5pro 模型 / rich 终端 UI / prompt_toolkit 交互

## 架构

```
src/agent/
├── core/               # 核心层
│   ├── model.py        #   模型客户端（mimo API，流式输出）
│   ├── loop.py         #   Agent 主循环（调用→解析→执行→循环）
│   ├── types.py        #   基础类型定义
│   └── context.py      #   工具执行上下文
│
├── tools/              # 工具层
│   ├── base.py         #   Tool Protocol（对齐 Claude Code）
│   ├── registry.py     #   工具注册中心
│   └── bash.py         #   Bash 工具（shell 命令执行）
│
├── cli/                # 交互层
│   └── app.py          #   终端 UI（Markdown 渲染、工具面板）
│
├── permissions/        # 权限层（开发中）
└── context/            # 上下文管理（开发中）
```

**核心流程**：用户输入 → 模型推理 → 生成工具调用 → 执行工具 → 结果注入 → 继续推理 → 循环

## 路线图

### 阶段 1：核心骨架（F01-F10）

让 Agent 能跑起来的最小可用版本。

| 功能 | 模块 | 状态 |
|------|------|------|
| 模型层 | `core/model.py` | ✅ |
| CLI 框架 | `cli/app.py` | ✅ |
| Tool Protocol | `tools/base.py` + `tools/registry.py` | ✅ |
| Agent 主循环 | `core/loop.py` | ✅ |
| Bash 工具 | `tools/bash.py` | ✅ |
| 文件读取 | `tools/file_read.py` | 🔜 |
| 文件写入 | `tools/file_write.py` | 🔜 |
| 搜索工具 | `tools/grep.py` | 🔜 |
| 权限检查 | `permissions/checker.py` | 🔜 |
| 上下文压缩 | `context/compressor.py` | 🔜 |

### 阶段 2：能力扩展（F11-F15）

补齐 Claude Code 的核心能力，从"能用"到"好用"。

| 功能 | 模块 | 说明 |
|------|------|------|
| Glob 文件查找 | `tools/glob.py` | 按模式匹配查找文件 |
| Sub-agent 派生 | `core/subagent.py` | 主 Agent 派生子 Agent 并行执行 |
| MCP 集成 | `tools/mcp.py` | 连接外部工具服务 |
| Session 持久化 | `context/session.py` | 对话历史持久化，跨 session 记忆 |
| Hooks 系统 | `core/hooks.py` | 工具调用前后的回调机制 |

## 快速开始

```bash
# 克隆
git clone https://github.com/L-congliang/python-agent.git
cd python-agent

# 环境
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # macOS/Linux

# 安装
pip install -e ".[dev]"

# 验证
python -m pytest tests/ -x -v
```

## 技术栈

- **模型**: mimo v2.5pro（小米），通过 Anthropic 兼容 API 调用
- **终端 UI**: rich（渲染）+ prompt_toolkit（输入交互）
- **数据验证**: pydantic
- **测试**: pytest
- **Python**: 3.12+

## License

MIT

## Contributing

Contributions are welcome! Please open an issue first.
