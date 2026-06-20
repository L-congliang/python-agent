# F06: 文件读取工具

> **参考**: Claude Code 的 Read 工具
> **前置依赖**: F03 Tool Protocol

## 设计目标

实现文件读取工具，让 Agent 能够读取文件内容。

这是编程助手的核心能力：
- 读取源代码文件，理解项目结构
- 读取配置文件，了解项目配置
- 读取 Jupyter Notebook，分析数据分析代码
- 结合行号，精确定位代码位置

## 与 Claude Code 的对齐点

| Claude Code | python-agent | 说明 |
|-------------|--------------|------|
| `Read` 工具 | `Read` 工具 | 工具名称对齐 |
| `file_path` 参数 | `file_path` 参数 | 文件路径 |
| `offset` 参数 | `offset` 参数 | 起始行号（从 1 开始） |
| `limit` 参数 | `limit` 参数 | 读取行数 |
| 支持图片/PDF | 暂不实现 | mimo 不支持多模态，后续按需扩展 |
| 支持 Notebook | 支持 | .ipynb 格式解析 |
| 行号输出 | 支持 | cat -n 风格 |
| FileReadState 缓存 | 支持 | mtime 检查防过期 |

## 设计决策总览

| 决策 | 选择 | 理由 |
|------|------|------|
| 文件类型 | 文本 + Notebook | 覆盖核心场景，mimo 不支持多模态故跳过图片 |
| 行范围 | offset + limit | 大文件精确读取，节省 token |
| 输出格式 | 带行号 | 模型可直接引用行号，提高精确度 |
| 截断上限 | 2000 行，保留头部 | 与 Claude Code 对齐，头部含 imports/类定义 |
| 编码处理 | UTF-8 优先 + chardet | 覆盖中文项目常见 GBK 编码 |
| 缓存策略 | FileReadState + mtime | 避免重复 I/O，mtime 检查防过期 |
| 代码组织 | 单文件 | Notebook 逻辑仅 20-30 行，YAGNI |

## 文件结构

```
src/agent/tools/
├── base.py           # 已有（Tool Protocol）
├── registry.py       # 已有（ToolRegistry）
├── __init__.py       # 已有（需添加 file_read 导出）
├── bash.py           # 已有
└── file_read.py      # 新增：文件读取工具实现
```

### `file_read.py` 内部结构

```
file_read.py
├── MAX_LINES = 2000                    # 截断上限
├── _detect_encoding()                  # 编码检测（UTF-8 优先 + chardet）
├── _resolve_path()                     # 路径解析（相对 → 绝对）
├── _read_file_content()                # 读取文件原始内容
├── _read_file_with_cache()             # 带缓存的读取（FileReadState + mtime）
├── _format_with_line_numbers()         # 添加行号
├── _truncate_lines()                   # 截断（保留头部）
├── _read_text_file()                   # 读取文本文件（主流程）
├── _read_notebook()                    # 读取 Jupyter Notebook
├── validate_file_read_input()          # 输入校验
├── execute_file_read()                 # 核心执行逻辑
└── file_read_tool                      # build_tool() 工厂调用
```

---

## 接口定义

### 1. 工具参数 Schema

```python
FILE_READ_PARAMETERS = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "要读取的文件路径（绝对路径或相对于 cwd 的路径）",
        },
        "offset": {
            "type": "integer",
            "description": "起始行号（从 1 开始），默认 1",
            "default": 1,
        },
        "limit": {
            "type": "integer",
            "description": "读取的行数，默认 2000",
            "default": 2000,
        },
    },
    "required": ["file_path"],
}
```

### 2. 路径解析（`_resolve_path`）

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

### 3. 编码检测（`_detect_encoding`）

```python
def _detect_encoding(file_path: str) -> str:
    """检测文件编码

    策略:
    1. 先尝试 UTF-8 读取（快速，覆盖 90% 场景）
    2. UTF-8 失败则用 chardet 检测前 8KB
    3. chardet 置信度 < 0.5 时 fallback 到 latin-1（万能编码，不会报错）

    Args:
        file_path: 文件路径

    Returns:
        编码名称（如 "utf-8", "gbk", "latin-1"）
    """
```

### 4. 文件读取（`_read_file_content`）

```python
def _read_file_content(file_path: str) -> str:
    """读取文件内容

    流程:
    1. 检测编码（_detect_encoding）
    2. 用检测到的编码打开文件
    3. 读取全部内容
    4. 返回解码后的字符串

    Args:
        file_path: 文件绝对路径

    Returns:
        文件内容字符串

    Raises:
        UnicodeDecodeError: 无法解码文件
        OSError: 文件读取失败
    """
```

### 5. 带缓存的读取（`_read_file_with_cache`）

```python
def _read_file_with_cache(file_path: str, context: ToolUseContext) -> str:
    """读取文件，带 FileReadState 缓存 + mtime 检查

    流程:
    1. 获取文件当前 mtime（os.path.getmtime）
    2. 检查 FileReadState 缓存
    3. 缓存命中且 mtime 相同 → 返回缓存内容
    4. 缓存未命中或 mtime 不同 → 读取文件，更新缓存

    缓存格式:
    - FileReadState 存储 (content: str, mtime: float) 元组
    - 需要修改 context.py 的 FileReadState 类型

    Args:
        file_path: 文件绝对路径
        context: 工具执行上下文

    Returns:
        文件内容字符串
    """
```

### 6. 行号格式化（`_format_with_line_numbers`）

```python
def _format_with_line_numbers(content: str, start_line: int = 1) -> str:
    """添加行号，类似 cat -n

    格式示例（start_line=1）:
        1 │ import os
        2 │ import sys
        3 │
        4 │ def main():
        5 │     print("hello")

    格式示例（start_line=5，即 offset=5）:
        5 │ def calculate(x, y):
        6 │     return x + y

    关键：行号对应原始文件行号，不是输出的相对位置。
    offset=5 时，第一行显示 "5 │" 而不是 "1 │"。

    行号宽度自动适配:
    - 1-9 行:     "    1 │ "
    - 10-99 行:   "   10 │ "
    - 100-999 行: "  100 │ "

    Args:
        content: 原始内容
        start_line: 起始行号（默认 1，对应 offset 参数）

    Returns:
        带行号的内容
    """
```

### 7. 截断（`_truncate_lines`）

```python
MAX_LINES = 2000

def _truncate_lines(content: str, max_lines: int = MAX_LINES) -> str:
    """截断过长内容，保留头部

    与 bash 工具的区别:
    - bash 保留尾部（命令输出有用信息在最后）
    - file_read 保留头部（imports、类定义、函数签名在开头）

    截断时添加提示行:
    "... (truncated, showing first 2000 of 5000 lines)"

    Args:
        content: 原始内容
        max_lines: 最大行数（默认 2000）

    Returns:
        截断后的内容
    """
```

### 8. Notebook 读取（`_read_notebook`）

```python
def _read_notebook(file_path: str, offset: int, limit: int) -> str:
    """读取 Jupyter Notebook 并格式化为可读文本

    Notebook JSON 结构:
    {
        "cells": [
            {
                "cell_type": "code" | "markdown",
                "source": ["line1\n", "line2\n"],
                "outputs": [
                    {"text": ["output line\n"], "output_type": "..."}
                ]
            }
        ]
    }

    格式化输出:
    --- Cell 1 (markdown) ---
    # My Notebook
    This is a description.

    --- Cell 2 (code) ---
    import pandas as pd
    df = pd.read_csv("data.csv")

    --- Cell 2 Output ---
       col1  col2
    0     1     2

    --- Cell 3 (code) ---
    df.head()

    处理要点:
    - 每个 cell 显示类型和编号
    - code cell 的 outputs 也显示（仅文本输出）
    - 二进制输出（图片 base64）跳过
    - offset/limit 按格式化后的行计算
    - 空 cells 跳过

    Args:
        file_path: Notebook 文件路径
        offset: 起始行号
        limit: 读取行数

    Returns:
        格式化后的内容（已应用行号和截断）
    """
```

### 9. 输入校验（`validate_file_read_input`）

```python
def validate_file_read_input(raw_input: dict, context: ToolUseContext) -> ValidationResult:
    """校验文件读取输入

    校验规则:
    1. file_path 必须存在且非空字符串
    2. file_path 必须是字符串类型
    3. offset 如果指定，必须是正整数
    4. limit 如果指定，必须是正整数
    5. 解析后的路径必须存在
    6. 解析后的路径必须是文件（不能是目录）

    Args:
        raw_input: 工具输入
        context: 工具执行上下文

    Returns:
        ValidationResult
    """
```

### 10. 核心执行（`execute_file_read`）

```python
def execute_file_read(input: dict, context: ToolUseContext) -> ToolResult:
    """读取文件内容

    流程:
    1. 解析参数（file_path, offset, limit）
    2. 解析路径（_resolve_path，相对 → 绝对）
    3. 检查中断状态
    4. 判断文件类型（.ipynb → Notebook，其他 → 文本）
    5. 文本文件: _read_file_with_cache → 截断 → 添加行号
    6. Notebook: _read_notebook（内部处理截断和行号）
    7. 返回 ToolResult

    Args:
        input: {"file_path": "src/main.py", "offset": 1, "limit": 2000}
        context: 工具执行上下文

    Returns:
        ToolResult:
        - output: 带行号的文件内容
        - is_error: 读取失败时为 True
    """
```

### 11. 工具注册

```python
file_read_tool = build_tool(
    name="read",
    description="读取文件内容。支持文本文件和 Jupyter Notebook。可指定行范围（offset/limit）。",
    parameters=FILE_READ_PARAMETERS,
    execute_fn=execute_file_read,
    is_read_only=lambda input: True,       # 只读，不修改文件
    is_concurrency_safe=lambda input: True, # 只读，可以并行
    validate_input=validate_file_read_input,
    get_summary=lambda input: f"Reading {os.path.basename(input.get('file_path', ''))}",
    get_user_facing_name=lambda input: "Read",
    get_activity_description=lambda input: f"Reading {input.get('file_path', '')}",
)
```

---

## 对 context.py 的修改

当前 `FileReadState` 只存储 `str`，需要扩展为存储 `(str, float)` 元组以支持 mtime 检查。

```python
# 修改前
@dataclass
class FileReadState:
    _cache: dict[str, str] = field(default_factory=dict)

    def get(self, path: str) -> str | None: ...
    def set(self, path: str, content: str) -> None: ...
    def has(self, path: str) -> bool: ...

# 修改后
@dataclass
class FileReadState:
    _cache: dict[str, tuple[str, float]] = field(default_factory=dict)

    def get(self, path: str) -> tuple[str, float] | None:
        """获取缓存的 (内容, mtime)，未缓存返回 None"""
        return self._cache.get(path)

    def set(self, path: str, content: str, mtime: float) -> None:
        """设置文件内容缓存（内容 + mtime）"""
        self._cache[path] = (content, mtime)

    def has(self, path: str) -> bool:
        """检查路径是否已缓存"""
        return path in self._cache
```

---

## 核心设计决策

### 1. 为什么输出带行号？

行号让模型可以精确引用代码位置：
- "第 15 行有 bug" 而不是 "在 `def main()` 下面第三行"
- 配合 Edit 工具（F07）时可以直接指定行号
- 与 Claude Code 的 Read 工具行为一致

### 2. 为什么保留头部而不是尾部？

| 工具 | 保留方向 | 理由 |
|------|---------|------|
| Bash | 尾部 | 命令输出有用信息在最后（测试结果、错误信息） |
| Read | 头部 | 文件结构在开头（imports、类定义、函数签名） |

模型理解文件时，通常需要先看头部了解结构，再按需读取其他部分。

### 3. 为什么用 chardet 而不是固定编码列表？

| 方案 | 优点 | 缺点 |
|------|------|------|
| 仅 UTF-8 | 最简单 | 中文项目大量 GBK 文件会失败 |
| UTF-8 + GBK + Latin-1 | 不引入依赖 | 遇到日文/韩文编码失败 |
| chardet 自动检测 | 覆盖所有编码 | 需要额外依赖 |

选择 chardet：中文项目经常遇到 GBK 编码（Windows 默认），chardet 能自动检测，准确率 >95%。

### 4. 为什么缓存需要 mtime 检查？

在一次对话中：
1. 模型读取 `main.py`（缓存）
2. 模型用 Bash 工具修改了 `main.py`
3. 模型再次读取 `main.py`（需要新内容）

如果不检查 mtime，第 3 步会返回缓存的旧内容。mtime 检查确保文件被修改后重新读取。

### 5. Notebook 输出格式为什么用分隔线？

```
--- Cell 1 (markdown) ---
内容
--- Cell 2 (code) ---
内容
```

分隔线清晰区分不同 cell，比纯 JSON 更易读。模型能快速定位到感兴趣的 cell。

---

## 测试场景

### 1. 基本文本文件读取

```python
def test_basic_text_read():
    """读取简单的文本文件"""
    result = file_read_tool.execute(
        {"file_path": "test.txt"},
        context,
    )
    assert not result.is_error
    assert "内容" in result.output
```

### 2. 带行号输出

```python
def test_line_numbers():
    """输出包含行号"""
    result = file_read_tool.execute(
        {"file_path": "test.txt"},
        context,
    )
    assert "│" in result.output
    assert "1 " in result.output
```

### 3. offset + limit 读取

```python
def test_offset_limit():
    """指定行范围读取"""
    result = file_read_tool.execute(
        {"file_path": "test.txt", "offset": 5, "limit": 10},
        context,
    )
    # 验证只读取了第 5-14 行
    assert "5 │" in result.output
    assert "14 │" in result.output
```

### 4. 文件不存在

```python
def test_file_not_found():
    """文件不存在时返回错误"""
    result = file_read_tool.execute(
        {"file_path": "/nonexistent/file.txt"},
        context,
    )
    assert result.is_error
    assert "不存在" in result.output
```

### 5. 路径是目录

```python
def test_path_is_directory():
    """路径是目录时返回错误"""
    result = file_read_tool.execute(
        {"file_path": "/tmp"},
        context,
    )
    assert result.is_error
    assert "目录" in result.output
```

### 6. Notebook 读取

```python
def test_notebook_read():
    """读取 Jupyter Notebook"""
    # 创建临时 .ipynb 文件
    notebook = {
        "cells": [
            {"cell_type": "markdown", "source": ["# Title"]},
            {"cell_type": "code", "source": ["print('hello')"], "outputs": []},
        ]
    }
    # 写入临时文件
    result = file_read_tool.execute(
        {"file_path": "test.ipynb"},
        context,
    )
    assert not result.is_error
    assert "Cell 1" in result.output
    assert "markdown" in result.output
    assert "Cell 2" in result.output
    assert "code" in result.output
    assert "print('hello')" in result.output
```

### 7. 相对路径解析

```python
def test_relative_path():
    """相对路径相对于 cwd 解析"""
    context.cwd = "/tmp"
    result = file_read_tool.execute(
        {"file_path": "test.txt"},
        context,
    )
    # 验证解析为 /tmp/test.txt
```

### 8. 编码检测（GBK）

```python
def test_gbk_encoding():
    """读取 GBK 编码的中文文件"""
    # 创建 GBK 编码的临时文件
    content = "你好世界".encode("gbk")
    with open("test_gbk.txt", "wb") as f:
        f.write(content)

    result = file_read_tool.execute(
        {"file_path": "test_gbk.txt"},
        context,
    )
    assert not result.is_error
    assert "你好世界" in result.output
```

### 9. 缓存命中

```python
def test_cache_hit():
    """第二次读取同一文件使用缓存"""
    result1 = file_read_tool.execute({"file_path": "test.txt"}, context)
    result2 = file_read_tool.execute({"file_path": "test.txt"}, context)
    assert result1.output == result2.output
```

### 10. 缓存过期（mtime 变化）

```python
def test_cache_invalidation():
    """文件修改后缓存失效"""
    result1 = file_read_tool.execute({"file_path": "test.txt"}, context)

    # 修改文件
    with open("test.txt", "w") as f:
        f.write("new content")
    # 等待一小段时间确保 mtime 变化
    import time; time.sleep(0.01)

    result2 = file_read_tool.execute({"file_path": "test.txt"}, context)
    assert "new content" in result2.output
```

### 11. 大文件截断

```python
def test_large_file_truncation():
    """超过 2000 行时截断，保留头部"""
    # 创建一个 3000 行的文件
    content = "\n".join(f"line {i}" for i in range(1, 3001))
    with open("large.txt", "w") as f:
        f.write(content)

    result = file_read_tool.execute(
        {"file_path": "large.txt"},
        context,
    )
    assert "truncated" in result.output
    assert "line 1" in result.output      # 头部保留
    assert "line 2000" in result.output    # 头部保留
    assert "line 2001" not in result.output  # 尾部截断
```

### 12. 输入校验

```python
def test_validate_empty_path():
    """空路径校验"""
    result = file_read_tool.validate_input({"file_path": ""}, context)
    assert not result.is_valid

def test_validate_invalid_offset():
    """无效 offset 校验"""
    result = file_read_tool.validate_input(
        {"file_path": "test.txt", "offset": -1},
        context,
    )
    assert not result.is_valid
```

### 13. 中断支持

```python
def test_abort():
    """中断文件读取"""
    context.abort_controller.abort()
    result = file_read_tool.execute(
        {"file_path": "test.txt"},
        context,
    )
    assert result.is_error
    assert "取消" in result.output
```

### 14. 工具属性

```python
def test_tool_properties():
    """工具属性正确"""
    assert file_read_tool.name == "read"
    assert "读取" in file_read_tool.description or "read" in file_read_tool.description.lower()
    assert "file_path" in file_read_tool.parameters["properties"]
    assert file_read_tool.is_read_only({})
    assert file_read_tool.is_concurrency_safe({})
```

---

## 依赖

```
F03 Tool Protocol（必须）
chardet（新增依赖，编码检测）
```

## 验收标准

- [ ] `file_read.py` 文件在 `src/agent/tools/`
- [ ] `FILE_READ_PARAMETERS` 定义正确的 JSON Schema
- [ ] `execute_file_read()` 函数实现完整
  - [ ] 路径解析（绝对/相对）
  - [ ] 文件存在性检查
  - [ ] Notebook 类型检测（.ipynb）
  - [ ] 带缓存的文件读取（FileReadState + mtime）
  - [ ] 编码检测（UTF-8 优先 + chardet）
  - [ ] 行号格式化（cat -n 风格）
  - [ ] 截断处理（保留头部 2000 行）
  - [ ] 中断状态检查
- [ ] `_read_notebook()` 实现完整
  - [ ] JSON 解析
  - [ ] Cell 格式化（类型、编号）
  - [ ] Output 显示（仅文本）
  - [ ] offset/limit 支持
- [ ] `validate_file_read_input()` 实现完整
  - [ ] file_path 非空校验
  - [ ] offset/limit 正整数校验
  - [ ] 文件存在性校验
  - [ ] 路径类型校验（不能是目录）
- [ ] `file_read_tool` 使用 `build_tool()` 创建
- [ ] 工具属性正确：
  - [ ] `name` = "read"
  - [ ] `is_read_only` = True
  - [ ] `is_concurrency_safe` = True
  - [ ] `get_summary` 返回文件名摘要
- [ ] `context.py` 的 `FileReadState` 修改支持 mtime
- [ ] `__init__.py` 添加 `file_read_tool` 导出
- [ ] `requirements.txt` 或 `pyproject.toml` 添加 `chardet` 依赖
- [ ] 测试覆盖所有场景（≥14 个测试）
- [ ] `make check` 通过

## 面试可能问的问题

```
Q: 为什么文件读取要带行号？
A: 行号让模型可以精确引用代码位置。
   没有行号时，模型只能说"在 def main() 下面第三行"，不精确。
   有行号时，模型可以直接说"第 15 行"，配合 Edit 工具精准修改。
   这与 Claude Code 的 Read 工具行为一致。

Q: 为什么截断保留头部而不是尾部？
A: 不同工具的截断策略不同：
   - Bash 保留尾部：命令输出有用信息在最后（测试结果、错误信息）
   - Read 保留头部：文件结构在开头（imports、类定义、函数签名）
   模型理解文件时，通常需要先看头部了解结构。

Q: 为什么用 chardet 而不是固定编码？
A: 中文项目经常遇到 GBK 编码（Windows 默认）。
   只支持 UTF-8 会导致大量文件读取失败。
   固定编码列表（UTF-8 + GBK + Latin-1）覆盖 99% 场景，
   但遇到日文/韩文编码会失败。
   chardet 自动检测准确率 >95%，一次依赖解决所有编码问题。

Q: FileReadState 缓存怎么防止过期？
A: 每次读取文件时，先获取文件的 mtime（修改时间）。
   如果 mtime 与缓存时相同，说明文件没变，用缓存。
   如果 mtime 不同，说明文件被修改了，重新读取。
   os.path.getmtime() 耗时约 0.001ms，可以忽略。

Q: Notebook 的 offset/limit 是按 cell 还是按行？
A: 按格式化后的行计算。
   Notebook 先被格式化为可读文本（包含 cell 分隔线、内容、输出），
   然后对格式化后的内容应用 offset/limit。
   这样行为与文本文件一致，模型不需要区分文件类型。

Q: 为什么不支持图片和 PDF？
A: 两个原因：
   1. mimo v2.5 pro 大概率不支持多模态输入，返回 base64 图片模型也看不懂
   2. PDF 需要额外依赖（PyMuPDF），且编程助手中读 PDF 场景较少
   按 YAGNI 原则，后续按需扩展。
```
