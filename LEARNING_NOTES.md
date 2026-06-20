# 学习笔记 - 基础概念

记录开发过程中遇到的基础概念，方便复习。

## 目录

### F01 模型层
1. [httpx vs Anthropic SDK](#1-httpx-vs-anthropic-sdk)
2. [Streaming（流式）vs Sync（同步）](#2-streaming流式vs-sync同步)
3. [重试策略（Retry）](#3-重试策略retry)
4. [HTTP 状态码与错误处理](#4-http-状态码与错误处理)
5. [配置管理](#5-配置管理)
6. [日志记录](#6-日志记录)
7. [ModelConfig vs MimoClient 设计模式](#七modelconfig-vs-mimoclient-设计模式)
8. [SSE vs WebSocket（流式传输）](#八sse-vs-websocket流式传输)

### F03/F04 工具协议与主循环
9. [Anthropic SDK 流式 API](#anthropic-sdk-流式-apisession-6)
10. [Generator Return Value](#generator-return-value)
11. [工具调用消息格式](#工具调用消息格式anthropic-api)
12. [F03 Tool Protocol 核心概念](#f03-tool-protocol-核心概念session-6讨论)
    - [闭包（Closure）](#闭包closure)
    - [Tool vs ToolImpl vs build_tool](#tool-vs-toolimpl-vs-build_tool)
    - [Tool Protocol vs 简单函数映射](#tool-protocol-vs-简单函数映射)
    - [registry.register(tool)](#registryregistertool)
13. [F03 详细讲解：context.py](#f03-详细讲解contextpy--工具执行上下文session-6)
    - [AbortController](#abortcontroller--中断控制)
    - [FileReadState](#filereadstate--文件缓存)
    - [ToolUseContext](#toolusecontext--工具的工作环境)
14. [F03 详细讲解：types.py](#f03-详细讲解typespy--权限与校验类型session-6)
    - [PermissionDecision](#permissiondecision--权限决策)
    - [ValidationResult](#validationresult--输入校验)
    - [ToolResult](#toolresult--工具执行结果)
15. [F03 详细讲解：registry.py](#f03-详细讲解registrypy--5-步执行流程session-6)
16. [F03 组件总览](#f03-组件总览)

### F05 Bash 工具
17. [F05 Bash 工具核心概念](#f05-bash-工具核心概念)
    - [subprocess](#subprocess--python-执行外部命令)
    - [退出码](#退出码returncode)
    - [stdout vs stderr](#stdout-vs-stderr)
    - [超时](#超时timeout)
    - [工作目录](#工作目录cwd)
    - [Shell 检测](#shell-检测)
    - [输出截断](#输出截断)

### F06 文件读取工具
18. [F06 文件读取工具核心概念](#f06-文件读取工具核心概念)
    - [文件编码与 chardet](#文件编码与-chardet)
    - [mtime（修改时间）](#mtime修改时间)
    - [文件缓存策略](#文件缓存策略)
    - [行号与 offset/limit](#行号与-offsetlimit)
    - [截断方向：头部 vs 尾部](#截断方向头部-vs-尾部)
    - [Jupyter Notebook 格式](#jupyter-notebook-格式)
    - [Q&A 回顾](#qa-回顾设计时问过的问题)

---

## 1. httpx vs Anthropic SDK

### httpx - 底层 HTTP 客户端

**是什么**: 通用的 HTTP 请求库，类似 requests，但支持异步和 HTTP/2。

**工作方式**: 自己构造 HTTP 请求，手动处理一切。

```python
import httpx

response = httpx.post(
    "https://api.mimo.com/v1/messages",
    headers={"x-api-key": "xxx", "anthropic-version": "2023-06-01"},
    json={
        "model": "mimo-v2.5-pro",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "你好"}]
    }
)
data = response.json()  # 自己解析
```

**特点**:
- ✅ 完全可控，零依赖
- ✅ 可以调任何 API
- ❌ 流式解析要自己写（SSE 协议）
- ❌ 错误格式要自己处理
- ❌ 重试逻辑要自己实现

---

### Anthropic SDK - 高层 API 客户端

**是什么**: Anthropic 官方 SDK，专门用来调 Claude API。mimo 兼容这个协议。

**工作方式**: SDK 处理 HTTP 细节，只需调用方法。

```python
import anthropic

client = anthropic.Anthropic(api_key="xxx", base_url="https://mimo-url")
message = client.messages.create(
    model="mimo-v2.5-pro",
    max_tokens=1024,
    messages=[{"role": "user", "content": "你好"}]
)
# message.content[0].text 直接拿到文本
```

**特点**:
- ✅ 流式解析内置（`client.messages.stream()`）
- ✅ 错误类型明确（`AuthenticationError`, `RateLimitError` 等）
- ✅ 类型提示完善，IDE 友好
- ❌ 只能调 Anthropic 兼容的 API
- ❌ 依赖第三方库

---

### 类比理解

```
httpx = 手动挡汽车
  - 你控制离合、换挡、油门
  - 灵活但累
  - 适合老司机或特殊需求

Anthropic SDK = 自动挡汽车
  - 你只管方向盘和油门
  - 简单但不够灵活
  - 适合大多数场景
```

---

## 2. 流式 vs 同步

### 同步 (Synchronous)

```
客户端: 发送请求
服务端: 处理中...（用户等待 3 秒）
服务端: 返回完整结果
客户端: 显示结果
```

**特点**: 代码简单，用户体验差（长时间等待无反馈）

---

### 流式 (Streaming)

```
客户端: 发送请求
服务端: 返回第 1 个 token（0.1 秒）
服务端: 返回第 2 个 token（0.1 秒）
服务端: 返回第 3 个 token（0.1 秒）
...
客户端: 边收边显示（打字机效果）
```

**特点**: 代码复杂，用户体验好（实时反馈）

---

### 流式的技术实现：SSE

**SSE (Server-Sent Events)** 是流式传输的协议：

```
HTTP/1.1 200 OK
Content-Type: text/event-stream

data: {"type": "content_block_delta", "delta": {"text": "你"}}
data: {"type": "content_block_delta", "delta": {"text": "好"}}
data: {"type": "content_block_delta", "delta": {"text": "！"}}
data: [DONE]
```

每个 `data:` 是一小段 JSON，客户端边收边解析。

---

## 3. 重试策略

### 为什么需要重试？

网络不稳定、服务器临时故障、限流等情况会导致请求失败。自动重试可以提高成功率。

---

### 指数退避 (Exponential Backoff)

```
第 1 次失败 → 等 1 秒重试
第 2 次失败 → 等 2 秒重试
第 3 次失败 → 等 4 秒重试
第 4 次失败 → 报错
```

**公式**: `wait_time = base_delay * (2 ^ attempt)`

**为什么指数退避？**
- 如果 API 限流，立刻重试会加重负担
- 等久一点再试，给 API 喘息时间
- 避免"惊群效应"（大量客户端同时重试）

---

### 退避 + 随机抖动 (Jitter)

```
wait_time = base_delay * (2 ^ attempt) + random(0, 1)
```

**为什么加随机？**
- 如果所有客户端都等 exactly 2 秒，会在 2 秒后同时重试
- 加随机让重试时间分散开

---

## 4. HTTP 错误码

### 常见错误码

| 错误码 | 含义 | 要不要重试 | 原因 |
|-------|------|-----------|------|
| 200 | 成功 | - | - |
| 400 | 请求格式错误 | ❌ | 代码写错了，重试没用 |
| 401 | 认证失败 | ❌ | API key 错了，重试没用 |
| 403 | 权限不足 | ❌ | 没权限，重试没用 |
| 404 | 资源不存在 | ❌ | URL 错了，重试没用 |
| 429 | 限流 | ✅ | 请求太快，等一会就好 |
| 500 | 服务器内部错误 | ✅ | 服务端临时问题 |
| 502 | 网关错误 | ✅ | 中间层问题 |
| 503 | 服务不可用 | ✅ | 服务端过载 |

---

### 错误处理策略

```python
try:
    response = call_api()
except AuthenticationError:  # 401
    raise  # 直接报错，不重试
except RateLimitError:  # 429
    wait_and_retry()
except APITimeoutError:
    retry()
except APIConnectionError:
    retry()
except APIError as e:
    raise  # 其他错误，直接报错
```

---

## 5. 配置管理

### 为什么不用硬编码？

```python
# ❌ 硬编码
api_key = "sk-abc123"  # 泄露风险！换环境要改代码

# ✅ 环境变量
api_key = os.environ["MIMO_API_KEY"]  # 安全，灵活
```

---

### 环境变量

```bash
# Linux/Mac
export MIMO_API_KEY="sk-abc123"

# Windows PowerShell
$env:MIMO_API_KEY="sk-abc123"

# Windows CMD
set MIMO_API_KEY=sk-abc123
```

---

### 配置优先级

```
环境变量 > 配置文件 > 默认值
```

```python
def load_config() -> ModelConfig:
    return ModelConfig(
        api_key=os.environ.get("MIMO_API_KEY"),  # 必须
        base_url=os.environ.get("MIMO_BASE_URL", "https://default.com"),  # 可选
        model=os.environ.get("MIMO_MODEL", "mimo-v2.5-pro"),  # 可选
    )
```

---

## 6. 日志记录

### 为什么要记日志？

- 调试问题：出了错能知道发生了什么
- 性能监控：知道每次调用花了多久
- 审计追踪：谁在什么时候调了什么

---

### Python logging 模块

```python
import logging

# 创建 logger
logger = logging.getLogger("agent.model")

# 设置级别
logger.setLevel(logging.INFO)

# 记录日志
logger.info("API call: %d messages", len(messages))
logger.warning("API retry: attempt %d/%d", attempt, max_retries)
logger.error("API error: %s", str(e))
```

---

### 日志级别

| 级别 | 用途 | 例子 |
|-----|------|------|
| DEBUG | 调试信息 | 请求参数、响应原文 |
| INFO | 正常操作 | API 调用成功、token 数 |
| WARNING | 警告 | 重试、限流 |
| ERROR | 错误 | API 调用失败 |
| CRITICAL | 严重错误 | 系统崩溃 |

---

## 七、ModelConfig vs MimoClient 设计模式

**问题**：为什么要分成两个类？

### ModelConfig — 配置容器

```python
@dataclass
class ModelConfig:
    api_key: str
    base_url: str = "https://..."
    model: str = "mimo-v2.5-pro"
    max_tokens: int = 4096
```

**职责**：只存数据 + 验证数据，不干业务逻辑。

**类比**：餐厅的"菜单"，记录食材、调料、份量。

### MimoClient — 业务执行者

```python
class MimoClient:
    def __init__(self, config: ModelConfig):
        self.config = config

    def chat(self, messages, system) -> str:
        ...
```

**职责**：接收配置，执行业务。

**类比**：餐厅的"厨师"，按菜单做菜。

### 分离的好处

- **配置复用**：一份配置可以创建多个客户端
- **单一职责**：改配置验证不影响业务代码，改业务逻辑不影响配置
- **测试方便**：测试配置验证不需要真的连 API

---

## 八、SSE vs WebSocket（流式传输）

### 三种传输方式对比

| | HTTP 普通请求 | SSE | WebSocket |
|---|---|---|---|
| **方向** | 单次请求/响应 | 服务器单向推送 | 双向通信 |
| **协议** | HTTP | HTTP | 独立协议(ws://) |
| **连接** | 请求完就断 | 保持长连接 | 保持长连接 |
| **场景** | 普通 API | AI 流式输出 | 聊天室、游戏 |

### SSE（Server-Sent Events）

```
客户端 ──── 请求 ────→ 服务器
客户端 ←── chunk1 ──── 服务器
客户端 ←── chunk2 ──── 服务器
客户端 ←── [DONE] ──── 服务器
```

**特点**：基于 HTTP，服务器单向推送，客户端只能接收。

### 为什么 AI 用 SSE？

- AI 场景：客户端发一次请求，服务器持续输出
- SSE 简单、基于 HTTP、单向推送刚好满足
- WebSocket 太重（双向通信不需要）

### 实际代码

```python
# SDK 内部发送 HTTP POST，带 stream=true
# 服务器返回 SSE 流（text/event-stream）
# SDK 解析 chunk，通过 text_stream 逐个吐出
with self.client.messages.stream(**params) as stream:
    for text in stream.text_stream:
        yield text  # 每次 yield 几个字，形成打字机效果
```

---

## 待补充

- [ ] async/await 异步编程
- [ ] type hints 类型注解
- [ ] dataclass 用法
- [ ] pytest 测试框架

---

## Anthropic SDK 流式 API（Session 6）

**问题**: `stream.text_stream` 只返回文本 chunk，`tool_use` block 不在其中

**解决**: 流结束后调用 `stream.get_final_message().content` 获取完整 content blocks

```python
# 只有文本
for text in stream.text_stream:
    print(text)

# 完整 blocks（含 tool_use）
final = stream.get_final_message()
for block in final.content:
    if block.type == "tool_use":
        print(block.name, block.input)
```

**StreamResult 模式**: 同时返回 text 迭代器 + content_blocks

```python
@dataclass
class StreamResult:
    text: Iterator[str]           # 流式显示用
    content_blocks: list[dict]    # 流结束后可用
```

## Generator Return Value

Python generator 可以通过 `return` 返回值，调用方通过 `StopIteration.value` 获取

```python
def gen():
    yield 1
    yield 2
    return "done"  # 不是 StopIteration

g = gen()
next(g)  # 1
next(g)  # 2
# next(g)  # StopIteration, value="done"
```

## 工具调用消息格式（Anthropic API）

```json
// assistant 消息（含 tool_use）
{"role": "assistant", "content": [
    {"type": "text", "text": "我来读取文件"},
    {"type": "tool_use", "id": "t1", "name": "read", "input": {"path": "test.txt"}}
]}

// tool_result 消息
{"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "t1", "content": "文件内容"}
]}
```

---

## F03 Tool Protocol 核心概念（Session 6 讨论）

### 闭包（Closure）

函数记住了它被创建时的环境。

```python
def make_greeting(name):
    def greet():
        return f"你好，{name}"  # greet 记住了 name
    return greet

say_hello = make_greeting("小明")
print(say_hello())  # "你好，小明" — name 本该消失，但被记住了
```

在 ToolImpl 里，闭包用来存储可选行为覆盖（如 `is_read_only=lambda input: True`）。

### Tool vs ToolImpl vs build_tool

- **Tool** (Protocol) — 接口定义，不能实例化
- **ToolImpl** (dataclass) — 具体实现，Tool 的实例
- **build_tool()** — 工厂函数，帮你创建 ToolImpl

工具开发者只用 `build_tool()`，不需要直接碰 ToolImpl。

### Tool Protocol vs 简单函数映射

```python
# 简单方式（demo 级别）
TOOLS = [{"name": "bash", ...}]        # 给 API
HANDLERS = {"bash": run_bash}           # 给自己用
output = HANDLERS["bash"](command="ls") # 直接调用

# Protocol 方式（框架级别）
tool = build_tool(name="bash", ..., execute_fn=run_bash)
registry.register(tool)
result = registry.validate_and_execute("bash", args, ctx)  # 5 步流程
```

区别：简单方式没有权限控制、输入校验、行为标记。工具少时够用，工具多时 Protocol 更可扩展。

### registry.register(tool)

就是把工具存进字典 `self._tools[tool.name] = tool`，带类型检查和重复检查。

对比 demo 的两个平行结构（TOOLS + HANDLERS），registry 把信息和行为绑在一个对象里，注册一次全搞定。

---

## F03 详细讲解：context.py — 工具执行上下文（Session 6）

### AbortController — 中断控制

就是一个布尔开关。用户按 Ctrl+C 时调用 `abort()`，工具执行前检查 `is_aborted`。

为什么不用 `raise KeyboardInterrupt`？因为中断需要跨函数传递——用户在主循环里按 Ctrl+C，但需要中断的是正在执行的工具。AbortController 是一个共享对象，谁都能检查它。

### FileReadState — 文件缓存

就是一个字典的封装。同一次对话中，可能多次读同一个文件，缓存避免重复磁盘 I/O。

### ToolUseContext — 工具的"工作环境"

工具执行时需要知道很多外部信息（工作目录、是否中断、文件缓存等）。如果一个个传参，函数签名会很长。打包成一个对象，传一个就够了。

为什么不直接传全局状态？因为 ToolUseContext 是工具看到的"视图"——只暴露工具需要的部分，不暴露全部应用状态。这是最小权限原则。

---

## F03 详细讲解：types.py — 权限与校验类型（Session 6）

### PermissionDecision — 权限决策

三种结果：allow（允许）、deny（拒绝）、ask（询问用户）。

```python
PermissionDecision.allow()                    # 允许执行
PermissionDecision.allow(updated_input={...}) # 允许，但修改参数
PermissionDecision.deny("权限不足")            # 拒绝，附原因
PermissionDecision.ask("要执行 rm 吗？")       # 询问用户
```

`updated_input` 的作用：权限检查时可以修改参数。比如工具要求绝对路径，你可以把相对路径改成绝对路径再放行。

### ValidationResult — 输入校验

校验失败不是异常，是正常流程。用返回值而不是异常，调用方处理更统一。

```python
ValidationResult.success()                    # 校验通过
ValidationResult.failure("路径不能为空")       # 校验失败
```

### ToolResult — 工具执行结果

```python
ToolResult(output="文件内容")                  # 成功
ToolResult(output="文件不存在", is_error=True)  # 失败
ToolResult(output="ok", new_messages=[...])    # 成功，附带新消息
```

`new_messages`：有些工具执行后需要往对话历史里注入额外消息。大多数工具用不到。

---

## F03 详细讲解：registry.py — 5 步执行流程（Session 6）

`validate_and_execute` 是 registry 的核心方法：

```
查找工具 → 检查启用 → 校验输入 → 检查权限 → 执行
   ↓ 失败      ↓ 失败      ↓ 失败      ↓ 失败      ↓ 失败
   返回错误    返回错误    返回错误    返回错误    返回错误
```

关键设计：不抛异常。每一步失败都返回 `ToolResult(is_error=True)`。

为什么？因为主循环需要把错误信息返回给模型，让模型知道出了什么问题并决定下一步。如果抛异常，主循环得自己猜发生了什么。

---

## F03 组件总览

```
types.py          定义数据结构
  ├─ PermissionDecision  权限决策（allow/deny/ask）
  ├─ ValidationResult    校验结果（success/failure）
  ├─ ToolResult          工具执行结果（output + is_error）
  └─ ToolCall            API 返回的工具调用请求

context.py        定义执行环境
  ├─ AbortController     中断开关
  ├─ FileReadState       文件缓存
  └─ ToolUseContext       工具能访问的全部上下文

tools/base.py     定义工具接口
  ├─ Tool (Protocol)     15 个属性/方法的接口
  ├─ ToolImpl            具体实现（dataclass）
  └─ build_tool()        工厂函数

tools/registry.py 管理工具
  ├─ register()          注册工具
  ├─ to_anthropic_tools() 转成 API 格式
  └─ validate_and_execute() 5 步执行流程
```

---

## F05 Bash 工具核心概念

### subprocess — Python 执行外部命令

Python 标准库模块，用于执行系统命令（如 `ls`、`git status`）。

```python
import subprocess
result = subprocess.run(["ls", "-la"], capture_output=True, text=True, timeout=30)
# result.stdout   → 正常输出
# result.stderr   → 错误信息
# result.returncode → 退出码（0=成功）
```

### 退出码（returncode）

所有命令执行后返回一个数字：`0` = 成功，`非0` = 失败。AI 模型根据退出码判断命令是否成功。

### stdout vs stderr

两种输出流：stdout 是正常结果，stderr 是错误信息。分开捕获方便排查问题。

### 超时（timeout）

防止命令卡死。`subprocess.run(..., timeout=30)` 超过 30 秒自动终止，抛出 `TimeoutExpired` 异常。

### 工作目录（cwd）

命令在哪个目录执行。`subprocess.run(..., cwd="/tmp")` 在 `/tmp` 目录执行命令。

### Shell 检测

Windows 上默认 shell 是 cmd.exe，不认识 Linux 命令（ls, cat, grep）。优先检测 Git Bash，fallback 到 cmd。

```
检测优先级: Git Bash → cmd.exe (Windows) → /bin/sh (Linux/Mac)
```

### 输出截断

命令输出可能很长（cat 大文件），截断保留尾部 2000 行，避免撑爆模型上下文。

---

## F06 文件读取工具核心概念

### 文件编码与 chardet

**问题**：文件存储的是字节（bytes），显示成文字需要"解码"。不同文件用不同编码。

```python
# 文件实际存储的是字节
b'\xe4\xbd\xa0\xe5\xa5\xbd'  # 这是什么？

# 用 UTF-8 解码 → "你好"
# 用 GBK 解码   → "浣犲"（乱码）
```

**常见编码**：

| 编码 | 用途 | 特点 |
|------|------|------|
| UTF-8 | 现代标准，90%+ 文件 | 可变长度，支持所有语言 |
| GBK | Windows 中文老项目 | 固定 2 字节，只支持中英文 |
| Latin-1 | 万能 fallback | 永远不报错，但可能乱码 |

**chardet 库**：自动检测文件编码。

```python
import chardet

raw = b'\xc4\xe3\xba\xc3'  # GBK 编码的"你好"
result = chardet.detect(raw)
# {'encoding': 'GB2312', 'confidence': 0.99}
```

**为什么需要 chardet？** 因为 `open(file)` 默认用 UTF-8，遇到 GBK 文件会报 `UnicodeDecodeError`。chardet 先检测编码，再用正确的编码打开。

**我们的策略**：UTF-8 优先 → chardet 检测 → latin-1 兜底。三层层层递进，确保不报错。

### mtime（修改时间）

文件系统记录的"最后修改时间"，是一个 Unix 时间戳（秒）。

```python
import os
mtime = os.path.getmtime("main.py")
# 1718956800.0（2024-06-21 10:00:00 的 Unix 时间戳）
```

**用途**：判断文件是否被修改过。如果 mtime 没变，文件内容一定没变（假设没有人在同一秒内改了又改回来）。

**为什么不用文件内容 hash？** 因为读取整个文件算 hash 太慢。`os.path.getmtime()` 只需要读文件元数据，耗时 0.001ms。

### 文件缓存策略

**问题**：一次对话中，Agent 可能多次读同一个文件。每次都读磁盘浪费 I/O。

**解决方案**：缓存文件内容 + mtime。

```
第 1 次读 main.py:
  → 缓存没有 → 读磁盘 → 存缓存 (内容, mtime=1000)

第 2 次读 main.py:
  → 缓存有 → 比较 mtime: 缓存 1000 vs 磁盘 1000
  → 相同 → 直接返回缓存（跳过磁盘读取）

用户用 Bash 修改了 main.py → mtime 变成 1001

第 3 次读 main.py:
  → 缓存有 → 比较 mtime: 缓存 1000 vs 磁盘 1001
  → 不同 → 重新读磁盘 → 更新缓存
```

**关键**：缓存存的是 `(内容, mtime)` 元组，不只是内容。没有 mtime 就无法检测过期。

### 行号与 offset/limit

**为什么输出要带行号？**

```
# 没有行号
def calculate(x, y):
    return x + y
```
模型只能说"在 `def calculate` 下面那一行"——不精确。

```
# 有行号
  7 │ def calculate(x, y):
  8 │     return x + y
```
模型可以直接说"第 8 行"——精确无歧义。

**offset/limit 的好处**：

大文件（500 行）不需要全部读取。模型可以：
1. 先读前 50 行（`offset=1, limit=50`）→ 了解文件结构
2. 再读第 100-150 行（`offset=100, limit=50`）→ 看感兴趣的函数
3. 总共只读 100 行，而不是 500 行

**行号对应原始文件行号**：`offset=100` 时，输出第一行显示 `100 │`，不是 `1 │`。

### 截断方向：头部 vs 尾部

不同工具保留不同方向：

| 工具 | 保留方向 | 原因 |
|------|---------|------|
| Bash | 尾部 | 命令输出有用信息在最后（测试结果、错误信息） |
| Read | 头部 | 文件结构在开头（imports、类定义、函数签名） |

```
Bash 截断（保留尾部）：
  ... (truncated 1000 lines)
  line 2001  ← 最后的输出
  line 2002
  ...
  line 3000  ← 有用信息在这里

Read 截断（保留头部）：
  ... (truncated, showing first 2000 of 5000 lines)
  line 1     ← imports 在这里
  line 2
  ...
  line 2000  ← 类定义、函数签名在头部
```

### Jupyter Notebook 格式

Notebook（.ipynb）本质是一个 JSON 文件：

```json
{
    "cells": [
        {
            "cell_type": "markdown",
            "source": ["# 标题\n", "描述"]
        },
        {
            "cell_type": "code",
            "source": ["print('hello')"],
            "outputs": [{"text": ["hello\n"], "output_type": "stream"}]
        }
    ]
}
```

**Read 工具的格式化输出**：

```
--- Cell 1 (markdown) ---
# 标题
描述

--- Cell 2 (code) ---
print('hello')

--- Cell 2 Output ---
hello
```

分隔线清晰区分不同 cell，比纯 JSON 更易读。offset/limit 按格式化后的行计算，与文本文件行为一致。

### Q&A 回顾：设计时问过的问题

**Q1: offset/limit 是什么意思？**

就是"从第几行开始读，读几行"。类比翻书：offset 是"翻到第几页"，limit 是"读几页"。

```
Read(file_path="main.py")              → 读整个文件（截断到 2000 行）
Read(file_path="main.py", offset=100, limit=50)  → 只读第 100-149 行
```

**Q2: 了解了前 50 行后，还是要全部读取吗？**

不是。模型像人一样"先看目录，再翻到具体页"：

```
第 1 步: Read(file_path="main.py", offset=1, limit=50)
         → 看到文件结构，发现 calculate 函数在第 100 行附近

第 2 步: Read(file_path="main.py", offset=95, limit=55)
         → 精确拿到 calculate 函数的实现

总共只读了 105 行，而不是全部 500 行
```

好处是**节省 token**。模型上下文窗口有限，塞太多内容会溢出。

**Q3: chardet 是什么？**

一个 Python 库，自动检测文件是什么编码。

```python
import chardet

# 读取一个文件的前几 KB 字节
with open("old_file.txt", "rb") as f:
    raw = f.read(8192)

# chardet 分析字节模式，猜测编码
result = chardet.detect(raw)
# {'encoding': 'GB2312', 'confidence': 0.99, 'language': 'Chinese'}

# 用检测到的编码解码
text = raw.decode(result['encoding'])
```

**为什么需要？** 中文项目经常遇到 GBK 编码（Windows 默认），直接 `open(file)` 用 UTF-8 会报错。chardet 先检测再解码，不会出错。

**Q4: mtime 检查是怎么做的？**

每次读文件前，先获取文件的"最后修改时间"，和缓存里的时间比较：

```python
import os

# 获取文件修改时间（Unix 时间戳，秒）
current_mtime = os.path.getmtime("main.py")
# 1718956800.0

# 和缓存比较
if cached_mtime == current_mtime:
    # 文件没变，用缓存（跳过磁盘读取）
    return cached_content
else:
    # 文件被修改了，重新读取
    content = read_file("main.py")
    update_cache(content, current_mtime)
```

`os.path.getmtime()` 只读文件元数据，耗时约 0.001ms，几乎无开销。

**Q5: 图片支持为什么去掉了？**

因为 mimo v2.5 pro 大概率不支持多模态（图片理解）。即使 Read 工具返回 base64 图片，模型也看不懂。所以跳过图片，只做文本 + Notebook。
