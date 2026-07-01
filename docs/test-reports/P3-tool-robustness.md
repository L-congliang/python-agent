# P3 工具鲁棒性测试报告

## 实现概览

Phase 3 实现了工具鲁棒性，包括：

1. **错误恢复策略** - 模型错误时设置任务状态为 FAILED，保留错误上下文
2. **重复调用拦截** - 检测同一工具同一参数的连续调用（默认 3 次）
3. **路径逃逸防护** - 文件路径必须在工作区内
4. **工具调用超时** - Bash 工具已有 30 秒超时保护
5. **重试上限** - 连续 5 次无效调用强制停止
6. **TaskState 状态机** - 追踪任务状态流转

## 模块结构

```
src/agent/robustness/
├── __init__.py          # 模块导出
├── task_state.py        # TaskState 状态机
├── repeat_detector.py   # 重复调用检测
├── path_guard.py        # 路径逃逸防护
└── retry_limiter.py     # 重试上限
```

## 测试结果

### 单元测试（24 个）

| 测试类 | 数量 | 状态 |
|--------|------|------|
| TestTaskState | 8 | ✅ PASSED |
| TestRepeatDetector | 5 | ✅ PASSED |
| TestPathGuard | 6 | ✅ PASSED |
| TestRetryLimiter | 5 | ✅ PASSED |

### Security Experiment（4 个场景）

| 场景 | 描述 | 安全事件 | 工具调用 |
|------|------|----------|----------|
| path_escape | 路径逃逸防护 | ✅ path_escape=1 | 0 |
| repeated_call | 重复调用拦截 | ✅ repeated_call=1 | 2 |
| normal_read | 正常文件读取 | 无 | 1 |
| normal_bash | 正常命令执行 | 无 | 1 |

### 全量测试

```
574 passed, 3 skipped
```

## 设计决策

### 1. 为什么重复检测用 hash？

参数可能很大（如文件内容），hash 更高效：
```python
args_str = json.dumps(arguments, sort_keys=True)
args_hash = hashlib.md5(f"{tool_name}:{args_str}".encode()).hexdigest()
```

### 2. 为什么路径防护用 resolve()？

解析符号链接和 `..`，获取真实路径：
```python
resolved = target.resolve()
resolved.relative_to(self._root)
```

### 3. 为什么模型错误不自动恢复？

模型错误（如 API 超时）通常是不可恢复的，应该：
- 设置任务状态为 FAILED
- 记录错误信息到 metadata
- 让调用者决定如何处理

### 4. 为什么重试上限区分"无效调用"和"错误调用"？

- **无效调用**：模型输出格式错误（JSON 解析失败）→ 计入重试上限
- **错误调用**：工具执行失败（文件不存在）→ 不计入重试上限

因为错误调用是正常的（文件确实不存在），不应该强制停止。

## 集成点

### AgentLoop 集成

```python
class AgentLoop:
    def __init__(self, ...):
        # 鲁棒性组件
        self._task_state = TaskState()
        self._repeat_detector = RepeatDetector(max_repeats=3)
        self._path_guard = PathGuard(workspace_root=...)
        self._retry_limiter = RetryLimiter(max_retries=5)

    def _execute_tool_calls(self, tool_calls):
        for tool_call in tool_calls:
            # 1. 重复调用检测
            is_repeated, msg = self._repeat_detector.check(...)
            if is_repeated:
                return error

            # 2. 路径逃逸防护
            if tool_call.name in ("read", "write", "edit"):
                is_safe, msg = self._path_guard.check_path(...)
                if not is_safe:
                    return error

            # 3. 执行工具
            result = self._registry.validate_and_execute(...)

            # 4. 重试上限检查
            if result.is_error:
                self._retry_limiter.record_failure()
            else:
                self._retry_limiter.record_success()
```

## 面试要点

### 1. 工具鲁棒性是什么？

防止模型陷入死循环、执行危险操作、或浪费资源的保护机制。

### 2. 为什么需要重复调用检测？

模型可能因为：
- 不理解之前的输出
- 幻觉（以为没读过文件）
- 格式错误导致解析失败

而反复调用同一个工具，浪费 token 和时间。

### 3. 路径逃逸防护的实现原理？

```python
# 解析路径
target = Path(file_path)
resolved = target.resolve()

# 检查是否在工作区内
try:
    resolved.relative_to(self._root)
    return True
except ValueError:
    return False  # 路径逃逸
```

### 4. TaskState 状态机的作用？

追踪任务的完整生命周期，用于：
- 调试：知道任务在哪一步失败
- 监控：统计任务成功率
- 恢复：从 checkpoint 恢复任务
