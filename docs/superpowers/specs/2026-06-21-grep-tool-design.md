# F08 Grep 工具设计文档

## 概述

F08 是一个文本搜索工具，用于在代码库中搜索匹配指定模式的内容。对齐 Claude Code 的 Grep 工具实现。

## 核心需求

- 内容搜索：在文件中查找匹配正则表达式的内容
- 文件过滤：只搜索特定类型的文件（glob 模式）
- 路径指定：支持在指定目录下搜索
- 结果控制：限制返回结果数量
- 大小写控制：支持大小写敏感/不敏感搜索
- 上下文显示：可选择显示匹配行周围的代码

## 设计决策

### 1. 底层实现：ripgrep 封装

**选择**：封装系统的 `rg`（ripgrep）命令

**理由**：
- 速度快：ripgrep 是 Rust 写的，比 grep 快 10 倍+
- 功能全：支持正则、文件过滤、忽略 .git 等
- 代码简单：只需构造命令和解析输出
- 对齐 Claude Code：Claude Code 的 Grep 也是用 ripgrep

**权衡**：
- 需要用户系统安装了 ripgrep
- 跨平台兼容性需要处理

### 2. 参数设计：平衡方案

**选择**：支持核心参数 + 常用参数，不支持高级参数

**参数列表**：
```python
{
    "pattern": str,         # 搜索模式（正则）- 必须
    "path": str,            # 搜索路径 - 可选，默认整个项目
    "include": str,         # 文件过滤（glob）- 可选
    "max_results": int,     # 最大结果数 - 可选，默认 100
    "case_sensitive": bool, # 大小写敏感 - 可选，默认 false
    "context_lines": int,   # 上下文行数 - 可选，默认 0
}
```

**理由**：
- 功能完整，覆盖 90% 使用场景
- 参数不多，学习成本低
- 代码量适中（~200 行）
- 展示设计权衡能力

### 3. 输出格式：简洁格式

**选择**：`文件名:行号:内容`

**示例**：
```
src/main.py:15:# TODO: implement this
src/utils.py:42:# TODO: fix bug
```

**理由**：
- 结果简洁，易于阅读
- 包含足够信息（文件、行号、内容）
- 对齐 Claude Code 的输出格式

### 4. 搜索范围：整个项目

**选择**：默认搜索整个项目目录

**理由**：
- 一次搜索找到所有结果
- 符合用户直觉
- 对齐 Claude Code 的行为

### 5. 文件过滤：glob 模式

**选择**：支持 glob 模式过滤（如 `*.py`、`*.ts`）

**理由**：
- 灵活：可以精确控制搜索哪些文件
- 简单：glob 模式易于理解
- 对齐 Claude Code 的参数设计

### 6. 结果数量：限制 100 条

**选择**：默认最多返回 100 条结果

**理由**：
- 避免信息过载
- 控制 token 消耗
- 提高响应速度

### 7. 大小写敏感：默认不敏感

**选择**：默认大小写不敏感，提供参数启用敏感

**理由**：
- 更常用：搜索 "todo" 能找到 "TODO"、"Todo"、"todo"
- 对齐 Claude Code 的行为
- 灵活：用户可以通过参数控制

### 8. 上下文显示：默认无上下文

**选择**：默认只显示匹配行，不显示周围代码

**理由**：
- 结果简洁
- 对齐 Claude Code 的默认行为
- 用户可以通过 context_lines 参数启用

### 9. 错误处理：检测并提示

**选择**：ripgrep 未安装时返回错误信息 + 安装指南

**理由**：
- 用户体验好：明确告知问题和解决方案
- 代码简单：不需要实现 fallback 逻辑
- 符合项目风格：错误信息要有上下文

## 技术细节

### 1. 核心函数

```python
def execute_grep(input: dict, context: ToolUseContext) -> ToolResult:
    """执行 grep 搜索

    Args:
        input: 工具输入参数
        context: 工具执行上下文

    Returns:
        ToolResult: 搜索结果
    """
    # 1. 检查 ripgrep 是否安装
    # 2. 解析路径（相对 → 绝对）
    # 3. 构造 rg 命令参数
    # 4. 执行 rg 命令
    # 5. 解析输出（文件名:行号:内容）
    # 6. 截断到 max_results
    # 7. 返回结果
```

### 2. 命令构造

```bash
rg \
  --line-number \
  --with-filename \
  --no-heading \
  --max-count 100 \
  --glob "*.py" \
  --case-insensitive \
  --context 2 \
  "TODO" \
  src/
```

### 3. 输出解析

```python
def parse_rg_output(output: str) -> list[dict]:
    """解析 ripgrep 输出

    Args:
        output: ripgrep 的原始输出

    Returns:
        解析后的结果列表
    """
    results = []
    for line in output.strip().split("\n"):
        if not line:
            continue
        # 格式：文件名:行号:内容
        parts = line.split(":", 2)
        if len(parts) == 3:
            results.append({
                "file": parts[0],
                "line": int(parts[1]),
                "content": parts[2],
            })
    return results
```

### 4. 行为标记

```python
is_read_only: True         # 只读操作
is_concurrency_safe: True  # 可并行执行
is_destructive: False      # 非破坏性
```

## 测试场景

### 1. 基本搜索
- 搜索简单的文本模式
- 验证输出格式正确

### 2. 正则搜索
- 使用正则表达式搜索
- 验证正则语法正确处理

### 3. 文件过滤
- 只搜索特定类型的文件（如 `*.py`）
- 验证过滤逻辑正确

### 4. 路径指定
- 在指定目录下搜索
- 验证路径解析正确

### 5. 大小写敏感
- 测试 case_sensitive 参数
- 验证大小写敏感/不敏感行为

### 6. 上下文显示
- 测试 context_lines 参数
- 验证上下文显示正确

### 7. 结果限制
- 测试 max_results 参数
- 验证结果截断正确

### 8. 错误情况
- ripgrep 未安装：返回错误信息 + 安装指南
- 搜索路径不存在：返回错误信息
- 正则表达式无效：返回错误信息
- 无匹配结果：返回 "No matches found"

## 验收标准

1. **功能完整**：支持所有定义的参数
2. **错误处理**：所有错误情况都有明确的错误信息
3. **测试覆盖**：所有测试场景都有对应的测试用例
4. **类型注解**：所有函数签名都有完整类型注解
5. **文档字符串**：所有公开接口都有 docstring
6. **代码风格**：符合项目代码风格（注释、命名等）
7. **通过验证**：`make check` 通过

## 文件结构

```
src/agent/tools/grep.py       # 主实现文件
tests/tools/test_grep.py      # 测试文件
specs/F08-grep-tool.md        # spec 文件（从本文档生成）
```

## 依赖

- `subprocess`：执行 ripgrep 命令
- `shutil`：检测 ripgrep 是否安装
- `os`：路径处理
- `re`：正则表达式验证（可选）

## 风险和缓解

### 1. ripgrep 未安装
- **风险**：用户系统没有安装 ripgrep
- **缓解**：检测并返回详细的安装指南

### 2. 跨平台兼容性
- **风险**：Windows/Mac/Linux 的 ripgrep 命令可能有差异
- **缓解**：使用 `shutil.which` 检测，使用标准参数

### 3. 性能问题
- **风险**：搜索大型代码库可能很慢
- **缓解**：限制结果数量，使用 ripgrep 的高性能

### 4. 正则表达式复杂
- **风险**：用户输入复杂的正则表达式可能导致性能问题
- **缓解**：ripgrep 本身有优化，我们不做额外处理

## 后续扩展

### 1. 高级参数（可选）
- `exclude`：排除模式
- `fixed_strings`：纯文本搜索
- `word_boundary`：单词边界匹配

### 2. 输出格式（可选）
- JSON 格式输出
- 上下文高亮

### 3. 缓存（可选）
- 缓存最近的搜索结果
- 增量搜索

## 参考

- Claude Code Grep 工具文档
- ripgrep 官方文档：https://github.com/BurntSushi/ripgrep
- 项目现有工具实现：file_read.py、file_write.py、bash.py
