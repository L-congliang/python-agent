## Context

项目已有基线：
- AgentLoop（流式调用 + 工具执行 + AbortController + 轮次保护）
- Tool Protocol（Protocol 模式，15 属性，fail-closed 默认值）
- ToolRegistry（注册/过滤/执行）
- MemoryManager（WorkingMemory + FileSummaries + EpisodicNotes + DurableMemory）
- 可观测性系统（TraceEmitter + RunReporter + CheckpointManager）

参照 Claude Code 的 AgentTool（233KB），需要实现多 Agent 编排能力。

约束：
- 不改变现有 AgentLoop 的核心循环逻辑
- 子 Agent 复用 AgentLoop，不新建轻量循环
- 代码质量标准：mypy --strict、测试覆盖

## Goals / Non-Goals

**Goals:**
- 实现 SubAgentTool，对齐 Claude Code 的 AgentTool 接口
- 实现 Agent 类型系统，支持按类型过滤工具集
- 子 Agent 继承父 Agent 的记忆（通过 system prompt 注入）
- 支持嵌套子 Agent，通过共享约束防止无限递归
- 支持后台执行模式，通过 TaskManager 管理异步任务
- 支持 worktree 隔离模式

**Non-Goals:**
- 不做远程 Agent（remote isolation）— 需要云环境支持，超出范围
- 不做 Workflow 编排（pipeline/parallel）— 这是更高级的编排，P5 只做基础子 Agent
- 不做 Agent 间消息传递（SendMessage）— 子 Agent 是一次性执行，不需要持续对话
- 不做 Agent 类型的动态注册（frontmatter 文件）— 内置类型足够

## Decisions

### D1: 子 Agent 复用 AgentLoop 而非新建轻量循环

**选择：** 子 Agent = AgentLoop 实例，通过 LoopConfig 关闭不需要的功能。

**替代方案：**
- A) 新建 SubAgentLoop（精简版循环）— 需要维护两套循环代码
- B) 用协程/线程隔离 — 复杂度高，收益不明显

**理由：**
1. 复用 AgentLoop 的所有现有能力（鲁棒性、trace、工具执行）
2. 通过配置关闭不需要的功能（enable_trace=False, enable_checkpoint=False）
3. 面试时能讲清楚"我选择复用而不是重写，因为维护两套循环代码的成本更高"

**子 Agent 的 LoopConfig 差异：**
```
max_turns: 20（默认，比主 Agent 的 50 小）
max_tool_calls: 50（默认，比主 Agent 的 100 小）
enable_trace: False（嵌套到主 Agent 的 trace）
enable_checkpoint: False（子 Agent 不需要 checkpoint）
system_prompt: 包含父 Agent 的记忆渲染
```

### D2: 记忆通过 system prompt 注入，不共享 MemoryManager 实例

**选择：** 子 Agent 创建时，将父 Agent 的 memory.render() 输出注入子 Agent 的 system prompt。子 Agent 有独立的空 MemoryManager。

**替代方案：**
- A) 子 Agent 共享父 Agent 的 MemoryManager 实例 — 子 Agent 的修改会污染父 Agent
- B) 子 Agent 完全不继承记忆 — 子 Agent 缺少上下文，可能重复读文件

**理由：**
1. system prompt 注入是只读的，子 Agent 不能修改父 Agent 的记忆
2. 子 Agent 知道父 Agent 之前读过什么文件，避免重复读取
3. 子 Agent 的 MemoryManager 是独立的，执行完销毁，不污染父 Agent
4. 面试时能讲清楚"记忆通过 prompt 注入而不是共享实例，保证状态隔离"

### D3: Agent 类型系统驱动工具集过滤

**选择：** AgentTypeRegistry 定义内置类型，每个类型指定 allowed_tools。子 Agent 创建时按类型过滤父 Agent 的 ToolRegistry。

**替代方案：**
- A) 主 Agent 在调用 subagent 时手动指定 tools 列表 — 灵活但容易出错
- B) 子 Agent 默认继承全部工具 — 子 Agent 可能误用高危工具（如 bash）

**理由：**
1. 类型系统让主 Agent 声明意图（"我需要一个 explorer"），系统自动配置
2. 类型定义集中管理，容易审计和修改
3. 主 Agent 仍然可以通过 subagent 的参数覆盖工具集（灵活）

**内置类型：**
```
general-purpose: 所有工具，完整能力
explore: 只读工具（read, grep, glob, bash），轻量探索
code-reviewer: 只读工具（read, grep, glob），代码审查
```

### D4: 嵌套子 Agent 通过 SubAgentConstraints 共享约束

**选择：** 允许嵌套子 Agent，通过 SubAgentConstraints 跨层级共享 token budget、abort signal、agent counter。

**替代方案：**
- A) 禁止嵌套 — 实现简单，但限制了复杂任务的分解能力
- B) 允许嵌套但不共享约束 — 子 Agent 可能无限递归

**理由：**
1. Claude Code 允许嵌套，面试时能讲清楚"我完全对齐了 Claude Code 的设计"
2. 共享约束防止无限递归：agent_counter 上限 100，token_budget 跨层级共享
3. 共享 abort_controller：父 Agent abort → 所有子 Agent abort

**SubAgentConstraints 结构：**
```python
@dataclass
class SubAgentConstraints:
    token_budget: int | None       # 总 token 预算（None = 不限制）
    tokens_spent: int              # 已消耗
    agent_counter: int             # 已创建的 agent 数
    max_agents: int = 100          # 全局上限
    abort_controller: AbortController  # 共享的中断控制器
```

### D5: 后台执行通过 TaskManager 管理

**选择：** SubAgentTool 支持 run_in_background=True，通过 TaskManager 在独立线程中执行子 Agent。

**替代方案：**
- A) 只支持阻塞模式 — 简单，但主 Agent 必须等待子 Agent 完成
- B) 用 asyncio — 项目目前是同步的，引入 asyncio 改动太大

**理由：**
1. 后台模式让主 Agent 可以并行派生多个子 Agent
2. 线程足够简单，不需要引入 asyncio
3. TaskManager 管理所有后台任务的生命周期

**TaskManager 接口：**
```python
class TaskManager:
    def register(self, task: SubAgentTask) -> str  # 返回 task_id
    def get_status(self, task_id: str) -> str
    def get_result(self, task_id: str) -> SubAgentResult  # 阻塞等待
    def stop(self, task_id: str) -> None
```

### D6: SubAgentTool 返回结构化结果

**选择：** SubAgentTool 返回 SubAgentResult（包含 result + 元数据），而非纯文本。

**替代方案：**
- A) 返回纯文本（对齐 Claude Code）— 简单，但丢失执行元数据
- B) 返回 JSON 字符串 — 需要主 Agent 解析

**理由：**
1. 结构化结果包含 turns_used、tool_calls_used、tokens_used 等元数据
2. 主 Agent 可以用这些信息判断子 Agent 的执行质量
3. trace 和 reporter 可以记录这些元数据
4. 面试时能讲清楚"这是我对 Claude Code 的改进，纯文本丢失了太多信息"

**SubAgentResult 结构：**
```python
@dataclass
class SubAgentResult:
    result: str                    # 最终回复文本
    status: str                    # "completed" | "stopped" | "failed"
    turns_used: int                # 实际轮次
    tool_calls_used: int           # 实际工具调用次数
    tokens_used: int               # 消耗的 token
    agent_type: str                # 使用的 agent 类型
    error: str | None = None       # 错误信息（如果失败）
```

### D7: worktree 隔离通过 git worktree 实现

**选择：** 子 Agent 指定 isolation="worktree" 时，创建 git worktree，子 Agent 在独立目录中执行。

**替代方案：**
- A) 用 Docker 容器隔离 — 依赖 Docker，不适合本地 CLI 工具
- B) 用 tmpdir 隔离 — 没有 git 历史，子 Agent 无法使用 git 命令

**理由：**
1. git worktree 是 git 原生功能，不需要额外依赖
2. 子 Agent 有完整的 git 历史，可以正常使用 git 命令
3. 执行完后可以选择合并或丢弃 worktree

**worktree 流程：**
```
1. git worktree add .worktrees/<task_id> -b subagent-<task_id>
2. 子 Agent 的 workspace_root 指向 worktree
3. 子 Agent 执行
4. 执行完后: git worktree remove .worktrees/<task_id>
```

## Risks / Trade-offs

**[R1] 子 Agent 复用 AgentLoop 可能导致资源浪费**
→ 缓解：通过 LoopConfig 关闭不需要的功能（trace、checkpoint、memory load）。子 Agent 的实际开销主要是模型调用，循环本身的开销可忽略。

**[R2] 嵌套子 Agent 可能导致 token 消耗失控**
→ 缓解：SubAgentConstraints 共享 token_budget，跨层级追踪消耗。max_agents=100 作为硬上限。

**[R3] 后台执行的线程安全问题**
→ 缓解：TaskManager 用 threading.Lock 保护共享状态。子 Agent 的 AbortController 是共享的，abort 操作是线程安全的。

**[R4] worktree 隔离可能残留未清理的 worktree**
→ 缓解：子 Agent 执行完后自动清理。如果进程异常退出，下次启动时检查并清理孤立 worktree。

**[R5] 子 Agent 继承记忆可能导致 system prompt 过长**
→ 缓解：只继承 memory.render_compact() 输出（更紧凑的格式）。如果仍然过长，截断到固定大小。
