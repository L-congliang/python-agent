# P0 评测框架 + 基础能力 — 测试报告

**日期**: 2026-06-18（回溯整理）
**开发周期**: 第 1-3 天
**测试方法**: 单元测试 + 集成测试
**测试结果**: 448 passed, 3 skipped, 0 failed

---

## 测试概述

P0 是项目的基础阶段，实现了 Agent 的核心骨架：
- 模型层（MimoClient + ModelAdapter）
- CLI 框架（rich + prompt_toolkit）
- Tool Protocol + 注册系统
- Agent 主循环
- 7 个工具（bash、file_read、file_write、file_edit、grep、glob、permission_checker）
- 上下文压缩
- 评测框架

---

## 测试覆盖

| 模块 | 测试文件 | 测试数 | 状态 |
|------|----------|--------|------|
| Tool Protocol | test_tool_protocol.py | 51 | ✅ |
| 模型层 | test_model.py | 20 | ✅ |
| 主循环 | test_agent_loop.py | 23 | ✅ |
| Bash 工具 | test_bash.py | 40 | ✅ |
| 文件读取 | test_file_read.py | 36 | ✅ |
| 文件写入 | test_file_write.py | 60 | ✅ |
| 文件编辑 | test_file_edit.py | 42 | ✅ |
| Grep 搜索 | test_grep.py | 80 | ✅ |
| Glob 发现 | test_glob.py | 34 | ✅ |
| 权限检查 | test_permission_checker.py | 27 | ✅ |
| 上下文压缩 | test_compressor.py | 13 | ✅ |
| 评测框架 | test_evaluation.py | 25 | ✅ |
| **总计** | | **451** | **448 passed, 3 skipped** |

---

## 各模块测试详情

### 1. Tool Protocol（51 个测试）

**覆盖场景**:
- PermissionDecision: allow/deny/ask 决策
- ValidationResult: 成功/失败验证
- AbortController: 中断控制
- FileReadState: 文件读取状态
- build_tool 工厂: 默认值、属性覆盖、异常处理
- Tool Protocol: @runtime_checkable 检查
- ToolRegistry: 注册/获取/删除/禁用
- to_anthropic_tools: 格式转换
- validate_and_execute: 完整执行流程（成功、未找到、禁用、验证失败、权限拒绝）

**关键测试**:
```python
# 验证 fail-closed 设计
def test_validate_and_execute_permission_denied():
    # 权限拒绝时返回 is_error=True，不抛异常

# 验证 build_tool 工厂
def test_build_tool_defaults():
    # 15 个属性/方法的默认值
```

---

### 2. 模型层（20 个测试）

**覆盖场景**:
- ModelConfig: 默认值、自定义值
- load_config: 环境变量加载、缺失 API key 报错
- MimoClient: 初始化、chat 返回、system prompt、流式输出
- 重试机制: rate_limit、timeout、connection_error 重试；auth_error、api_error 不重试
- 流式输出: usage 提取、缺失处理

**关键测试**:
```python
# 验证重试策略
def test_retry_on_rate_limit():
    # 429 错误自动重试

def test_no_retry_on_auth_error():
    # 401 错误不重试，直接抛出
```

**集成测试**（3 个，跳过）:
- test_chat_returns_reply
- test_multi_turn_context
- test_stream_yields_chunks

需要真实 API key 才能运行。

---

### 3. 主循环（23 个测试）

**覆盖场景**:
- 简单文本响应: 普通回复、流式回复
- 工具调用: 单工具、多工具、执行错误、未知工具
- 循环限制: max_turns、max_tool_calls
- 中断控制: AbortController
- 历史管理: 消息历史、reset、messages 返回副本
- 配置: 默认配置、自定义配置、system prompt
- 工具结果格式: 正常结果、错误结果 is_error
- Token 追踪: 初始值、累积、重置、自动压缩

**关键测试**:
```python
# 验证循环终止条件
def test_max_turns_exceeded():
    # 超过 max_turns 强制停止

def test_max_tool_calls_exceeded():
    # 超过 max_tool_calls 强制停止

# 验证工具结果注入
def test_tool_result_injected_correctly():
    # 工具结果正确注入到消息历史
```

---

### 4. Bash 工具（40 个测试）

**覆盖场景**:
- detect_shell: shell 检测、缓存
- truncate_output: 输出截断、自定义限制
- validate_bash_input: 有效输入、空命令、无效超时、相对/绝对路径
- execute_bash: 基本命令、失败、stderr、超时、工作目录、中断、特殊字符
- BashTool: 工具属性、代理执行
- 输出截断集成: 大输出截断、小输出不截断

**关键测试**:
```python
# 验证超时保护
def test_timeout():
    # 超时后终止进程

# 验证输出截断
def test_large_output_truncated():
    # 超过 max_lines 截断，保留头部和尾部
```

---

### 5. 文件读取（36 个测试）

**覆盖场景**:
- resolve_path: 绝对路径、相对路径、点路径
- detect_encoding: UTF-8、GBK 编码检测
- format_with_line_numbers: 基本格式、自定义起始行、行号宽度自适应
- truncate_lines: 短内容、长内容截断
- execute_file_read: 基本读取、行号、offset/limit、文件不存在、是目录、中断、GBK 编码、缓存命中、缓存失效、大文件
- 读取 Notebook: 基本、带输出、offset/limit
- validate_input: 有效输入、空路径、无效 offset/limit

**关键测试**:
```python
# 验证缓存机制
def test_cache_hit():
    # 第二次读取使用缓存

def test_cache_invalidation_on_mtime_change():
    # 文件修改后缓存失效

# 验证编码检测
def test_gbk_encoding():
    # 正确读取 GBK 编码文件
```

---

### 6. 文件写入（60 个测试）

**覆盖场景**:
- resolve_path: 绝对、相对、点、点点路径
- ensure_directory: 创建嵌套目录、已存在、根路径
- check_write_permission: 可写文件、新文件、只读文件
- check_disk_space: 小内容、大内容
- update_cache: 缓存设置、mtime 匹配、覆盖
- validate_notebook_structure: 有效、缺少字段、类型错误
- execute_file_write: 基本写入、覆盖、创建目录、权限错误、磁盘空间、编码、Notebook
- validate_input: 有效、空路径、无内容无_cells

**关键测试**:
```python
# 验证目录创建
def test_creates_nested_directories():
    # 自动创建多级目录

# 验证 Notebook 写入
def test_write_notebook():
    # 正确写入 .ipynb 文件
```

---

### 7. 文件编辑（42 个测试）

**覆盖场景**:
- find_occurrence: 找到、未找到、多次出现
- apply_edit: 替换、无变化、编码
- execute_file_edit: 基本编辑、多次出现报错、文件不存在、old=new 警告、相对路径、编码、缓存更新
- 验证实际文件: 编辑后内容正确
- validate_input: 有效、空路径、空 old_string、old=new

**关键测试**:
```python
# 验证精确替换
def test_basic_edit():
    # old_string 精确匹配并替换

# 验证多次出现报错
def test_multiple_occurrences_error():
    # old_string 出现多次时报错，要求更多上下文
```

---

### 8. Grep 搜索（80 个测试）

**覆盖场景**:
- build_grep_command: 命令构建
- parse_ripgrep_output: 输出解析
- detect_ripgrep: 可用、不可用
- escape_pattern: 特殊字符转义
- resolve_search_path: 路径解析
- format_results: 结果格式化、截断
- execute_grep: 基本搜索、正则、glob 过滤、路径、context、head_limit、offset、ripgrep 不可用、中断
- 验证实际文件: 搜索真实文件
- validate_input: 有效、空模式、不存在路径

**关键测试**:
```python
# 验证正则搜索
def test_regex_pattern():
    # 支持正则表达式

# 验证 glob 过滤
def test_glob_filter():
    # 只搜索特定文件类型

# 验证结果截断
def test_head_limit():
    # 限制返回结果数量
```

---

### 9. Glob 发现（34 个测试）

**覆盖场景**:
- build_glob_command: 命令构建
- parse_glob_output: 输出解析
- format_results: 结果格式化、截断
- execute_glob: 基本发现、路径、head_limit、不存在路径、中断
- 验证实际文件: 发现真实文件
- validate_input: 有效、空模式、不存在路径

**关键测试**:
```python
# 验证模式匹配
def test_wildcard_pattern():
    # 支持通配符模式

# 验证路径递归
def test_recursive_search():
    # 递归搜索子目录
```

---

### 10. 权限检查（27 个测试）

**覆盖场景**:
- PermissionChecker: 初始化、默认权限
- check_permission: 工具不存在、allow/deny/ask
- 内置规则: bash always_ask、file_write always_ask、file_read auto_allow
- 规则优先级: deny > ask > allow
- 用户确认: approve、deny、updated_input
- 权限更新: 动态添加规则

**关键测试**:
```python
# 验证规则优先级
def test_deny_overrides_ask():
    # deny 规则优先于 ask

# 验证用户确认
def test_user_approve():
    # 用户确认后执行
```

---

### 11. 上下文压缩（13 个测试）

**覆盖场景**:
- ContextCompressor: 初始化
- compress: 基本压缩、空历史、短历史
- find_split_point: 分割点选择
- format_messages: 消息格式化、工具结果消息

**关键测试**:
```python
# 验证压缩策略
def test_compress_preserves_recent():
    # 保留最近的消息，压缩旧消息

# 验证分割点选择
def test_split_point_keeps_recent():
    # 分割点选择保证最近消息完整
```

---

### 12. 评测框架（25 个测试）

**覆盖场景**:
- BenchmarkTask: 创建、带 setup
- load_benchmark: 有效加载、缺少字段、多任务
- FakeModelClient: 确定性输出、记录 prompt、耗尽报错、单输出、prompt cache
- Evaluator: 运行任务、final_answer、tool_call、耗尽输出、步骤记录
- Metrics: 全通过、混合、按类别、空
- Regression: 改进、退化、格式化报告、保存/加载结果

**关键测试**:
```python
# 验证确定性输出
def test_deterministic_output():
    # FakeModelClient 返回预设输出

# 验证回归检测
def test_compare_regressed():
    # 检测性能退化
```

---

## 设计决策

### 1. 为什么用 Protocol 而不是 ABC？

```python
@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    ...
```

**原因**:
- Protocol 是结构化子类型，不需要显式继承
- `@runtime_checkable` 支持 `isinstance()` 检查
- 更灵活，符合 Python 鸭子类型哲学

### 2. 为什么 build_tool 用 fail-closed 默认值？

```python
def build_tool(...):
    is_read_only = False  # 默认不是只读
    is_destructive = True  # 默认是破坏性的
    ...
```

**原因**:
- 安全第一：默认最严格的权限
- 显式覆盖：工具必须明确声明自己的权限
- 避免意外：新工具默认需要确认

### 3. 为什么模型错误不自动重试？

```python
# 429, 500, timeout → 重试
# 401, 400 → 不重试
```

**原因**:
- 可恢复错误（限流、超时）→ 重试
- 不可恢复错误（认证、参数）→ 立即失败
- 避免无效重试浪费资源

---

## 面试要点

### 1. Tool Protocol 是什么？

**答**: 定义工具必须实现的接口（15 个属性/方法），使用 `@runtime_checkable` Protocol 实现结构化子类型。

**追问**: 为什么不用 ABC？
**答**: Protocol 更灵活，不需要显式继承，符合 Python 鸭子类型。而且 `@runtime_checkable` 支持运行时类型检查。

### 2. build_tool 工厂函数的作用？

**答**: 简化工具创建，提供 fail-closed 默认值。工具只需要定义自己的属性，其他用默认值。

**追问**: 什么是 fail-closed？
**答**: 默认最严格的权限。比如 `is_read_only=False`, `is_destructive=True`。新工具默认需要用户确认，避免意外操作。

### 3. Agent 主循环的终止条件？

**答**: 4 种终止条件：
1. 模型返回纯文本（无工具调用）
2. 达到 max_turns
3. 达到 max_tool_calls
4. 用户中断（AbortController）

### 4. 为什么需要 FakeModelClient？

**答**: 用于评测框架的确定性测试。不依赖真实 API，测试结果可重复。

**追问**: 和真实 API 测试的区别？
**答**: FakeModelClient 测试框架逻辑，真实 API 测试模型能力。两者互补。

---

## 总结

P0 阶段建立了项目的完整骨架，测试覆盖了所有核心模块：

| 维度 | 状态 |
|------|------|
| 测试数量 | 451 个（448 passed, 3 skipped） |
| 模块覆盖 | 12 个模块全部覆盖 |
| 测试类型 | 单元测试 + 集成测试 |
| 边界条件 | 空输入、超时、中断、权限拒绝 |
| 错误处理 | 异常捕获、错误返回、重试策略 |

**3 个 skipped 测试**是模型层集成测试，需要真实 API key 才能运行。

**关键发现**: 测试代码本身就是最好的文档。通过测试可以理解每个模块的边界和行为。
