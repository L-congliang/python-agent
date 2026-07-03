# P5 多 Agent 系统 — 完整测试报告

**日期**: 2026-07-02
**开发周期**: 第 12-14 天
**测试方法**: 单元测试 + Bug 修复验证 + 真实模型验证（待补充）
**测试结果**: 78 passed, 0 failed

---

## 测试概述

P5 实现了多 Agent 系统，包括：
- SubAgentTool: 子 Agent 工具，主 Agent 通过调用此工具派生子任务
- 子 Agent 上下文隔离: 独立上下文，只接收 task 描述，执行完销毁
- AgentType 定义: 预定义 Agent 类型（general_purpose、explore、code_reviewer）
- TaskManager: 任务管理器，追踪子 Agent 状态和结果
- Worktree 隔离: Git worktree 实现文件系统隔离

---

## 测试覆盖

| 模块 | 测试文件 | 测试数 | 状态 |
|------|----------|--------|------|
| SubAgentTool | test_subagent_tool.py | 11 | ✅ |
| 子 Agent 创建 | test_sub_agent.py | 18 | ✅ |
| AgentType 定义 | test_agent_type.py | 14 | ✅ |
| TaskManager | test_task_manager.py | 10 | ✅ |
| Worktree 隔离 | test_worktree.py | 9 | ✅ |
| Loop SubAgent 集成 | test_loop_subagent.py | 16 | ✅ |
| **总计** | | **78** | **78 passed, 0 failed** |

---

## 各模块测试详情

### 1. SubAgentTool（11 个测试）

**覆盖场景**:
- 工具属性: name、description、parameters
- 输入验证: 有效输入、空 prompt、缺少 prompt
- 执行: 成功执行、父 Agent 未找到、约束检查
- 结果格式: 成功结果、失败结果、stopped 结果

**关键测试**:
```python
# 验证工具属性
def test_tool_name():
    assert SubAgentTool.name == "subagent"

# 验证输入验证
def test_validate_empty_prompt():
    # 空 prompt 返回验证失败

# 验证执行
def test_execute_success():
    # 成功创建子 Agent 并执行
```

---

### 2. 子 Agent 创建（18 个测试）

**覆盖场景**:
- SubAgentConstraints: 创建限制、token 预算、计数器
- SubAgentResult: 完成、停止、失败结果
- SubAgentStatus: 状态流转
- 上下文隔离: 独立消息历史、工具过滤、最大轮次限制

**关键测试**:
```python
# 验证约束共享
def test_constraints_shared():
    # 子 Agent 从父 Agent 继承约束

# 验证上下文隔离
def test_independent_messages():
    # 子 Agent 有独立的消息历史

# 验证工具过滤
def test_filtered_tools():
    # 子 Agent 只能使用允许的工具
```

---

### 3. AgentType 定义（14 个测试）

**覆盖场景**:
- AgentTypeDefinition: 创建、frozen 属性
- AgentTypeRegistry: 注册、获取、删除
- 内置类型: general_purpose、explore、code_reviewer
- 工具过滤: general_purpose 获取所有工具、explore 限制工具、code_reviewer 只读

**关键测试**:
```python
# 验证内置类型
def test_builtin_types_registered():
    # general_purpose、explore、code_reviewer 已注册

# 验证工具过滤
def test_explore_default_max_turns():
    # explore 类型默认 max_turns=10

def test_code_reviewer_read_only():
    # code_reviewer 只能使用只读工具
```

---

### 4. TaskManager（10 个测试）

**覆盖场景**:
- 任务注册: 返回 task_id
- 状态查询: running、completed
- 结果获取: 阻塞等待、立即返回
- 任务停止: 存在、不存在
- 任务列表: 列出所有任务
- 清理: 清理已完成任务
- 并发访问: 多线程安全

**关键测试**:
```python
# 验证阻塞等待
def test_get_result_blocks_until_complete():
    # 结果未就绪时阻塞，直到完成

# 验证并发安全
def test_concurrent_access():
    # 多线程同时访问不会崩溃
```

---

### 5. Worktree 隔离（9 个测试）

**覆盖场景**:
- 创建: 成功、失败、超时、git 未找到
- 清理: 成功、失败、超时
- 孤儿清理: 无 worktrees 目录、无孤儿

**关键测试**:
```python
# 验证创建成功
def test_create_success():
    # 成功创建 git worktree

# 验证超时处理
def test_create_timeout():
    # 超时后返回错误

# 验证孤儿清理
def test_cleanup_orphaned_worktrees():
    # 清理不再需要的 worktree
```

---

### 6. Loop SubAgent 集成（16 个测试）

**覆盖场景**:
- 创建子 Agent: 成功创建、独立消息、工具过滤、轮次限制、约束共享、记录创建
- 构建 prompt: 包含类型描述、父记忆、额外上下文、工具列表
- 结果创建: 完成、停止、失败结果
- 约束检查: Agent 计数超限、Token 预算耗尽

**关键测试**:
```python
# 验证子 Agent 创建
def test_creates_sub_agent():
    # 成功创建子 Agent 实例

# 验证上下文隔离
def test_sub_agent_has_independent_messages():
    # 子 Agent 有独立的消息历史

# 验证约束检查
def test_agent_counter_exceeded():
    # 超过最大 Agent 数量时返回错误

def test_token_budget_exhausted():
    # Token 预算耗尽时返回错误
```

---

## Bug 修复记录

### Bug 1：`_find_parent_agent()` 返回 None

**严重程度**: Critical（功能完全不可用）

**现象**: 调用 subagent 工具时，每次都返回错误 "[错误] 无法找到父 Agent 实例"

**根因**: `ToolUseContext` 没有 `agent_loop` 字段，`_find_parent_agent()` 无法获取父 Agent 引用，写死了 `return None`

**修复**:
- `src/agent/core/context.py` — 添加 `agent_loop: Any = None` 字段
- `src/agent/core/loop.py` — 创建 ToolUseContext 时传入 `agent_loop=self`
- `src/agent/tools/subagent.py` — `_find_parent_agent` 改为 `return context.agent_loop`

**影响范围**: 所有 subagent 调用

---

### Bug 2：SubAgentConstraints 每次新建

**严重程度**: High（资源限制失效）

**现象**: token budget 和 agent counter 限制不生效，每次调用约束都是全新的

**根因**: `_execute_subagent` 里直接 `constraints = SubAgentConstraints()`，没有从父 Agent 继承

**修复**: 改为从 `parent_loop._subagent_constraints` 继承，首次调用时创建并绑定到父 Agent

**影响范围**: 嵌套子 Agent 的资源限制

---

## 真实模型验证（待补充）

由于 API 限流，真实模型验证测试暂时无法运行。待补充以下测试：

### 测试场景 1：基本 SubAgent 调用

**任务**: 使用 subagent 搜索项目中所有包含 "TODO" 的 Python 文件

**验证点**:
- 模型是否正确调用 subagent 工具
- 子 Agent 是否独立执行任务
- 结果是否正确返回给主 Agent

### 测试场景 2：上下文隔离验证

**任务**: 主 Agent 和子 Agent 同时读取不同文件

**验证点**:
- 子 Agent 的消息历史是否独立
- 子 Agent 是否能访问主 Agent 的记忆

### 测试场景 3：资源约束验证

**任务**: 创建多个子 Agent，验证 token budget 限制

**验证点**:
- Agent 计数是否正确
- Token 预算是否生效
- 超限时是否返回错误

---

## 设计决策

### 1. 为什么用 ToolUseContext 传递 agent_loop？

**原因**: 避免循环导入。

```
loop.py → subagent.py (注册工具)
subagent.py → loop.py (创建子 Agent)
```

如果直接 import，会死循环。通过 context 传递引用打破了循环依赖。

---

### 2. 为什么子 Agent 要有独立上下文？

**原因**: 避免污染主对话。

子 Agent 执行的是独立子任务，它的中间步骤、错误、调试信息不应该出现在主对话中。只有最终结果返回给主 Agent。

---

### 3. 为什么需要 AgentType？

**原因**: 预定义角色，简化配置。

不同任务需要不同的能力：
- explore: 只读，快速搜索
- code_reviewer: 只读，代码分析
- general_purpose: 全部工具

通过 AgentType，用户不需要手动配置工具过滤。

---

### 4. 为什么用 Git Worktree 隔离？

**原因**: 文件系统级别的隔离。

当多个子 Agent 同时修改文件时，可能会冲突。Git Worktree 让每个子 Agent 在独立的工作目录中操作，避免冲突。

---

## 面试要点

### 1. 多 Agent 系统的架构？

**答**:
```
主 Agent (AgentLoop)
  ↓ 调用 subagent 工具
SubAgentTool._execute()
  ↓ 创建子 Agent
AgentLoop._create_subagent()
  ↓ 独立上下文 + 工具过滤
子 Agent 执行任务
  ↓ 返回结果
SubAgentResult → 主 Agent
```

---

### 2. 如何实现上下文隔离？

**答**: 子 Agent 创建时：
- 独立的 messages 列表（只包含 task 描述）
- 独立的 ToolUseContext（不共享文件读取状态）
- 工具过滤（根据 AgentType 只允许部分工具）

---

### 3. 如何控制资源使用？

**答**: SubAgentConstraints 机制：
- agent_counter: 限制同时运行的 Agent 数量
- token_budget: 限制总 token 消耗
- 从父 Agent 继承，所有子 Agent 共享约束

---

### 4. 和 Claude Code 的 SubAgent 有什么区别？

**答**:
- Claude Code: 用 worktree 实现文件系统隔离
- 我们: 支持 worktree（可选），默认用上下文隔离

**权衡**: worktree 隔离更彻底，但开销更大。我们让用户选择。

---

## 总结

P5 阶段实现了完整的多 Agent 系统：

| 维度 | 状态 |
|------|------|
| 测试数量 | 78 个（全部通过） |
| 模块覆盖 | 6 个模块全部覆盖 |
| Bug 修复 | 2 个关键 Bug 已修复 |
| 真实模型验证 | 待补充（API 限流） |

**关键发现**:
1. 上下文隔离是多 Agent 系统的核心，避免子 Agent 污染主对话
2. 资源约束机制防止子 Agent 失控（无限创建、耗尽 token）
3. AgentType 预定义角色，简化用户配置
4. Git Worktree 提供可选的文件系统隔离

**待改进**:
1. 补充真实模型验证测试
2. 优化 SubAgent prompt 构建，提高模型调用成功率
3. 支持更多 AgentType（如 tester、documenter）
