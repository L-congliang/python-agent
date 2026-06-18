# Python Agent 学习进度

## 已完成

### 概念课程（11节）
1. ✅ Tool 接口（Protocol 模式）
2. ✅ 单次工具调用（LLM 如何触发工具）
3. ✅ 结果回传（ToolResult）
4. ✅ 简单循环（while True 主循环）
5. ✅ 错误类型（参数错误、执行错误、超时）
6. ✅ 错误传递（is_error 标记）
7. ✅ 重试机制（LLM 自我修正）
8. ✅ Token 与上下文（为什么需要管理）
9. ✅ 三种压缩策略（截断、摘要、裁剪）
10. ✅ 并发执行（read-only 并发，write 串行）
11. ✅ 权限系统（ALLOW/DENY/ASK）

### 项目初始化
- ✅ GitHub 仓库创建：https://github.com/L-congliang/python-agent
- ✅ 目录结构搭建
- ✅ `types.py` 类型定义

## 待实现

- [ ] `tools/base.py` - Tool 接口（Protocol）
- [ ] `core/loop.py` - Agent 主循环
- [ ] `tools/bash.py` - Bash 工具
- [ ] `tools/file_read.py` - 文件读取
- [ ] `tools/file_write.py` - 文件写入
- [ ] `tools/grep.py` - 搜索工具
- [ ] `permissions/checker.py` - 权限检查
- [ ] `context/compressor.py` - 上下文压缩

## 核心架构理解

```
用户输入
    ↓
[Agent 主循环] ←──────────────────┐
    ↓                              │
调用 LLM API                       │
    ↓                              │
解析响应                           │
    ├─ 文本 → 返回给用户           │
    └─ ToolCall → 执行工具         │
                    ↓              │
                收集结果           │
                    ↓              │
                继续循环 ──────────┘
```

## TypeScript → Python 对照表

| TypeScript | Python |
|------------|--------|
| `interface` | `Protocol` |
| `type X = {...}` | `@dataclass` |
| `async function*` | `async def` + `yield` |
| `Promise.all` | `asyncio.gather` |
| `for await...of` | `async for` |
