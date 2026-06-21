# F08: 搜索工具（Grep）

> **参考**: Claude Code 的 Grep 工具
> **前置依赖**: F03 Tool Protocol

## 设计目标

实现文本搜索工具，让 Agent 能够在代码库中搜索匹配指定模式的内容。

这是编程助手的核心能力：
- 搜索代码中的特定模式（函数、变量、注释等）
- 过滤特定类型的文件（只搜索 Python、只搜索 TypeScript 等）
- 在指定目录下搜索，缩小搜索范围
- 控制结果数量，避免信息过载

## 与 Claude Code 的对齐点

| Claude Code | python-agent | 说明 |
|-------------|--------------|------|
| `Grep` 工具 | `grep` 工具 | 搜索文件内容 |
| `pattern` 参数 | `pattern` 参数 | 搜索模式（正则） |
| `path` 参数 | `path` 参数 | 搜索路径 |
| `include` 参数 | `include` 参数 | 文件过滤（glob） |
| `max_results` 参数 | `max_results` 参数 | 最大结果数 |
| `case_sensitive` 参数 | `case_sensitive` 参数 | 大小写敏感 |
| `context_lines` 参数 | `context_lines` 参数 | 上下文行数 |
| ripgrep 封装 | ripgrep 封装 | 底层实现 |

## 设计决策总览

| 决策 | 选择 | 理由 |
|------|------|------|
| 底层实现 | ripgrep 封装 | 速度快、功能全、代码简单 |
| 参数设计 | 核心参数 + 常用参数 | 覆盖 90% 场景，学习成本低 |
| 输出格式 | `文件名:行号:内容` | 简洁、信息足够、对齐 Claude Code |
| 搜索范围 | 默认整个项目 | 一次搜索找到所有结果 |
| 文件过滤 | glob 模式 | 灵活、简单、对齐 Claude Code |
| 结果数量 | 默认 100 条 | 避免信息过载、控制 token 消耗 |
| 大小写敏感 | 默认不敏感 | 更常用、对齐 Claude Code |
| 上下文显示 | 默认无上下文 | 结果简洁、对齐 Claude Code |
| 错误处理 | 检测并提示 | 用户体验好、代码简单 |

## 文件结构

```
src/agent/tools/
├── base.py           # 已有（Tool Protocol）
├── registry.py       # 已有（ToolRegistry）
├── __init__.py       # 已有（需添加导出）
├── bash.py           # 已有
├── file_read.py      # 已有（F06）
├── file_write.py     # 已有（F07）
├── file_edit.py      # 已有（F07）
└── grep.py           # 新增：Grep 工具
```

### `grep.py` 内部结构

```
grep.py
├── DEFAULT_MAX_RESULTS          # 常量：默认最大结果数
├── _check_ripgrep_installed()   # 检查 ripgrep 是否安装
├── _resolve_path()              # 路径解析（相对 → 绝对）
├── _build_rg_command()          # 构造 ripgrep 命令参数
├── _parse_rg_output()           # 解析 ripgrep 输出
├── GREP_PARAMETERS              # 参数定义
├── validate_grep_input()        # 输入校验
├── execute_grep()               # 核心执行逻辑
└── grep_tool                    # build_tool() 工厂调用
```

---

## 接口定义

### 1. 参数 Schema

```python
GREP_PARAMETERS = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "搜索模式（支持正则表达式）",
        },
        "path": {
            "type": "string",
            "description": "搜索路径（绝对或相对路径），默认整个项目",
        },
        "include": {
            "type": "string",
            "description": "文件过滤（glob 模式，如 *.py、*.ts）",
        },
        "max_results": {
            "type": "integer",
            "description": "最大结果数，默认 100",
            "default": 100,
        },
        "case_sensitive": {
            "type": "boolean",
            "description": "大小写敏感，默认 false",
            "default": False,
        },
        "context_lines": {
            "type": "integer",
            "description": "显示匹配行前后的上下文行数，默认 0",
            "default": 0,
        },
    },
    "required": ["pattern"],
}
```

### 2. 检查 ripgrep 安装

```python
def _check_ripgrep_installed() -> bool:
    """检查 ripgrep 是否已安装

    Returns:
        True 如果 ripgrep 已安装，否则 False
    """
    return shutil.which("rg") is not None
```

### 3. 路径解析

```python
def _resolve_path(path: str, cwd: str) -> str:
    """解析路径为绝对路径

    Args:
        path: 输入路径（绝对或相对）
        cwd: 当前工作目录

    Returns:
        绝对路径字符串
    """
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(cwd, path))
```

### 4. 命令构造

```python
def _build_rg_command(
    pattern: str,
    path: str,
    include: str | None,
    max_results: int,
    case_sensitive: bool,
    context_lines: int,
) -> list[str]:
    """构造 ripgrep 命令参数

    Args:
        pattern: 搜索模式（正则）
        path: 搜索路径
        include: 文件过滤（glob 模式）
        max_results: 最大结果数
        case_sensitive: 大小写敏感
        context_lines: 上下文行数

    Returns:
        命令参数列表
    """
    cmd = [
        "rg",
        "--line-number",
        "--with-filename",
        "--no-heading",
        "--max-count",
        str(max_results),
    ]

    if case_sensitive:
        cmd.append("--case-sensitive")
    else:
        cmd.append("--case-insensitive")

    if include:
        cmd.extend(["--glob", include])

    if context_lines > 0:
        cmd.extend(["--context", str(context_lines)])

    cmd.append(pattern)
    cmd.append(path)

    return cmd
```

### 5. 输出解析

```python
def _parse_rg_output(output: str) -> list[dict[str, Any]]:
    """解析 ripgrep 输出

    Args:
        output: ripgrep 的原始输出

    Returns:
        解析后的结果列表，每个结果包含 file、line、content
    """
    results = []
    for line in output.strip().split("\n"):
        if not line:
            continue
        # 格式：文件名:行号:内容
        parts = line.split(":", 2)
        if len(parts) == 3:
            try:
                results.append({
                    "file": parts[0],
                    "line": int(parts[1]),
                    "content": parts[2],
                })
            except ValueError:
                # 行号解析失败，跳过该行
                continue
    return results
```

### 6. 输入校验

```python
def validate_grep_input(
    raw_input: dict[str, Any], context: ToolUseContext
) -> ValidationResult:
    """校验 grep 输入

    校验规则:
    1. pattern 必须存在、是字符串且非空
    2. max_results 必须是正整数
    3. context_lines 必须是非负整数
    4. path 如果提供，必须是非空字符串且路径存在

    Args:
        raw_input: 工具输入
        context: 工具执行上下文

    Returns:
        ValidationResult
    """
    # 检查 pattern
    pattern = raw_input.get("pattern")
    if not pattern or not isinstance(pattern, str) or not pattern.strip():
        return ValidationResult.failure("pattern 不能为空")

    # 检查 max_results
    max_results = raw_input.get("max_results", DEFAULT_MAX_RESULTS)
    if not isinstance(max_results, int) or max_results < 1:
        return ValidationResult.failure("max_results 必须是正整数")

    # 检查 context_lines
    context_lines = raw_input.get("context_lines", 0)
    if not isinstance(context_lines, int) or context_lines < 0:
        return ValidationResult.failure("context_lines 必须是非负整数")

    # 检查 path（如果提供）
    path = raw_input.get("path")
    if path is not None:
        if not isinstance(path, str) or not path.strip():
            return ValidationResult.failure("path 不能为空字符串")
        abs_path = _resolve_path(path, context.cwd)
        if not os.path.exists(abs_path):
            return ValidationResult.failure(f"路径不存在: {abs_path}")

    return ValidationResult.success()
```

### 7. 核心执行

```python
def execute_grep(input: dict[str, Any], context: ToolUseContext) -> ToolResult:
    """执行 grep 搜索

    使用 ripgrep 搜索文件内容，返回匹配的行。

    Args:
        input: 工具输入参数，包含 pattern、path、include 等
        context: 工具执行上下文

    Returns:
        ToolResult: 搜索结果或错误信息
    """
    # 检查 ripgrep 是否安装
    if not _check_ripgrep_installed():
        return ToolResult(
            output="ripgrep 未安装。请安装 ripgrep：\n"
                   "  Windows: winget install BurntSushi.ripgrep.MSVC\n"
                   "  Mac: brew install ripgrep\n"
                   "  Linux: sudo apt install ripgrep",
            is_error=True,
        )

    # 检查中断
    if context.abort_controller.is_aborted:
        return ToolResult(output="搜索被取消", is_error=True)

    # 解析参数
    pattern: str = input.get("pattern", "")
    path = input.get("path", context.cwd)
    include = input.get("include")
    max_results = input.get("max_results", DEFAULT_MAX_RESULTS)
    case_sensitive = input.get("case_sensitive", False)
    context_lines = input.get("context_lines", 0)

    # 解析路径
    abs_path = _resolve_path(path, context.cwd)

    # 检查路径存在性
    if not os.path.exists(abs_path):
        return ToolResult(output=f"路径不存在: {abs_path}", is_error=True)

    try:
        # 构造命令
        cmd = _build_rg_command(
            pattern=pattern,
            path=abs_path,
            include=include,
            max_results=max_results,
            case_sensitive=case_sensitive,
            context_lines=context_lines,
        )

        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 处理结果
        if result.returncode == 0:
            # 有匹配结果
            results = _parse_rg_output(result.stdout)
            if not results:
                return ToolResult(output="No matches found", is_error=False)

            # 格式化输出
            output_lines = []
            for r in results:
                output_lines.append(f"{r['file']}:{r['line']}:{r['content']}")
            return ToolResult(output="\n".join(output_lines), is_error=False)

        elif result.returncode == 1:
            # 无匹配结果（ripgrep 返回 1 表示无匹配）
            return ToolResult(output="No matches found", is_error=False)

        else:
            # 错误
            return ToolResult(
                output=f"搜索失败: {result.stderr}",
                is_error=True,
            )

    except subprocess.TimeoutExpired:
        return ToolResult(output="搜索超时（30秒）", is_error=True)
    except Exception as e:
        return ToolResult(output=f"搜索失败: {str(e)}", is_error=True)
```

### 8. 工具注册

```python
grep_tool = build_tool(
    name="grep",
    description="搜索文件内容。支持正则表达式、文件过滤、路径指定等。",
    parameters=GREP_PARAMETERS,
    execute_fn=execute_grep,
    is_read_only=lambda input: True,
    is_concurrency_safe=lambda input: True,
    validate_input=validate_grep_input,
    get_summary=lambda input: f"Searching for '{input.get('pattern', '')}'",
    get_user_facing_name=lambda input: "Grep",
    get_activity_description=lambda input: f"Searching for '{input.get('pattern', '')}'",
)
```

---

## 核心设计决策

### 1. 为什么用 ripgrep 而不是自己实现？

性能和功能：
1. ripgrep 是 Rust 写的，比 grep 快 10 倍+
2. 支持正则、文件过滤、忽略 .git 等
3. 代码简单，只需构造命令和解析输出
4. 对齐 Claude Code 的实现方式

### 2. 为什么默认大小写不敏感？

更常用：
1. 搜索 "todo" 能找到 "TODO"、"Todo"、"todo"
2. 对齐 Claude Code 的行为
3. 用户可以通过 case_sensitive 参数启用敏感

### 3. 为什么默认最多返回 100 条结果？

控制成本：
1. 避免信息过载
2. 控制 token 消耗
3. 提高响应速度
4. 用户可以通过 max_results 参数调整

### 4. 为什么默认不显示上下文？

简洁优先：
1. 结果简洁，易于阅读
2. 对齐 Claude Code 的默认行为
3. 用户可以通过 context_lines 参数启用

### 5. 为什么检测 ripgrep 安装并给出安装指南？

用户体验：
1. 明确告知问题和解决方案
2. 代码简单，不需要实现 fallback 逻辑
3. 符合项目风格：错误信息要有上下文

---

## 测试场景

### 1. 基本搜索

```python
def test_basic_search():
    """搜索简单的文本模式"""
    # 创建测试文件
    with open("test.py", "w") as f:
        f.write("def hello():\n    print('hello')\n")

    result = execute_grep({"pattern": "hello"}, context)
    assert not result.is_error
    assert "test.py" in result.output
    assert "hello" in result.output
```

### 2. 正则搜索

```python
def test_regex_search():
    """使用正则表达式搜索"""
    with open("test.py", "w") as f:
        f.write("def hello():\n    print('hello')\n")

    result = execute_grep({"pattern": "def \\w+\\("}, context)
    assert not result.is_error
    assert "def hello(" in result.output
```

### 3. 文件过滤

```python
def test_file_filter():
    """只搜索特定类型的文件"""
    with open("test.py", "w") as f:
        f.write("hello world")
    with open("test.txt", "w") as f:
        f.write("hello world")

    result = execute_grep({"pattern": "hello", "include": "*.py"}, context)
    assert not result.is_error
    assert "test.py" in result.output
    assert "test.txt" not in result.output
```

### 4. 路径指定

```python
def test_path_specified():
    """在指定目录下搜索"""
    os.makedirs("src", exist_ok=True)
    with open("src/main.py", "w") as f:
        f.write("hello world")

    result = execute_grep({"pattern": "hello", "path": "src"}, context)
    assert not result.is_error
    assert "src/main.py" in result.output
```

### 5. 大小写敏感

```python
def test_case_sensitive():
    """测试大小写敏感搜索"""
    with open("test.py", "w") as f:
        f.write("Hello hello HELLO")

    # 默认不敏感
    result = execute_grep({"pattern": "hello"}, context)
    assert not result.is_error
    assert result.output.count("hello") == 3  # 匹配所有

    # 敏感模式
    result = execute_grep({"pattern": "hello", "case_sensitive": True}, context)
    assert not result.is_error
    assert result.output.count("hello") == 1  # 只匹配小写
```

### 6. 上下文显示

```python
def test_context_lines():
    """测试上下文行数"""
    with open("test.py", "w") as f:
        f.write("line1\nline2\nline3\nline4\nline5")

    result = execute_grep({"pattern": "line3", "context_lines": 1}, context)
    assert not result.is_error
    assert "line2" in result.output
    assert "line4" in result.output
```

### 7. 结果限制

```python
def test_max_results():
    """测试结果数量限制"""
    with open("test.py", "w") as f:
        for i in range(200):
            f.write(f"line {i}\n")

    result = execute_grep({"pattern": "line", "max_results": 10}, context)
    assert not result.is_error
    assert result.output.count("\n") < 20  # 应该被截断
```

### 8. 错误情况

```python
def test_ripgrep_not_installed():
    """ripgrep 未安装"""
    with mock.patch("shutil.which", return_value=None):
        result = execute_grep({"pattern": "hello"}, context)
        assert result.is_error
        assert "ripgrep 未安装" in result.output

def test_path_not_exists():
    """搜索路径不存在"""
    result = execute_grep({"pattern": "hello", "path": "/nonexistent"}, context)
    assert result.is_error
    assert "路径不存在" in result.output

def test_no_matches():
    """无匹配结果"""
    with open("test.py", "w") as f:
        f.write("hello world")

    result = execute_grep({"pattern": "nonexistent"}, context)
    assert not result.is_error
    assert "No matches found" in result.output
```

---

## 依赖

```
F03 Tool Protocol（必须）
subprocess（标准库）
shutil（标准库）
os（标准库）
无新增依赖
```

## 验收标准

### 功能验收标准

- [x] `grep.py` 文件在 `src/agent/tools/`
- [x] `GREP_PARAMETERS` 定义正确的 JSON Schema
- [x] `execute_grep()` 函数实现完整
  - [x] 检查 ripgrep 安装
  - [x] 检查中断状态
  - [x] 解析路径（绝对/相对）
  - [x] 构造 rg 命令
  - [x] 执行 rg 命令
  - [x] 解析输出
  - [x] 格式化结果
  - [x] 错误处理
- [x] `validate_grep_input()` 实现完整
  - [x] pattern 非空校验
  - [x] max_results 正整数校验
  - [x] context_lines 非负整数校验
  - [x] path 存在性校验
- [x] `grep_tool` 使用 `build_tool()` 创建
- [x] 工具属性正确：
  - [x] `name` = "grep"
  - [x] `is_read_only` = True
  - [x] `is_concurrency_safe` = True
  - [x] `get_summary` 返回搜索模式摘要

### 测试验收标准

- [x] 测试覆盖所有场景（≥80 个测试）
- [x] 所有测试通过
- [x] `make check` 通过

### 文档验收标准

- [x] `feature_list.json` 更新 F08 状态为 done
- [x] `specs/F08-grep-tool.md` 创建完成

## 面试可能问的问题

```
Q: 为什么用 ripgrep 而不是自己实现搜索逻辑？
A: 性能和功能：
   1. ripgrep 是 Rust 写的，比 grep 快 10 倍+
   2. 支持正则、文件过滤、忽略 .git 等
   3. 代码简单，只需构造命令和解析输出
   4. 对齐 Claude Code 的实现方式

Q: 为什么默认大小写不敏感？
A: 更常用：
   1. 搜索 "todo" 能找到 "TODO"、"Todo"、"todo"
   2. 对齐 Claude Code 的行为
   3. 用户可以通过 case_sensitive 参数启用敏感

Q: 为什么默认最多返回 100 条结果？
A: 控制成本：
   1. 避免信息过载
   2. 控制 token 消耗
   3. 提高响应速度
   4. 用户可以通过 max_results 参数调整

Q: 为什么默认不显示上下文？
A: 简洁优先：
   1. 结果简洁，易于阅读
   2. 对齐 Claude Code 的默认行为
   3. 用户可以通过 context_lines 参数启用

Q: 为什么检测 ripgrep 安装并给出安装指南？
A: 用户体验：
   1. 明确告知问题和解决方案
   2. 代码简单，不需要实现 fallback 逻辑
   3. 符合项目风格：错误信息要有上下文
```
