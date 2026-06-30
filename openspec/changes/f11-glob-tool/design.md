## Context

Agent 已有 Grep 工具（内容搜索），但缺少文件发现能力。用户经常需要按模式查找文件，如"项目里有哪些测试文件"、"找到所有配置文件"。Claude Code 的 Glob 工具是 Phase 2 基础功能。

现有工具模式（Grep、Bash、FileRead 等）已建立统一的架构：
- 辅助函数（纯函数，易测试）
- 输入校验（validate_input → ValidationResult）
- 核心执行（execute_fn → ToolResult）
- 参数定义（JSON Schema）
- 工具注册（build_tool）

## Goals / Non-Goals

**Goals:**
- 实现 Glob 工具，支持 `**/*.py`、`src/**/*.ts` 等递归 glob 模式
- 返回匹配的文件路径列表
- 支持按修改时间排序（默认）和按路径排序
- 对齐 Claude Code 的 Glob 工具行为

**Non-Goals:**
- 不支持文件内容搜索（那是 Grep 的职责）
- 不支持正则匹配（glob 模式足够）
- 不需要高性能优化（标准库 pathlib 性能够用）

## Decisions

### 1. 实现方式：pathlib.Path.glob()

**选择**: 使用 Python 标准库 `pathlib.Path.glob()`

**理由**:
- 无外部依赖（不像 Grep 需要 ripgrep）
- 跨平台（Windows/Mac/Linux 都能用）
- 标准库，稳定可靠
- 性能对于文件列表场景足够

**备选方案**:
- A: glob 模块 + os.walk — 需要自己处理 `**` 递归，代码更多
- B: 调用外部命令 find — Windows 兼容性差

### 2. 参数设计

```python
{
    "pattern": str,      # 必须，如 "**/*.py"
    "path": str,         # 可选，默认 cwd
    "max_results": int,  # 可选，默认 100
    "sort_by": str,      # 可选，默认 "modified"，可选 "path"
}
```

**理由**:
- pattern 是必须的，LLM 需要明确指定要找什么文件
- path 可选，默认当前工作目录
- max_results 防止结果过多（大项目可能有几千个文件）
- sort_by 提供灵活性，默认按修改时间（最常用）

### 3. 输出格式

```
src/agent/core/model.py
src/agent/core/loop.py
src/agent/tools/base.py
...
(共 42 个文件)
```

**理由**:
- 纯路径列表，简洁清晰
- 末尾显示总数，方便 LLM 理解规模
- 每行一个路径，方便后续处理（如传给 FileRead）

### 4. 排序策略

- 按修改时间（默认）：最新修改的文件排在前面，符合"最近在改什么"的直觉
- 按路径排序：字母顺序，方便查找特定文件

## Risks / Trade-offs

**[风险] 大目录性能** → pathlib.glob() 在文件很多时可能慢。缓解：限制 max_results=100，避免返回过多结果。

**[风险] 符号链接循环** → pathlib 会自动处理符号链接，不会无限循环。无需额外处理。

**[权衡] 功能简单** → Glob 工具功能单一，没有复杂的过滤逻辑。这是好事：简单可靠，容易测试。如果需要更复杂的过滤，可以让 LLM 用 Grep 搜索文件名。

## Migration Plan

无迁移需求。新增工具，不影响现有功能。

## Open Questions

无。
