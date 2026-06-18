# F01: 模型层 - mimo API 调通

## 需求

用 Anthropic SDK 连接 mimo v2.5pro API，实现基础的对话能力。
不需要工具调用，只需要能发消息、收回复。

## mimo API 信息

```
接口地址: https://token-plan-cn.xiaomimimo.com/anthropic
模型名称: mimo-v2.5-pro (待确认，可能是其他名称)
认证方式: x-api-key header（和 Claude API 一致）
协议格式: Anthropic Messages API 兼容
```

## 接口定义

```python
# core/model.py

import anthropic

class MimoClient:
    """mimo API 客户端"""

    def __init__(self, api_key: str, base_url: str):
        self.client = anthropic.Anthropic(
            api_key=api_key,
            base_url=base_url,
        )
        self.model = "mimo-v2.5-pro"

    def chat(self, messages: list[dict], system: str = "") -> str:
        """发送对话，返回回复文本"""
        ...

    def chat_stream(self, messages: list[dict], system: str = "") -> Iterator[str]:
        """流式对话，逐块返回文本"""
        ...
```

## 测试场景

### 1. 基础连接

```python
def test_mimo_client_connects():
    """能连接 mimo API 并收到回复"""
    client = MimoClient(api_key="...", base_url="...")
    reply = client.chat([{"role": "user", "content": "你好"}])
    assert len(reply) > 0
```

### 2. 多轮对话

```python
def test_multi_turn():
    """多轮对话能保持上下文"""
    client = MimoClient(...)
    messages = [
        {"role": "user", "content": "我叫小明"},
        {"role": "assistant", "content": "你好小明！"},
        {"role": "user", "content": "我叫什么？"},
    ]
    reply = client.chat(messages)
    assert "小明" in reply
```

### 3. 流式输出

```python
def test_stream():
    """流式输出逐块返回"""
    client = MimoClient(...)
    chunks = list(client.chat_stream([{"role": "user", "content": "说一句话"}]))
    assert len(chunks) > 1  # 不是只有一块
    full = "".join(chunks)
    assert len(full) > 0
```

### 4. 错误处理

```python
def test_invalid_key():
    """API key 无效时抛出明确错误"""
    client = MimoClient(api_key="invalid", base_url="...")
    with pytest.raises(Exception):
        client.chat([{"role": "user", "content": "test"}])
```

## 验收标准

- [ ] `MimoClient` 定义在 `core/model.py`
- [ ] 能连接 mimo API 并收到回复
- [ ] 支持多轮对话
- [ ] 支持流式输出
- [ ] 错误时抛出明确异常
- [ ] 测试用例通过（需要真实 API key）
- [ ] `make check` 通过
