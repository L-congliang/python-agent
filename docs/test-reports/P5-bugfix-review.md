# P5 多 Agent — Bug 修复测试报告

**日期**: 2026-07-02
**Session**: 19
**内容**: P5 多 Agent 系统代码审查 + Bug 修复

---

## 发现的 Bug

### Bug 1：`_find_parent_agent()` 返回 None

**严重程度**: Critical（功能完全不可用）

**现象**: 调用 subagent 工具时，每次都返回错误 "[错误] 无法找到父 Agent 实例"

**根因**: `ToolUseContext` 没有 `agent_loop` 字段，`_find_parent_agent()` 无法获取父 Agent 引用，写死了 `return None`

**修复**:
- `src/agent/core/context.py` — 添加 `agent_loop: Any = None` 字段
- `src/agent/core/loop.py` — 创建 ToolUseContext 时传入 `agent_loop=self`
- `src/agent/tools/subagent.py` — `_find_parent_agent` 改为 `return context.agent_loop`

**影响范围**: 所有 subagent 调用

### Bug 2：SubAgentConstraints 每次新建

**严重程度**: High（资源限制失效）

**现象**: token budget 和 agent counter 限制不生效，每次调用约束都是全新的

**根因**: `_execute_subagent` 里直接 `constraints = SubAgentConstraints()`，没有从父 Agent 继承

**修复**: 改为从 `parent_loop._subagent_constraints` 继承，首次调用时创建并绑定到父 Agent

**影响范围**: 嵌套子 Agent 的资源限制

### 额外修复

- 调换 parent_loop 赋值顺序（先找父 Agent，再取约束）
- 修 `input: dict` → `input: dict[str, Any]` 类型注解

---

## 验证结果

### 类型检查

```
uv run mypy src/agent/core/context.py src/agent/tools/subagent.py --strict
Success: no issues found in 2 source files
```

### 全量测试

```
uv run pytest tests/ -x -v
================== 709 passed, 3 skipped in 65.76s ==================
```

### 相关测试文件

| 测试文件 | 测试数 | 状态 |
|----------|--------|------|
| test_subagent_tool.py | 11 | ✅ 全部通过 |
| test_sub_agent.py | 11 | ✅ 全部通过 |
| test_agent_type.py | 10 | ✅ 全部通过 |
| test_task_manager.py | 8 | ✅ 全部通过 |
| test_worktree.py | 7 | ✅ 全部通过 |
| test_loop_subagent.py | 15 | ✅ 全部通过 |

---

## 修改的文件

| 文件 | 改动 |
|------|------|
| `src/agent/core/context.py` | +1 字段 (`agent_loop`)，+1 导入 (`Any`) |
| `src/agent/core/loop.py` | +1 行 (`agent_loop=self`) |
| `src/agent/tools/subagent.py` | 修复 `_find_parent_agent`，修复 constraints 继承，修复类型注解 |

---

## 面试要点

**问**: P5 多 Agent 系统有什么 Bug？
**答**: 发现了两个关键 Bug：
1. 父 Agent 引用传递问题 — ToolUseContext 没有 agent_loop 字段，导致子 Agent 无法创建。通过给 context 加字段解决。
2. 约束不共享 — 每次调用新建 SubAgentConstraints，token budget 限制形同虚设。改为从父 Agent 继承共享约束。

**问**: 为什么用 context 传递 agent_loop 而不是直接 import？
**答**: 避免循环导入。loop.py 引用 subagent.py（注册工具），subagent.py 引用 loop.py（创建子 Agent），互相 import 会死循环。通过 context 传递引用打破了循环依赖。
