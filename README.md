# Python Agent - Learning Claude Code Architecture

通过逐步实现，学习 Claude Code 的 Agent 架构。

## 核心问题

**Claude Code 如何让 LLM 稳定地、自主地完成复杂的工程任务？**

Claude Code 的优势不在模型更强，而在于架构设计。本项目通过自己动手实现，理解这些设计。

## 学习路线

```
阶段 1: 基础概念（已完成）→ 阶段 2: 实现简化版 → 阶段 3: 对源码
     ↓                        ↓                       ↓
  理解每个组件做什么        动手写代码理解原理      找到真实实现
```

### 阶段 1: 基础概念 ✅

| # | 概念 | 核心问题 |
|---|------|----------|
| 1 | Tool 定义 | 工具的"说明书"长什么样？ |
| 2 | Tool 执行 | LLM 说了"用 bash"，怎么真的执行？ |
| 3 | Tool 结果 | 怎么把结果喂回 LLM？ |
| 4 | 主循环 | while True 背后的逻辑是什么？ |
| 5 | 权限控制 | 哪些操作需要用户确认？ |
| 6 | 错误处理 | 工具失败了怎么办？ |
| 7 | System Prompt | LLM 怎么知道"我是谁"？ |
| 8 | 上下文压缩 | 对话太长怎么处理？ |
| 9 | 流式输出 | 怎么实现打字机效果？ |
| 10 | 子 Agent | 怎么管理多个 Agent？ |
| 11 | Skill | 怎么让 Agent 学会新技能？ |

### 阶段 2: 实现简化版

| # | 模块 | 对应能力 | 状态 |
|---|------|----------|------|
| F01 | Tool Protocol | 定义工具接口 | ⬜ pending |
| F02 | Agent 主循环 | while True + 工具调度 | ⬜ pending |
| F03 | Bash 工具 | 执行 shell 命令 | ⬜ pending |
| F04 | 文件读取 | 读取文件内容 | ⬜ pending |
| F05 | 文件写入 | 创建/修改文件 | ⬜ pending |
| F06 | 搜索工具 | 在文件中搜索 | ⬜ pending |
| F07 | 权限检查 | 控制危险操作 | ⬜ pending |
| F08 | 上下文压缩 | 处理长对话 | ⬜ pending |

### 阶段 3: 对比 Claude Code 源码

实际去 Claude Code 仓库里找对应实现，对比差异。

## 项目结构

```
python-agent/
│
│   ── Harness 基础设施 ──────────────────────────
│
├── CLAUDE.md               # Agent 操作手册 (harness 指令)
├── feature_list.json       # 功能清单 (scope 控制 + 进度追踪)
├── claude-progress.md      # Session 进度日志 (状态持久化)
├── specs/                  # 功能 Spec 文件 (先写 spec 再写代码)
│   └── F01-tool-protocol.md
├── init.sh                 # 环境初始化脚本 (session lifecycle)
├── Makefile                # 验证命令入口 (verification)
│
│   ── 项目代码 ──────────────────────────────────
│
├── src/agent/              # 主代码
│   ├── core/               # 核心模块
│   │   └── types.py        # 基础类型定义
│   ├── tools/              # 工具实现 (待开发)
│   ├── permissions/        # 权限管理 (待开发)
│   └── context/            # 上下文管理 (待开发)
├── tests/                  # 测试文件 (待开发)
├── examples/               # 示例代码 (待开发)
│
│   ── 配置 ──────────────────────────────────────
│
├── pyproject.toml          # 项目配置和依赖
└── .gitignore
```

## 开发流程

```
读 feature_list.json → 读 spec → 写代码 → 跑测试 → 提交
```

详见 [CLAUDE.md](CLAUDE.md)。

## 快速开始

```bash
# 克隆项目
git clone https://github.com/L-congliang/python-agent.git
cd python-agent

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 安装依赖（可编辑模式）
pip install -e .

# 验证安装
python -c "from agent import __version__; print(__version__)"
```

## 技术栈

- **Python**: 3.12+
- **AI SDK**: `anthropic`
- **数据验证**: `pydantic`
- **测试**: `pytest`

## 学习笔记

详见 [LEARNING_PROGRESS.md](LEARNING_PROGRESS.md) 和 [docs/](docs/) 目录。

## License

MIT
