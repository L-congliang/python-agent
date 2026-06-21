# F09 权限检查器（PermissionChecker）

## 需求

实现通用权限策略层，根据工具的行为标记（`is_read_only`、`is_destructive`）和权限模式自动判断是否允许执行。这是 `permissions/` 目录的核心模块。

### 核心职责

1. **权限模式管理**：支持不同权限模式（default、plan）
2. **自动策略判断**：基于工具行为标记自动决策（allow/deny/ask）
3. **工具级权限委托**：调用工具的 `check_permissions` 方法获取工具级决策
4. **决策合并**：合并工具级决策和系统级策略

### 权限模式

| 模式 | 只读工具 | 非只读工具 | 非只读+破坏性 |
|------|----------|------------|---------------|
| `default` | allow | ask | ask |
| `plan` | allow | deny | deny |

- **default**：正常模式，非只读操作需要用户确认
- **plan**：计划模式，只允许只读操作，禁止所有写入

### 决策优先级

```
工具级 check_permissions
    ↓ (如果返回 deny/ask，直接使用)
    ↓ (如果返回 allow，继续检查系统级策略)
系统级策略（基于 is_read_only/is_destructive + 权限模式）
```

## 接口

### PermissionMode 枚举

```python
class PermissionMode(Enum):
    DEFAULT = "default"   # 正常模式
    PLAN = "plan"         # 计划模式（只读）
```

### PermissionChecker 类

```python
class PermissionChecker:
    """权限检查器，管理权限模式和自动策略判断。"""

    def __init__(self, mode: PermissionMode = PermissionMode.DEFAULT) -> None:
        """初始化权限检查器。

        Args:
            mode: 权限模式
        """
        ...

    @property
    def mode(self) -> PermissionMode:
        """当前权限模式。"""
        ...

    def set_mode(self, mode: PermissionMode) -> None:
        """切换权限模式。

        Args:
            mode: 新的权限模式
        """
        ...

    def check(self, tool: Tool, input_data: dict, context: ToolUseContext) -> PermissionDecision:
        """检查工具是否有权限执行。

        执行流程：
        1. 调用工具的 check_permissions 获取工具级决策
        2. 如果工具级决策是 deny/ask，直接返回
        3. 如果工具级决策是 allow，检查系统级策略
        4. 返回最终决策

        Args:
            tool: 工具实例
            input_data: 工具输入
            context: 工具执行上下文

        Returns:
            最终的权限决策
        """
        ...
```

### 辅助函数

```python
def check_system_policy(
    tool: Tool,
    input_data: dict,
    mode: PermissionMode,
) -> PermissionDecision:
    """检查系统级权限策略。

    基于工具的 is_read_only/is_destructive 标记和权限模式做出决策。

    Args:
        tool: 工具实例
        input_data: 工具输入
        mode: 权限模式

    Returns:
        系统级权限决策
    """
    ...
```

## 场景

### 场景 1：default 模式 + 只读工具
- 工具：file_read（is_read_only=True）
- 预期：allow（无需确认）

### 场景 2：default 模式 + 非只读工具
- 工具：file_write（is_read_only=False）
- 预期：ask（需要用户确认）

### 场景 3：default 模式 + 破坏性工具
- 工具：bash（is_read_only=False, is_destructive=True）
- 预期：ask（需要用户确认）

### 场景 4：plan 模式 + 只读工具
- 工具：file_read（is_read_only=True）
- 预期：allow

### 场景 5：plan 模式 + 非只读工具
- 工具：file_write（is_read_only=False）
- 预期：deny（计划模式禁止写入）

### 场景 6：工具级 deny 覆盖系统级 allow
- 工具 check_permissions 返回 deny
- 系统级策略是 allow
- 预期：deny（工具级优先）

### 场景 7：工具级 allow + 系统级 ask
- 工具 check_permissions 返回 allow
- 系统级策略是 ask
- 预期：ask（系统级策略生效）

### 场景 8：工具级 updated_input
- 工具 check_permissions 返回 allow(updated_input=...)
- 预期：使用修改后的输入

## 验收标准

1. ✅ PermissionMode 枚举定义正确
2. ✅ PermissionChecker 类实现完整
3. ✅ check() 方法按优先级合并工具级和系统级决策
4. ✅ check_system_policy() 基于 is_read_only/is_destructive + 模式判断
5. ✅ default 模式：只读=allow，非只读=ask
6. ✅ plan 模式：只读=allow，非只读=deny
7. ✅ 工具级 deny/ask 优先于系统级策略
8. ✅ 工具级 updated_input 正确传递
9. ✅ 所有测试通过
10. ✅ mypy --strict 无错误
