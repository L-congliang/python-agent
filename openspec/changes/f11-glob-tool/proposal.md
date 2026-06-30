## Why

Agent 目前缺少文件发现能力。Grep 可以搜索文件内容，但无法按模式匹配文件路径。当用户问"项目里有哪些测试文件"或"找到所有配置文件"时，Agent 只能用 Grep 间接查找，不够精确。Glob 是 Claude Code 的基础工具之一，属于 Phase 2（重要）功能。

## What Changes

- 新增 `tools/glob.py`：实现 Glob 工具，使用 `pathlib.Path.glob()` 进行模式匹配
- 支持 `**/*.py`、`src/**/*.ts` 等 glob 模式
- 返回匹配的文件路径列表，按修改时间排序（默认）或按路径排序
- 更新 `tools/__init__.py` 导出 glob_tool
- 创建 spec 文件 `specs/F11-glob.md`

## Capabilities

### New Capabilities
- `glob-file-search`: 按模式匹配查找文件路径，支持递归 glob 模式、排序选项、结果数量限制

### Modified Capabilities
（无）

## Impact

- 新增文件：`src/agent/tools/glob.py`
- 修改文件：`src/agent/tools/__init__.py`（导出 glob_tool）
- 新增测试：`tests/test_glob.py`
- 新增 spec：`specs/F11-glob.md`
- 无外部依赖：使用 Python 标准库 pathlib
- 无破坏性变更
