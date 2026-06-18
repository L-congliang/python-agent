# Claude Code 架构分析

本文档基于 Claude Code 泄露源码（2026-03-31 版本）的分析，用于指导 python-agent 项目的架构设计。

**核心原则：我们的工具数量可以少，但框架必须是工业级的，不是 demo。**

---

## 1. 整体架构

```
src/src/
├── main.tsx           # 入口（803KB），CLI 启动、参数解析、初始化
├── QueryEngine.ts     # 查询引擎，SDK 模式核心
├── query.ts           # 主循环：消息→API→流式解析→工具执行→循环（68KB）
├── Tool.ts            # Tool 类型定义 + buildTool() 工厂（核心地基）
├── tools.ts           # 工具注册表，getAllBaseTools()
├── commands.ts        # 斜杠命令（50+ 命令）
├── context.ts         # 系统上下文（git status、CLAUDE.md）
├── cost-tracker.ts    # 费用追踪
├── history.ts         # 会话历史
├── constants/
│   ├── prompts.ts     # 系统提示构建
│   └── system.ts      # 系统常量
├── services/
│   ├── api/           # API 调用层
│   ├── compact/       # 上下文压缩（auto-compact）
│   ├── mcp/           # MCP 协议支持
│   └── analytics/     # 遥测分析
├── tools/             # 60+ 工具实现
│   ├── BashTool/
│   ├── FileEditTool/
│   ├── FileReadTool/
│   ├── AgentTool/     # 子代理系统（233KB）
│   └── ...
├── utils/
│   ├── permissions/   # 权限系统
│   ├── model/         # 模型选择/切换
│   └── ...
└── types/             # TypeScript 类型定义
```

---

## 2. Tool 系统（最核心）

### 2.1 Tool 类型定义

Claude Code 的 Tool 是一个**完整的接口**，包含 30+ 个属性/方法：

```typescript
type Tool<Input, Output, Progress> = {
  // === 基本信息 ===
  name: string                    // 工具名
  aliases?: string[]              // 别名（重命名兼容）
  searchHint?: string             // ToolSearch 关键词
  maxResultSizeChars: number      // 结果超大时持久化到磁盘

  // === Schema ===
  inputSchema: ZodSchema          // 输入 schema（Zod）
  outputSchema?: ZodSchema        // 输出 schema
  inputJSONSchema?: object        // MCP 工具用 JSON Schema

  // === 行为标记 ===
  isEnabled(): boolean            // 是否启用
  isConcurrencySafe(input): boolean   // 能否并行执行
  isReadOnly(input): boolean      // 是否只读
  isDestructive(input): boolean   // 是否不可逆
  shouldDefer?: boolean           // 是否延迟加载（ToolSearch）
  alwaysLoad?: boolean            // 强制始终加载
  strict?: boolean                // API strict mode

  // === 权限 ===
  checkPermissions(input, context): PermissionDecision
  validateInput(input, context): ValidationResult
  preparePermissionMatcher(input): (pattern) => boolean

  // === 执行 ===
  call(input, context, canUseTool, parentMessage, onProgress): ToolResult

  // === UI 渲染（React/Ink）===
  description(input, options): string
  prompt(options): string
  userFacingName(input): string
  renderToolUseMessage(input, options): ReactNode
  renderToolResultMessage(content, progress, options): ReactNode
  renderToolUseProgressMessage(progress, options): ReactNode
  renderToolUseRejectedMessage(input, options): ReactNode
  renderToolUseErrorMessage(result, options): ReactNode
  renderGroupedToolUse?(toolUses, options): ReactNode

  // === 序列化 ===
  mapToolResultToToolResultBlockParam(content, toolUseID): ToolResultBlockParam
  toAutoClassifierInput(input): unknown
  getToolUseSummary(input): string | null
  getActivityDescription(input): string | null
  getPath?(input): string

  // === 中断 ===
  interruptBehavior?(): 'cancel' | 'block'
  isSearchOrReadCommand?(input): { isSearch, isRead, isList }
}
```

### 2.2 buildTool() 工厂函数

```typescript
const TOOL_DEFAULTS = {
  isEnabled: () => true,
  isConcurrencySafe: () => false,    // fail-closed
  isReadOnly: () => false,           // fail-closed
  isDestructive: () => false,
  checkPermissions: (input) => ({ behavior: 'allow', updatedInput: input }),
  toAutoClassifierInput: () => '',
  userFacingName: () => '',
}

export function buildTool<D>(def: D): BuiltTool<D> {
  return { ...TOOL_DEFAULTS, userFacingName: () => def.name, ...def }
}
```

**关键设计**：
- 默认值 fail-closed（假设不安全、会写入）
- 工具只需提供自己关心的属性
- 用 `satisfies ToolDef<...>` 保证类型安全

### 2.3 ToolUseContext（工具执行上下文）

```typescript
type ToolUseContext = {
  options: {
    commands: Command[]
    debug: boolean
    mainLoopModel: string
    tools: Tools
    thinkingConfig: ThinkingConfig
    mcpClients: MCPServerConnection[]
    agentDefinitions: AgentDefinitionsResult
    maxBudgetUsd?: number
    customSystemPrompt?: string
    appendSystemPrompt?: string
  }
  abortController: AbortController
  readFileState: FileStateCache
  getAppState(): AppState
  setAppState(f: (prev: AppState) => AppState): void
  messages: Message[]
  // ... 50+ 字段
}
```

---

## 3. 主循环（query.ts）

### 3.1 核心流程

```
用户输入
  ↓
构建 messages（含 system prompt、user context、system context）
  ↓
调用 API（流式）
  ↓
解析响应（text + tool_use blocks）
  ↓
┌─ 有 tool_use → 执行工具 → 注入结果 → 循环 ↑
│
└─ 无 tool_use → 返回给用户 → 等待输入
```

### 3.2 关键机制

| 机制 | 说明 |
|------|------|
| Auto Compact | token 接近窗口限制时自动压缩历史 |
| Max Output Recovery | 输出截断时自动重试（最多 3 次） |
| Token Budget | `+500k` 风格的 token 预算控制 |
| Thinking 规则 | thinking block 必须在 trajectory 中保持完整 |
| Tool Result Budget | 工具结果过大时持久化到磁盘 |
| Streaming Tool Executor | 流式解析 tool_use 并提前开始执行 |

### 3.3 QueryParams

```typescript
type QueryParams = {
  messages: Message[]
  systemPrompt: SystemPrompt
  userContext: { [k: string]: string }
  systemContext: { [k: string]: string }
  canUseTool: CanUseToolFn
  toolUseContext: ToolUseContext
  fallbackModel?: string
  maxTurns?: number
  taskBudget?: { total: number }
}
```

---

## 4. 权限系统

### 4.1 三级权限模式

```typescript
type PermissionMode = 'default' | 'plan' | 'auto' | 'bypass'
```

| 模式 | 行为 |
|------|------|
| default | 危险操作需要用户确认 |
| plan | 只读模式，不能写文件 |
| auto | 自动批准大部分操作（有分类器） |
| bypass | 跳过所有权限检查（测试用） |

### 4.2 工具级权限

```typescript
type PermissionDecision =
  | { behavior: 'allow'; updatedInput: input }
  | { behavior: 'deny'; message: string }
  | { behavior: 'ask'; message: string; suggestions?: string[] }
```

### 4.3 文件系统权限

通配符模式匹配路径：
```
always_allow: ["Read(src/**)", "Edit(src/**)"]
always_deny: ["Bash(rm -rf *)"]
```

---

## 5. 工具列表（核心 20 个）

| 工具 | 文件大小 | 用途 |
|------|----------|------|
| AgentTool | 233KB | 子代理（fork、后台、远程） |
| BashTool | 160KB | shell 命令执行 |
| FileReadTool | - | 文件读取 |
| FileEditTool | - | 文件编辑（old→new） |
| FileWriteTool | - | 文件写入 |
| GlobTool | - | 模式匹配查找文件 |
| GrepTool | - | ripgrep 内容搜索 |
| WebFetchTool | - | 网页抓取 |
| WebSearchTool | - | 网页搜索 |
| AskUserQuestionTool | - | 向用户提问 |
| TodoWriteTool | - | 任务清单 |
| EnterPlanModeTool | - | 进入计划模式 |
| ExitPlanModeTool | - | 退出计划模式 |
| SkillTool | - | 执行斜杠命令 |
| TaskOutputTool | - | 获取后台任务输出 |
| TaskStopTool | - | 停止后台任务 |
| NotebookEditTool | - | Jupyter 编辑 |
| CronCreateTool | - | 定时任务 |
| WorkflowTool | - | 工作流脚本 |
| SendMessageTool | - | 多代理通信 |

---

## 6. 系统提示构建

### 6.1 分层结构

```
System Prompt
├── 静态部分（可跨用户缓存）
│   ├── 角色定义
│   ├── 行为指令
│   ├── 工具使用说明
│   └── 安全规则
├── DYNAMIC_BOUNDARY 分界标记
└── 动态部分（用户/会话特定）
    ├── git status
    ├── CLAUDE.md 内容
    ├── 当前日期
    └── MCP 配置
```

### 6.2 关键指令片段

```
You are an interactive agent that helps users with software engineering tasks.

IMPORTANT: Assist with authorized security testing, defensive security,
CTF challenges, and educational contexts. Refuse requests for destructive
techniques, DoS attacks, mass targeting, supply chain compromise, or
detection evasion for malicious purposes.

Tools are executed in a user-selected permission mode.
When you attempt to call a tool that is not automatically allowed,
the user will be prompted so that they can approve or deny the execution.
If the user denies a tool you call, do not re-attempt the exact same tool call.
```

---

## 7. 对 python-agent 的启示

### 7.1 必须对齐的（工业级框架）

| 方面 | Claude Code 做法 | python-agent 需要 |
|------|------------------|-------------------|
| Tool 接口 | 30+ 属性，buildTool 工厂 | 完整的 Protocol + 默认值 |
| 权限检查 | checkPermissions + validateInput | 两层检查 |
| 结果序列化 | mapToolResultToToolResultBlockParam | 统一序列化 |
| 执行上下文 | ToolUseContext（50+ 字段） | 完整的上下文对象 |
| 主循环 | query.ts 68KB | 完整的循环 + 错误恢复 |
| 系统提示 | 分层构建 | 分层构建 |
| Auto Compact | token 接近限制时压缩 | 必须实现 |

### 7.2 可以简化的（工具数量）

| 方面 | Claude Code | python-agent |
|------|-------------|--------------|
| 工具数量 | 60+ | 先做 5 个核心 |
| UI 渲染 | React/Ink TSX | Rich 组件 |
| 子代理 | AgentTool 233KB | 暂不做 |
| MCP 支持 | 完整 | 暂不做 |
| 遥测分析 | 完整 | 暂不做 |

### 7.3 核心工具优先级

```
Phase 1（必须）: BashTool, FileReadTool, FileEditTool, FileWriteTool
Phase 2（重要）: GlobTool, GrepTool, WebFetchTool
Phase 3（增强）: AskUserQuestionTool, TodoWriteTool, AgentTool
```

---

## 8. 架构对比图

```
Claude Code (TypeScript)          python-agent (Python)
─────────────────────────         ─────────────────────
Tool.ts (buildTool)        →      tools/base.py (Tool Protocol)
tools.ts (getAllBaseTools)  →      tools/registry.py (ToolRegistry)
query.ts (主循环)           →      core/loop.py (AgentLoop)
ToolUseContext              →      core/context.py (ToolUseContext)
PermissionMode              →      permissions/checker.py
constants/prompts.ts        →      core/prompts.py
services/compact/           →      context/compressor.py
```

---

## 9. 关键代码片段参考

### Tool Protocol（Python 版本应该是这样）

```python
@runtime_checkable
class Tool(Protocol):
    """工具协议 - 对齐 Claude Code 的 Tool 类型"""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def parameters(self) -> dict[str, Any]: ...

    # 行为标记
    def is_enabled(self) -> bool: ...
    def is_concurrency_safe(self, input: dict) -> bool: ...
    def is_read_only(self, input: dict) -> bool: ...
    def is_destructive(self, input: dict) -> bool: ...

    # 权限检查
    def check_permissions(self, input: dict, context: ToolUseContext) -> PermissionDecision: ...
    def validate_input(self, input: dict, context: ToolUseContext) -> ValidationResult: ...

    # 执行
    def execute(self, input: dict, context: ToolUseContext) -> ToolResult: ...

    # 序列化
    def to_tool_result_block(self, output: Any, tool_use_id: str) -> dict: ...
    def get_summary(self, input: dict) -> str | None: ...
```

### ToolUseContext（Python 版本）

```python
@dataclass
class ToolUseContext:
    """工具执行上下文 - 对齐 Claude Code 的 ToolUseContext"""
    model: str
    tools: list[Tool]
    abort_controller: AbortController
    app_state: AppState
    messages: list[Message]
    debug: bool = False
    verbose: bool = False
    # ... 更多字段
```

---

## 10. 总结

**Claude Code 的核心不是工具多，而是框架完整**：

1. **Tool 接口**：30+ 属性，覆盖行为、权限、UI、序列化
2. **主循环**：auto-compact、recovery、token budget、streaming
3. **权限系统**：三级模式 + 通配符 + 分类器
4. **上下文管理**：分层提示 + 动态注入 + 缓存策略

python-agent 的目标：**框架 100% 对齐，工具数量 30%**。
