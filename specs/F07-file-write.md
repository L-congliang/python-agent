# F07: 文件写入工具（Write + Edit）

> **参考**: Claude Code 的 Write/Edit 工具
> **前置依赖**: F03 Tool Protocol, F06 FileReadState

## 设计目标

实现文件写入工具，让 Agent 能够创建和修改文件内容。

这是编程助手的核心能力：
- 创建新文件（模块、配置、脚本等）
- 修改现有文件（修复 bug、添加功能、重构代码）
- 支持 Jupyter Notebook 的完整写入
- 自动创建目录，减少用户交互成本

## 与 Claude Code 的对齐点

| Claude Code | python-agent | 说明 |
|-------------|--------------|------|
| `Write` 工具 | `write` 工具 | 创建/覆盖文件 |
| `Edit` 工具 | `edit` 工具 | 精确替换 |
| `file_path` 参数 | `file_path` 参数 | 文件路径 |
| `content` 参数 | `content` 参数 | 文件内容 |
| `old_string` 参数 | `old_string` 参数 | 要替换的文本 |
| `new_string` 参数 | `new_string` 参数 | 替换后的文本 |
| `replace_all` 参数 | `replace_all` 参数 | 是否替换所有 |
| 先读后写 | 先读后写 | 安全机制 |
| 自动创建目录 | 自动创建目录 | 用户体验 |

## 设计决策总览

| 决策 | 选择 | 理由 |
|------|------|------|
| 工具分离 | Write + Edit 两个工具 | 职责分离，与 Claude Code 对齐 |
| Write 模式 | 覆盖模式 | 文件存在则覆盖，不存在则创建 |
| Edit 唯一性 | 严格唯一 | old_string 必须唯一匹配，避免误改 |
| 安全机制 | 先读后写 | Write/Edit 前必须先 Read，确保理解上下文 |
| 缓存策略 | 写入后更新缓存 | 避免下次 Read 重新读取 |
| 目录创建 | 自动创建目录 | 用户体验更好，减少交互成本 |
| 编码处理 | 固定 UTF-8 | 简化实现，覆盖 99% 场景 |
| 行号处理 | 纯内容 | Write 写入源代码，不带行号装饰 |
| 并发安全 | 不并发安全 | 避免同时写入同一文件冲突 |
| 权限确认 | 需要权限确认 | Write/Edit 是写操作，需要用户确认 |
| 错误处理 | 完整错误处理 | 自动创建文件/目录、磁盘空间检查、权限检查 |

## 文件结构

```
src/agent/tools/
├── base.py           # 已有（Tool Protocol）
├── registry.py       # 已有（ToolRegistry）
├── __init__.py       # 已有（需添加导出）
├── bash.py           # 已有
├── file_read.py      # 已有（F06）
├── file_write.py     # 新增：Write 工具
└── file_edit.py      # 新增：Edit 工具
```

### `file_write.py` 内部结构

```
file_write.py
├── _resolve_path()              # 路径解析（相对 → 绝对）
├── _ensure_directory()          # 自动创建父目录
├── _check_write_permission()    # 检查写权限
├── _check_disk_space()          # 检查磁盘空间
├── _update_cache()              # 更新 FileReadState 缓存
├── _write_notebook()            # 写入 Jupyter Notebook
├── _validate_notebook_structure() # 验证 Notebook 结构
├── FILE_WRITE_PARAMETERS        # 参数定义
├── validate_file_write_input()  # 输入校验
├── execute_file_write()         # 核心执行逻辑
└── file_write_tool              # build_tool() 工厂调用
```

### `file_edit.py` 内部结构

```
file_edit.py
├── FILE_EDIT_PARAMETERS         # 参数定义
├── validate_file_edit_input()   # 输入校验
├── execute_file_edit()          # 核心执行逻辑
└── file_edit_tool               # build_tool() 工厂调用
```

---

## 接口定义

### 1. Write 工具参数 Schema

```python
FILE_WRITE_PARAMETERS = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "要写入的文件路径（绝对路径或相对于 cwd 的路径）",
        },
        "content": {
            "type": "string",
            "description": "要写入的文件内容（纯文本，不带行号）",
        },
    },
    "required": ["file_path", "content"],
}
```

### 2. Edit 工具参数 Schema

```python
FILE_EDIT_PARAMETERS = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "要修改的文件路径（绝对路径或相对于 cwd 的路径）",
        },
        "old_string": {
            "type": "string",
            "description": "要替换的原始文本（必须在文件中唯一匹配）",
        },
        "new_string": {
            "type": "string",
            "description": "替换后的新文本",
        },
        "replace_all": {
            "type": "boolean",
            "description": "是否替换所有匹配项（默认 false）",
            "default": False,
        },
    },
    "required": ["file_path", "old_string", "new_string"],
}
```

### 3. 路径解析（共享）

```python
def _resolve_path(file_path: str, cwd: str) -> str:
    """解析文件路径为绝对路径

    - 绝对路径：直接使用
    - 相对路径：相对于 context.cwd 解析

    Args:
        file_path: 输入路径（绝对或相对）
        cwd: 当前工作目录

    Returns:
        绝对路径字符串
    """
    if os.path.isabs(file_path):
        return file_path
    return os.path.abspath(os.path.join(cwd, file_path))
```

### 4. 自动创建目录（共享）

```python
def _ensure_directory(file_path: str) -> None:
    """确保父目录存在，不存在则自动创建

    Args:
        file_path: 文件绝对路径

    Raises:
        OSError: 目录创建失败
    """
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
```

### 5. 检查写权限（共享）

```python
def _check_write_permission(file_path: str) -> str | None:
    """检查文件是否可写

    Args:
        file_path: 文件绝对路径

    Returns:
        None: 可写
        str: 错误信息（不可写）
    """
    if os.path.exists(file_path):
        # 文件存在，检查文件权限
        if not os.access(file_path, os.W_OK):
            return f"文件不可写: {file_path}"
    else:
        # 文件不存在，检查目录权限
        directory = os.path.dirname(file_path)
        if directory and not os.access(directory, os.W_OK):
            return f"目录不可写: {directory}"
    return None
```

### 6. 检查磁盘空间（共享）

```python
def _check_disk_space(file_path: str, content_size: int) -> str | None:
    """检查磁盘空间是否足够

    Args:
        file_path: 文件绝对路径
        content_size: 要写入的内容大小（字节）

    Returns:
        None: 空间足够
        str: 错误信息（空间不足）
    """
    try:
        directory = os.path.dirname(file_path) or "."
        stat = os.statvfs(directory)
        free_space = stat.f_bavail * stat.f_frsize
        if content_size > free_space:
            return f"磁盘空间不足: 需要 {content_size} 字节，可用 {free_space} 字节"
    except OSError:
        # Windows 不支持 statvfs，跳过检查
        pass
    return None
```

### 7. 更新缓存（共享）

```python
def _update_cache(file_path: str, content: str, context: ToolUseContext) -> None:
    """更新 FileReadState 缓存

    Args:
        file_path: 文件绝对路径
        content: 文件内容
        context: 工具执行上下文
    """
    mtime = os.path.getmtime(file_path)
    context.file_read_state.set(file_path, content, mtime)
```

### 8. Notebook 写入

```python
def _write_notebook(file_path: str, content: str) -> None:
    """写入 Jupyter Notebook

    流程:
    1. 解析 JSON 内容
    2. 验证 Notebook 结构（cells、metadata、nbformat）
    3. 写入文件（UTF-8 编码）

    Args:
        file_path: Notebook 文件路径
        content: Notebook JSON 内容

    Raises:
        ValueError: JSON 格式无效
        ValueError: Notebook 结构无效
    """
    try:
        notebook = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"无效的 JSON 格式: {e}")

    # 验证 Notebook 结构
    validation_error = _validate_notebook_structure(notebook)
    if validation_error:
        raise ValueError(validation_error)

    # 写入文件
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(notebook, f, indent=1, ensure_ascii=False)


def _validate_notebook_structure(notebook: dict) -> str | None:
    """验证 Notebook 结构

    Args:
        notebook: Notebook 字典

    Returns:
        None: 有效
        str: 错误信息（无效）
    """
    required_fields = ["cells", "metadata", "nbformat"]
    for field in required_fields:
        if field not in notebook:
            return f"Notebook 缺少 {field} 字段"

    # 验证 cells 是列表
    if not isinstance(notebook["cells"], list):
        return "cells 字段必须是列表"

    # 验证每个 cell 的结构
    for i, cell in enumerate(notebook["cells"]):
        if "cell_type" not in cell:
            return f"Cell {i} 缺少 cell_type 字段"
        if "source" not in cell:
            return f"Cell {i} 缺少 source 字段"

    return None
```

### 9. Write 工具输入校验

```python
def validate_file_write_input(raw_input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
    """校验文件写入输入

    校验规则:
    1. file_path 必须存在且非空字符串
    2. file_path 必须是字符串类型
    3. content 必须存在且是字符串类型
    4. 解析后的路径不能是目录

    Args:
        raw_input: 工具输入
        context: 工具执行上下文

    Returns:
        ValidationResult
    """
    file_path = raw_input.get("file_path")
    if not file_path or not isinstance(file_path, str) or not file_path.strip():
        return ValidationResult.failure("file_path 不能为空")

    content = raw_input.get("content")
    if content is None or not isinstance(content, str):
        return ValidationResult.failure("content 不能为空")

    # 检查路径是否是目录
    abs_path = _resolve_path(file_path, context.cwd)
    if os.path.isdir(abs_path):
        return ValidationResult.failure(f"路径是目录，不是文件: {abs_path}")

    return ValidationResult.success()
```

### 10. Edit 工具输入校验

```python
def validate_file_edit_input(raw_input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
    """校验文件编辑输入

    校验规则:
    1. file_path 必须存在且非空字符串
    2. file_path 必须是字符串类型
    3. old_string 必须存在且是字符串类型
    4. new_string 必须存在且是字符串类型
    5. 解析后的路径必须存在
    6. 解析后的路径必须是文件（不能是目录）
    7. old_string 必须在文件中存在
    8. 如果 replace_all=False，old_string 必须唯一匹配

    Args:
        raw_input: 工具输入
        context: 工具执行上下文

    Returns:
        ValidationResult
    """
    file_path = raw_input.get("file_path")
    if not file_path or not isinstance(file_path, str) or not file_path.strip():
        return ValidationResult.failure("file_path 不能为空")

    old_string = raw_input.get("old_string")
    if old_string is None or not isinstance(old_string, str):
        return ValidationResult.failure("old_string 不能为空")

    new_string = raw_input.get("new_string")
    if new_string is None or not isinstance(new_string, str):
        return ValidationResult.failure("new_string 不能为空")

    # 检查文件存在性
    abs_path = _resolve_path(file_path, context.cwd)
    if not os.path.exists(abs_path):
        return ValidationResult.failure(f"文件不存在: {abs_path}")

    if os.path.isdir(abs_path):
        return ValidationResult.failure(f"路径是目录，不是文件: {abs_path}")

    # 读取文件内容
    try:
        with open(abs_path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return ValidationResult.failure(f"读取文件失败: {e}")

    # 检查 old_string 是否存在
    if old_string not in content:
        return ValidationResult.failure(f"old_string 在文件中不存在")

    # 检查唯一性（replace_all=False 时）
    replace_all = raw_input.get("replace_all", False)
    if not replace_all:
        count = content.count(old_string)
        if count > 1:
            return ValidationResult.failure(f"old_string 匹配多个（{count} 个），请提供更精确的 old_string")

    return ValidationResult.success()
```

### 11. Write 工具核心执行

```python
def execute_file_write(input: dict[str, Any], context: ToolUseContext) -> ToolResult:
    """写入文件内容

    流程:
    1. 解析参数（file_path, content）
    2. 解析路径（_resolve_path，相对 → 绝对）
    3. 检查中断状态
    4. 检查写权限（_check_write_permission）
    5. 检查磁盘空间（_check_disk_space）
    6. 自动创建父目录（_ensure_directory）
    7. 写入文件（UTF-8 编码）
    8. 更新缓存（_update_cache）
    9. 返回 ToolResult

    Args:
        input: {"file_path": "src/main.py", "content": "..."}
        context: 工具执行上下文

    Returns:
        ToolResult:
        - output: "写入成功" 或错误信息
        - is_error: 写入失败时为 True
    """
    try:
        # 1. 解析参数
        file_path = input.get("file_path")
        content = input.get("content")

        # 2. 解析路径
        abs_path = _resolve_path(file_path, context.cwd)

        # 3. 检查中断
        if context.abort_controller.is_aborted:
            return ToolResult(output="文件写入被取消", is_error=True)

        # 4. 检查写权限
        permission_error = _check_write_permission(abs_path)
        if permission_error:
            return ToolResult(output=permission_error, is_error=True)

        # 5. 检查磁盘空间
        space_error = _check_disk_space(abs_path, len(content.encode("utf-8")))
        if space_error:
            return ToolResult(output=space_error, is_error=True)

        # 6. 自动创建目录
        _ensure_directory(abs_path)

        # 7. 写入文件
        if abs_path.endswith(".ipynb"):
            _write_notebook(abs_path, content)
        else:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)

        # 8. 更新缓存
        _update_cache(abs_path, content, context)

        return ToolResult(output="写入成功", is_error=False)

    except ValueError as e:
        return ToolResult(output=f"输入错误: {e}", is_error=True)
    except OSError as e:
        return ToolResult(output=f"文件系统错误: {e}", is_error=True)
    except Exception as e:
        return ToolResult(output=f"写入失败: {e}", is_error=True)
```

### 12. Edit 工具核心执行

```python
def execute_file_edit(input: dict[str, Any], context: ToolUseContext) -> ToolResult:
    """修改文件内容

    流程:
    1. 解析参数（file_path, old_string, new_string, replace_all）
    2. 解析路径（_resolve_path，相对 → 绝对）
    3. 检查中断状态
    4. 检查文件存在性
    5. 读取文件内容（带缓存）
    6. 查找 old_string 匹配
    7. 校验唯一性（replace_all=False 时）
    8. 执行替换
    9. 写入文件（UTF-8 编码）
    10. 更新缓存（_update_cache）
    11. 返回 ToolResult

    Args:
        input: {
            "file_path": "src/main.py",
            "old_string": "def hello():",
            "new_string": "def hello(name):",
            "replace_all": False
        }
        context: 工具执行上下文

    Returns:
        ToolResult:
        - output: "修改成功" 或错误信息
        - is_error: 修改失败时为 True
    """
    try:
        # 1. 解析参数
        file_path = input.get("file_path")
        old_string = input.get("old_string")
        new_string = input.get("new_string")
        replace_all = input.get("replace_all", False)

        # 2. 解析路径
        abs_path = _resolve_path(file_path, context.cwd)

        # 3. 检查中断
        if context.abort_controller.is_aborted:
            return ToolResult(output="文件编辑被取消", is_error=True)

        # 4. 检查文件存在性
        if not os.path.exists(abs_path):
            return ToolResult(output=f"文件不存在: {abs_path}", is_error=True)

        if os.path.isdir(abs_path):
            return ToolResult(output=f"路径是目录，不是文件: {abs_path}", is_error=True)

        # 5. 读取文件内容
        try:
            with open(abs_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return ToolResult(output=f"读取文件失败: {e}", is_error=True)

        # 6. 查找 old_string 匹配
        if old_string not in content:
            return ToolResult(output="old_string 在文件中不存在", is_error=True)

        # 7. 校验唯一性（replace_all=False 时）
        if not replace_all:
            count = content.count(old_string)
            if count > 1:
                return ToolResult(
                    output=f"old_string 匹配多个（{count} 个），请提供更精确的 old_string",
                    is_error=True,
                )

        # 8. 执行替换
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        # 9. 写入文件
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # 10. 更新缓存
        _update_cache(abs_path, new_content, context)

        return ToolResult(output="修改成功", is_error=False)

    except Exception as e:
        return ToolResult(output=f"编辑失败: {e}", is_error=True)
```

### 13. 工具注册

```python
# Write 工具注册
file_write_tool = build_tool(
    name="write",
    description="写入文件内容。创建新文件或覆盖现有文件。",
    parameters=FILE_WRITE_PARAMETERS,
    execute_fn=execute_file_write,
    is_read_only=lambda input: False,       # 写操作
    is_concurrency_safe=lambda input: False, # 不并发安全
    validate_input=validate_file_write_input,
    get_summary=lambda input: f"Writing {input.get('file_path', '')}",
    get_user_facing_name=lambda input: "Write",
    get_activity_description=lambda input: f"Writing {input.get('file_path', '')}",
)

# Edit 工具注册
file_edit_tool = build_tool(
    name="edit",
    description="修改文件内容。基于 old_string/new_string 精确替换。",
    parameters=FILE_EDIT_PARAMETERS,
    execute_fn=execute_file_edit,
    is_read_only=lambda input: False,       # 写操作
    is_concurrency_safe=lambda input: False, # 不并发安全
    validate_input=validate_file_edit_input,
    get_summary=lambda input: f"Editing {input.get('file_path', '')}",
    get_user_facing_name=lambda input: "Edit",
    get_activity_description=lambda input: f"Editing {input.get('file_path', '')}",
)
```

---

## 核心设计决策

### 1. 为什么 Write 和 Edit 要分开？

职责分离原则：
- **Write** 负责"整个文件"：创建新文件或完全覆盖现有文件
- **Edit** 负责"局部修改"：基于 old_string/new_string 精确替换

分开的好处：
1. 每个工具只做一件事，易于理解和测试
2. 与 Claude Code 对齐，用户熟悉这种设计
3. 如果合并，参数复杂，容易出错
4. 职责分离，代码清晰，易于维护

### 2. 为什么 Edit 的 old_string 必须唯一匹配？

避免误改：
1. 如果 old_string 匹配多个，Edit 不知道改哪个
2. 强制唯一匹配，确保修改意图清晰
3. 用户可以通过提供更精确的 old_string 来解决
4. 如果确实需要替换所有，可以用 replace_all=True

### 3. 为什么 Write 要先读后写（Read-before-Write）？

安全机制：
1. 确保模型理解文件内容后再写入
2. 防止误覆盖重要文件
3. 与 Claude Code 的设计一致
4. 提高用户对模型操作的信任度

### 4. 为什么写入后要更新缓存？

性能优化：
1. 写入后文件内容已知，更新缓存避免下次 Read 重新读取
2. mtime 也已知，可以直接设置
3. 减少磁盘 I/O，提高响应速度
4. 保证缓存与磁盘内容一致

### 5. 为什么 Write/Edit 不并发安全？

数据完整性：
1. 同时写入同一文件会导致内容混乱
2. 串行执行更容易预测结果
3. Agent 循环中很少需要同时写多个文件
4. 通过 is_concurrency_safe=False 标记，让 ToolRegistry 确保串行执行

### 6. 为什么固定 UTF-8 编码？

简化实现：
1. UTF-8 覆盖 99% 场景
2. 避免编码检测的复杂性
3. 如果原文件是 GBK，写入 UTF-8 后可能乱码
4. 但编程助手通常创建新文件，不是修改旧文件
5. 如果需要保持原编码，可以用 Edit 工具

### 7. 为什么自动创建目录而不是报错？

用户体验：
1. 用户说"写入 src/utils/helper.py"，期望自动创建目录
2. 减少交互成本，不需要先手动 mkdir
3. Claude Code 也是这样做的
4. 如果路径有误，后续 Read 会发现文件不存在

### 8. 为什么不限制写入文件大小？

YAGNI 原则：
1. 编程助手很少需要写入超大文件
2. 如果限制大小，需要额外的确认逻辑
3. 增加复杂度，但收益不大
4. 如果需要限制，可以后续按需添加

---

## 测试场景

### 1. Write 工具基本功能

```python
def test_basic_write():
    """创建新文件"""
    result = file_write_tool.execute(
        {"file_path": "test.txt", "content": "hello world"},
        context,
    )
    assert not result.is_error
    assert "写入成功" in result.output
    # 验证文件内容
    with open("test.txt", encoding="utf-8") as f:
        assert f.read() == "hello world"

def test_overwrite_existing():
    """覆盖现有文件"""
    # 先创建文件
    with open("test.txt", "w", encoding="utf-8") as f:
        f.write("old content")
    # 覆盖
    result = file_write_tool.execute(
        {"file_path": "test.txt", "content": "new content"},
        context,
    )
    assert not result.is_error
    # 验证内容已更新
    with open("test.txt", encoding="utf-8") as f:
        assert f.read() == "new content"

def test_auto_create_directory():
    """自动创建父目录"""
    result = file_write_tool.execute(
        {"file_path": "src/utils/helper.py", "content": "print('hello')"},
        context,
    )
    assert not result.is_error
    # 验证目录已创建
    assert os.path.exists("src/utils/helper.py")
```

### 2. Edit 工具基本功能

```python
def test_basic_edit():
    """基本替换"""
    # 先创建文件
    with open("test.txt", "w", encoding="utf-8") as f:
        f.write("def hello():\n    print('hello')")
    # 替换
    result = file_edit_tool.execute(
        {
            "file_path": "test.txt",
            "old_string": "def hello():",
            "new_string": "def hello(name):",
        },
        context,
    )
    assert not result.is_error
    # 验证内容已更新
    with open("test.txt", encoding="utf-8") as f:
        content = f.read()
        assert "def hello(name):" in content

def test_old_string_not_found():
    """old_string 不存在"""
    with open("test.txt", "w", encoding="utf-8") as f:
        f.write("hello world")
    result = file_edit_tool.execute(
        {
            "file_path": "test.txt",
            "old_string": "nonexistent",
            "new_string": "new",
        },
        context,
    )
    assert result.is_error
    assert "不存在" in result.output

def test_old_string_multiple_matches():
    """old_string 匹配多个"""
    with open("test.txt", "w", encoding="utf-8") as f:
        f.write("hello\nhello\nhello")
    result = file_edit_tool.execute(
        {
            "file_path": "test.txt",
            "old_string": "hello",
            "new_string": "hi",
            "replace_all": False,
        },
        context,
    )
    assert result.is_error
    assert "匹配多个" in result.output

def test_replace_all():
    """替换所有匹配项"""
    with open("test.txt", "w", encoding="utf-8") as f:
        f.write("hello\nhello\nhello")
    result = file_edit_tool.execute(
        {
            "file_path": "test.txt",
            "old_string": "hello",
            "new_string": "hi",
            "replace_all": True,
        },
        context,
    )
    assert not result.is_error
    # 验证所有都已替换
    with open("test.txt", encoding="utf-8") as f:
        content = f.read()
        assert content == "hi\nhi\nhi"
```

### 3. 错误处理

```python
def test_file_not_found():
    """Edit 工具：文件不存在"""
    result = file_edit_tool.execute(
        {
            "file_path": "nonexistent.py",
            "old_string": "old",
            "new_string": "new",
        },
        context,
    )
    assert result.is_error
    assert "不存在" in result.output

def test_path_is_directory():
    """路径是目录"""
    os.makedirs("test_dir", exist_ok=True)
    result = file_write_tool.execute(
        {"file_path": "test_dir", "content": "hello"},
        context,
    )
    assert result.is_error
    assert "目录" in result.output

def test_permission_denied():
    """文件不可写"""
    # 创建只读文件
    with open("readonly.txt", "w", encoding="utf-8") as f:
        f.write("content")
    os.chmod("readonly.txt", 0o444)  # 只读
    result = file_write_tool.execute(
        {"file_path": "readonly.txt", "content": "new content"},
        context,
    )
    assert result.is_error
    assert "不可写" in result.output
```

### 4. Notebook 写入

```python
def test_notebook_write():
    """写入 Jupyter Notebook"""
    notebook = {
        "cells": [
            {"cell_type": "code", "source": ["print('hello')"], "outputs": []}
        ],
        "metadata": {},
        "nbformat": 4,
    }
    result = file_write_tool.execute(
        {"file_path": "test.ipynb", "content": json.dumps(notebook)},
        context,
    )
    assert not result.is_error
    # 验证 Notebook 内容
    with open("test.ipynb", encoding="utf-8") as f:
        loaded = json.load(f)
        assert len(loaded["cells"]) == 1
```

### 5. 缓存更新

```python
def test_write_cache_update():
    """写入后更新缓存"""
    result = file_write_tool.execute(
        {"file_path": "test.txt", "content": "hello"},
        context,
    )
    assert not result.is_error
    # 验证缓存已更新
    cached = context.file_read_state.get(os.path.abspath("test.txt"))
    assert cached is not None
    assert cached[0] == "hello"

def test_edit_cache_update():
    """编辑后更新缓存"""
    with open("test.txt", "w", encoding="utf-8") as f:
        f.write("hello")
    result = file_edit_tool.execute(
        {
            "file_path": "test.txt",
            "old_string": "hello",
            "new_string": "hi",
        },
        context,
    )
    assert not result.is_error
    # 验证缓存已更新
    cached = context.file_read_state.get(os.path.abspath("test.txt"))
    assert cached is not None
    assert cached[0] == "hi"
```

### 6. 中断支持

```python
def test_write_abort():
    """中断文件写入"""
    context.abort_controller.abort()
    result = file_write_tool.execute(
        {"file_path": "test.txt", "content": "hello"},
        context,
    )
    assert result.is_error
    assert "取消" in result.output

def test_edit_abort():
    """中断文件编辑"""
    with open("test.txt", "w", encoding="utf-8") as f:
        f.write("hello")
    context.abort_controller.abort()
    result = file_edit_tool.execute(
        {
            "file_path": "test.txt",
            "old_string": "hello",
            "new_string": "hi",
        },
        context,
    )
    assert result.is_error
    assert "取消" in result.output
```

### 7. 输入校验

```python
def test_validate_write_empty_path():
    """空路径校验"""
    result = file_write_tool.validate_input({"file_path": "", "content": "hello"}, context)
    assert not result.is_valid

def test_validate_write_empty_content():
    """空内容校验"""
    result = file_write_tool.validate_input({"file_path": "test.txt", "content": ""}, context)
    assert not result.is_valid

def test_validate_edit_empty_old_string():
    """空 old_string 校验"""
    result = file_edit_tool.validate_input(
        {"file_path": "test.txt", "old_string": "", "new_string": "new"},
        context,
    )
    assert not result.is_valid

def test_validate_edit_empty_new_string():
    """空 new_string 校验"""
    result = file_edit_tool.validate_input(
        {"file_path": "test.txt", "old_string": "old", "new_string": ""},
        context,
    )
    assert not result.is_valid
```

### 8. 工具属性

```python
def test_write_tool_properties():
    """Write 工具属性正确"""
    assert file_write_tool.name == "write"
    assert "写入" in file_write_tool.description or "write" in file_write_tool.description.lower()
    assert "file_path" in file_write_tool.parameters["properties"]
    assert "content" in file_write_tool.parameters["properties"]
    assert not file_write_tool.is_read_only({})
    assert not file_write_tool.is_concurrency_safe({})

def test_edit_tool_properties():
    """Edit 工具属性正确"""
    assert file_edit_tool.name == "edit"
    assert "修改" in file_edit_tool.description or "edit" in file_edit_tool.description.lower()
    assert "file_path" in file_edit_tool.parameters["properties"]
    assert "old_string" in file_edit_tool.parameters["properties"]
    assert "new_string" in file_edit_tool.parameters["properties"]
    assert not file_edit_tool.is_read_only({})
    assert not file_edit_tool.is_concurrency_safe({})
```

---

## 依赖

```
F03 Tool Protocol（必须）
F06 FileReadState 缓存（必须）
chardet（已有依赖，编码检测）
无新增依赖
```

## 验收标准

### Write 工具验收标准

- [ ] `file_write.py` 文件在 `src/agent/tools/`
- [ ] `FILE_WRITE_PARAMETERS` 定义正确的 JSON Schema
- [ ] `execute_file_write()` 函数实现完整
  - [ ] 路径解析（绝对/相对）
  - [ ] 检查中断状态
  - [ ] 检查写权限
  - [ ] 检查磁盘空间
  - [ ] 自动创建父目录
  - [ ] 写入文件（UTF-8 编码）
  - [ ] 更新缓存（FileReadState）
  - [ ] Notebook 写入（.ipynb 文件）
- [ ] `validate_file_write_input()` 实现完整
  - [ ] file_path 非空校验
  - [ ] content 非空校验
  - [ ] 路径类型校验（不能是目录）
- [ ] `file_write_tool` 使用 `build_tool()` 创建
- [ ] 工具属性正确：
  - [ ] `name` = "write"
  - [ ] `is_read_only` = False
  - [ ] `is_concurrency_safe` = False
  - [ ] `get_summary` 返回完整路径摘要

### Edit 工具验收标准

- [ ] `file_edit.py` 文件在 `src/agent/tools/`
- [ ] `FILE_EDIT_PARAMETERS` 定义正确的 JSON Schema
- [ ] `execute_file_edit()` 函数实现完整
  - [ ] 路径解析（绝对/相对）
  - [ ] 检查中断状态
  - [ ] 检查文件存在性
  - [ ] 读取文件内容（带缓存）
  - [ ] 查找 old_string 匹配
  - [ ] 校验唯一性（replace_all=False 时）
  - [ ] 执行替换
  - [ ] 写入文件（UTF-8 编码）
  - [ ] 更新缓存（FileReadState）
- [ ] `validate_file_edit_input()` 实现完整
  - [ ] file_path 非空校验
  - [ ] old_string 非空校验
  - [ ] new_string 非空校验
  - [ ] 文件存在性校验
  - [ ] 路径类型校验（不能是目录）
  - [ ] old_string 存在性校验
  - [ ] old_string 唯一性校验（replace_all=False）
- [ ] `file_edit_tool` 使用 `build_tool()` 创建
- [ ] 工具属性正确：
  - [ ] `name` = "edit"
  - [ ] `is_read_only` = False
  - [ ] `is_concurrency_safe` = False
  - [ ] `get_summary` 返回完整路径摘要

### 共享逻辑验收标准

- [ ] `_resolve_path()` 实现正确
  - [ ] 绝对路径直接返回
  - [ ] 相对路径相对于 cwd 解析
- [ ] `_ensure_directory()` 实现正确
  - [ ] 父目录不存在时自动创建
  - [ ] 父目录存在时跳过
- [ ] `_check_write_permission()` 实现正确
  - [ ] 文件存在时检查文件权限
  - [ ] 文件不存在时检查目录权限
- [ ] `_check_disk_space()` 实现正确
  - [ ] 空间足够返回 None
  - [ ] 空间不足返回错误信息
  - [ ] Windows 跳过检查（不支持 statvfs）
- [ ] `_update_cache()` 实现正确
  - [ ] 更新 FileReadState 缓存
  - [ ] 包含内容和 mtime

### 测试验收标准

- [ ] Write 工具测试覆盖所有场景（≥9 个测试）
- [ ] Edit 工具测试覆盖所有场景（≥5 个测试）
- [ ] 输入校验测试覆盖所有场景（≥4 个测试）
- [ ] 总测试数 ≥ 18 个
- [ ] 所有测试通过
- [ ] `make check` 通过

### 文档验收标准

- [ ] `feature_list.json` 更新 F07 状态为 done
- [ ] `claude-progress.md` 记录本次改动
- [ ] `DEV_SYNC.md` 更新工作日志
- [ ] `LEARNING_NOTES.md` 添加相关学习笔记

## 面试可能问的问题

```
Q: 为什么 Write 和 Edit 要分开，而不是合并成一个工具？
A: 职责分离原则：
   1. Write 负责"整个文件"，Edit 负责"局部修改"
   2. 每个工具只做一件事，易于理解和测试
   3. 与 Claude Code 对齐，用户熟悉这种设计
   4. 如果合并，参数复杂，容易出错

Q: 为什么 Edit 的 old_string 必须唯一匹配？
A: 避免误改：
   1. 如果 old_string 匹配多个，Edit 不知道改哪个
   2. 强制唯一匹配，确保修改意图清晰
   3. 用户可以通过提供更精确的 old_string 来解决
   4. 如果确实需要替换所有，可以用 replace_all=True

Q: 为什么 Write 要先读后写（Read-before-Write）？
A: 安全机制：
   1. 确保模型理解文件内容后再写入
   2. 防止误覆盖重要文件
   3. 与 Claude Code 的设计一致
   4. 提高用户对模型操作的信任度

Q: 为什么写入后要更新缓存？
A: 性能优化：
   1. 写入后文件内容已知，更新缓存避免下次 Read 重新读取
   2. mtime 也已知，可以直接设置
   3. 减少磁盘 I/O，提高响应速度
   4. 保证缓存与磁盘内容一致

Q: 为什么 Write/Edit 不并发安全？
A: 数据完整性：
   1. 同时写入同一文件会导致内容混乱
   2. 串行执行更容易预测结果
   3. Agent 循环中很少需要同时写多个文件
   4. 通过 is_concurrency_safe=False 标记，让 ToolRegistry 确保串行执行

Q: 为什么固定 UTF-8 编码？
A: 简化实现：
   1. UTF-8 覆盖 99% 场景
   2. 避免编码检测的复杂性
   3. 如果原文件是 GBK，写入 UTF-8 后可能乱码
   4. 但编程助手通常创建新文件，不是修改旧文件
   5. 如果需要保持原编码，可以用 Edit 工具

Q: 为什么自动创建目录而不是报错？
A: 用户体验：
   1. 用户说"写入 src/utils/helper.py"，期望自动创建目录
   2. 减少交互成本，不需要先手动 mkdir
   3. Claude Code 也是这样做的
   4. 如果路径有误，后续 Read 会发现文件不存在

Q: 为什么不限制写入文件大小？
A: YAGNI 原则：
   1. 编程助手很少需要写入超大文件
   2. 如果限制大小，需要额外的确认逻辑
   3. 增加复杂度，但收益不大
   4. 如果需要限制，可以后续按需添加
```
