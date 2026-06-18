# F01: 模型层 - mimo API 客户端

## 需求

封装 mimo v2.5pro API，提供可靠的对话能力。
不只是"调通 API"，而是做一个**生产级的 API 客户端**，包含重试、超时、错误处理、日志。

## 设计决策

### 为什么用 Anthropic SDK 而不是直接 httpx？

```
方案 A: 直接用 httpx 发 HTTP 请求
  优点: 零依赖，完全可控
  缺点: 要自己处理流式解析、错误格式、重试逻辑

方案 B: 用 Anthropic SDK，改 base_url（选择这个）
  优点: 流式解析、错误处理已经做好，mimo 接口兼容
  缺点: 依赖第三方 SDK，如果 mimo 改接口可能不兼容

选择理由: mimo 的 /anthropic 路径说明它刻意兼容 Anthropic 协议，
          用 SDK 可以专注于业务逻辑而不是 HTTP 细节。
          如果未来 mimo 改接口，再换成 httpx 也不难。
```

### 为什么不直接暴露 Anthropic SDK？

```
直接暴露 SDK 的问题:
  - 调用方需要了解 SDK 的内部结构（Message 对象、ContentBlock 等）
  - 换模型时要改所有调用方
  - 无法统一做重试、日志、错误处理

封装的好处:
  - 调用方只关心 messages 和返回的 str
  - 重试、超时、日志在封装层统一处理
  - 未来换 SDK 只改这一层
```

## mimo API 信息

```
接口地址: https://token-plan-cn.xiaomimimo.com/anthropic
模型名称: mimo-v2.5-pro (待确认，可能需要实际调用测试)
认证方式: x-api-key header
协议格式: Anthropic Messages API 兼容
```

## 接口定义

```python
# core/model.py

from dataclasses import dataclass
from collections.abc import Iterator
import anthropic


@dataclass
class ModelConfig:
    """模型配置"""
    api_key: str
    base_url: str
    model: str = "mimo-v2.5-pro"
    max_tokens: int = 4096
    timeout: float = 60.0          # 单次请求超时（秒）
    max_retries: int = 3           # 最大重试次数
    retry_delay: float = 1.0       # 重试间隔（秒）


class MimoClient:
    """mimo API 客户端

    职责:
    - 管理 API 连接
    - 提供同步/流式两种对话方式
    - 统一处理重试、超时、错误
    - 记录调用日志
    """

    def __init__(self, config: ModelConfig):
        ...

    def chat(self, messages: list[dict], system: str = "") -> str:
        """同步对话，返回完整回复文本

        Args:
            messages: 对话历史，格式 [{"role": "user", "content": "..."}]
            system: 系统提示词

        Returns:
            模型回复的文本内容

        Raises:
            AuthenticationError: API key 无效
            RateLimitError: 请求过于频繁
            APIError: 其他 API 错误
        """
        ...

    def chat_stream(self, messages: list[dict], system: str = "") -> Iterator[str]:
        """流式对话，逐块返回文本

        Args:
            messages: 对话历史
            system: 系统提示词

        Yields:
            每个文本块（chunk）

        Raises:
            同 chat()
        """
        ...
```

## 错误处理策略

```
错误类型              处理方式                    用户看到什么
─────────────────────────────────────────────────────────────
AuthenticationError   不重试，直接报错             "API key 无效"
RateLimitError        重试，指数退避               "请求过于频繁，重试中..."
APITimeoutError       重试（最多 3 次）            "请求超时，重试中..."
APIConnectionError    重试（最多 3 次）            "网络连接失败，重试中..."
APIError              不重试，直接报错             "API 错误: {message}"
```

重试逻辑：

```python
def _retry(self, fn, max_retries=3):
    """指数退避重试"""
    for attempt in range(max_retries):
        try:
            return fn()
        except (RateLimitError, APITimeoutError, APIConnectionError) as e:
            if attempt == max_retries - 1:
                raise
            wait = self.config.retry_delay * (2 ** attempt)
            time.sleep(wait)
```

## 日志记录

```python
import logging

logger = logging.getLogger("agent.model")

# 记录每次 API 调用:
logger.info("API call: %d messages, system=%d chars", len(messages), len(system))
logger.info("API response: %d tokens, %.2fs", token_count, elapsed)
logger.warning("API retry: attempt %d/%d, error: %s", attempt, max_retries, e)
```

## 配置管理

API key 不硬编码，通过环境变量或配置文件：

```python
import os

def load_config() -> ModelConfig:
    """从环境变量加载配置"""
    api_key = os.environ.get("MIMO_API_KEY")
    if not api_key:
        raise ValueError("MIMO_API_KEY 环境变量未设置")

    return ModelConfig(
        api_key=api_key,
        base_url=os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/anthropic"),
        model=os.environ.get("MIMO_MODEL", "mimo-v2.5-pro"),
    )
```

## 测试场景

### 1. 基础连接

```python
def test_chat_returns_reply():
    """能连接 API 并收到非空回复"""
    client = MimoClient(load_config())
    reply = client.chat([{"role": "user", "content": "说'你好'"}])
    assert len(reply) > 0
    assert isinstance(reply, str)
```

### 2. 多轮对话

```python
def test_multi_turn_context():
    """多轮对话能保持上下文"""
    client = MimoClient(load_config())
    messages = [
        {"role": "user", "content": "记住这个数字: 42"},
        {"role": "assistant", "content": "好的，我记住了数字 42。"},
        {"role": "user", "content": "我让你记住的数字是多少？"},
    ]
    reply = client.chat(messages)
    assert "42" in reply
```

### 3. 流式输出

```python
def test_stream_yields_chunks():
    """流式输出逐块返回，拼接后是完整回复"""
    client = MimoClient(load_config())
    chunks = list(client.chat_stream([{"role": "user", "content": "说一句话"}]))
    assert len(chunks) > 0
    full = "".join(chunks)
    assert len(full) > 0
```

### 4. 认证失败

```python
def test_invalid_key_raises_auth_error():
    """API key 无效时抛出 AuthenticationError"""
    config = ModelConfig(api_key="invalid", base_url="...")
    client = MimoClient(config)
    with pytest.raises(AuthenticationError):
        client.chat([{"role": "user", "content": "test"}])
```

### 5. 重试机制

```python
def test_retry_on_timeout():
    """超时时自动重试"""
    # mock 一个超时的 API，验证重试逻辑
    ...
```

### 6. 配置加载

```python
def test_load_config_from_env():
    """从环境变量正确加载配置"""
    os.environ["MIMO_API_KEY"] = "test-key"
    config = load_config()
    assert config.api_key == "test-key"
    assert "mimo" in config.base_url
```

## 文件结构

```
src/agent/core/
├── __init__.py
├── types.py        # 已有
└── model.py        ← MimoClient + ModelConfig + load_config
```

## 验收标准

- [ ] `MimoClient` 和 `ModelConfig` 定义在 `core/model.py`
- [ ] 同步对话 `chat()` 能正常工作
- [ ] 流式对话 `chat_stream()` 能正常工作
- [ ] 重试机制：超时和限流自动重试，指数退避
- [ ] 错误分类：认证错误、限流、超时、连接错误分别处理
- [ ] 配置管理：从环境变量读取，不硬编码
- [ ] 日志记录：记录每次调用的 token 数和耗时
- [ ] 测试覆盖正常路径和错误路径
- [ ] `make check` 通过

## 面试可能问的问题

```
Q: 为什么封装 SDK 而不是直接用？
A: 统一重试/日志/错误处理，调用方不关心 SDK 细节。

Q: 重试策略怎么选的？
A: 指数退避，避免在限流时加重负担。3 次是经验值。

Q: 流式和同步怎么选？
A: CLI 用流式（体验好），测试用同步（简单）。

Q: mimo 和 Claude 的 API 差异怎么处理？
A: 目前兼容，如果不兼容了就在这一层做转换。
```
