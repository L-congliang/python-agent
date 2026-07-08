# Demo Walkthrough

## 1. Demo 目标

这份 demo 主要证明六件事：

- agent 能读取代码
- agent 能通过 tool call 修改代码
- 高风险修改需要用户确认
- 修改前能看到 diff
- 修改后能跑测试
- workspace guard 能阻止越界访问

## 2. Demo 环境准备

### Python / 包管理

- Python `>=3.11`
- 推荐使用 `uv`

安装：

```bash
pip install uv
uv sync
```

### 进入项目目录

```bash
cd python-agent
```

### 环境变量

真实 CLI 演示需要：

```bash
MIMO_API_KEY=your_api_key
```

可选：

```bash
MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/anthropic
MIMO_MODEL=mimo-v2.5-pro
```

### 没有 API key 时能做什么

没有 API key 也可以跑：

- `tests/test_main_smoke.py`
- `tests/test_e2e_agent_workflow.py`
- `tests/test_agent_loop.py`
- `tests/test_cli.py`
- `pytest tests -q`

这些测试不依赖真实远程 LLM。

### 三条演示路线对 API key 的要求

- 路线 A：不需要 API key，使用本地测试和 fake model 证明主链路。
- 路线 B：需要真实 `MIMO_API_KEY`，因为要启动真实 CLI 并走真实模型调用。
- 路线 C：默认不需要 API key，可以直接通过测试和权限交互说明安全边界。

## 3. Demo 路线 A：测试驱动演示

这一条路线不需要真实 API key。

### 命令 1

```bash
uv run pytest tests/test_e2e_agent_workflow.py -q
```

它证明：

- agent 能完成真实任务级闭环
- 包括读文件、编辑 bug、跑测试、权限拒绝/批准、workspace guard

### 命令 2

```bash
uv run pytest tests/test_agent_loop.py -q
```

它证明：

- loop 层的权限分支、工具调用和核心调度逻辑是稳定的

### 命令 3

```bash
uv run pytest tests/test_cli.py -q
```

它证明：

- CLI confirmation handler
- `/reset`
- `/compact`
- fallback 行为

### 命令 4

```bash
uv run pytest tests -q
```

它证明：

- 当前仓库的整体测试状态是稳定的

## 4. Demo 路线 B：真实 CLI 演示

这条路线需要真实 API key。

### 步骤 1：准备一个小场景

可以在单独目录准备：

`calculator.py`

```python
def add(a, b):
    return a - b
```

`test_calculator.py`

```python
from calculator import add

def test_add():
    assert add(1, 2) == 3
```

### 步骤 2：启动 agent

```bash
uv run python -m agent.main
```

### 步骤 3：输入任务

可以直接说：

```text
请读取 calculator.py，修复 add 函数的 bug，然后运行测试。
```

### 步骤 4：观察 CLI

理想路径是：

1. agent 调用 `read`
2. agent 提出 `edit`
3. CLI 展示 diff preview
4. CLI 询问是否允许执行
5. 用户输入 `y`
6. agent 应用修改
7. agent 调用 `bash` 运行测试
8. 输出修复完成

## 5. Demo 路线 C：安全边界演示

这一条路线默认不需要真实 API key；其中 workspace guard 最稳妥的做法是直接跑现有 e2e 来证明。

### 演示 1：拒绝 ASK 不会写文件

- 当 CLI 询问是否允许 `write` 或 `edit` 时，输入 `n`
- 文件不会被修改

### 演示 2：直接回车默认拒绝

- 在确认提示下直接回车
- 行为等同拒绝

### 演示 3：workspace 外 grep/glob 被拒绝

推荐直接用：

```bash
uv run pytest tests/test_e2e_agent_workflow.py -q
```

然后解释第三个 e2e 用例就是在验证这个边界。

### 演示 4：write 默认不覆盖已有文件

可以说明：

- `write` 只适合新建文件
- 目标存在时需要显式 `overwrite=true`

### 演示 5：edit 多处匹配时拒绝

可以说明：

- `old_string` 多处匹配且 `replace_all=false` 时会失败
- 这是为了避免模糊替换误改代码

## 6. 面试现场怎么演示

推荐顺序：

1. 先讲项目目标
2. 再讲 `AgentLoop -> ToolRegistry -> tools`
3. 先跑 `tests/test_e2e_agent_workflow.py`
4. 再展示一次真实 CLI 的确认面板
5. 最后诚实说明没做的部分

可以照着说：

> 这个项目是一个本地 Python code agent demo，我重点做的是多轮 tool-calling 闭环、权限确认、文件编辑安全和任务级回归测试。  
> 我先用 e2e 测试证明它不是只堆工具，然后再用真实 CLI 展示高风险编辑前的 diff preview 和用户确认。  
> 当前它适合定位成 demo / prototype 之前的扎实作品，还不是 production-ready，也没有 MCP、WebUI 和完整 rollback。
