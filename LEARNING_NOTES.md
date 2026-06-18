# 学习笔记 - 基础概念

记录开发过程中遇到的基础概念，方便复习。

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

## 待补充

- [ ] async/await 异步编程
- [ ] type hints 类型注解
- [ ] dataclass 用法
- [ ] pytest 测试框架
