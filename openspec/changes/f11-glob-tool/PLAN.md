---
phase: F11
plan: glob-tool
type: feature
wave: 1
depends_on: []
files_modified:
  - src/agent/tools/glob.py
  - src/agent/tools/__init__.py
  - tests/test_glob.py
autonomous: false
requirements:
  - REQ-F11-01: 实现 Glob 工具，支持递归 glob 模式匹配文件路径
  - REQ-F11-02: 支持按修改时间排序（默认）和按路径排序
  - REQ-F11-03: 支持 max_results 限制返回数量
  - REQ-F11-04: 遵循现有工具架构模式（辅助函数→校验→执行→注册）
---

<objective>
实现 Glob 工具，让 Agent 能够按模式匹配文件路径。对齐 Claude Code 的 Glob 工具行为，使用 pathlib.Path.glob() 作为底层实现。

**交付物：**
- `src/agent/tools/glob.py` — Glob 工具实现
- `tests/test_glob.py` — 完整测试覆盖
- 更新 `src/agent/tools/__init__.py` 导出 glob_tool
</objective>

<read_first>
**必读文件（执行前必须阅读）：**
- `src/agent/tools/grep.py` — 同类工具实现，遵循相同的架构模式
- `src/agent/tools/base.py` — build_tool 工厂函数和 Tool Protocol
- `src/agent/core/types.py` — ToolResult, ValidationResult 类型定义
- `src/agent/core/context.py` — ToolUseContext 类型
- `openspec/changes/f11-glob-tool/design.md` — 设计决策和参数定义
</read_first>

<tasks>
## 1. 基础结构（Wave 1）

<task id="T1" wave="1">
<objective>创建 glob.py 文件，定义常量和辅助函数</objective>
<read_first>
- src/agent/tools/grep.py — 参考 _resolve_path() 实现
- src/agent/tools/base.py — 了解 build_tool 接口
</read_first>
<action>
1. 创建 `src/agent/tools/glob.py`
2. 定义常量 `DEFAULT_MAX_RESULTS = 100`
3. 实现 `_resolve_path(path: str, cwd: str) -> str` — 复用 grep.py 的路径解析逻辑
4. 实现 `_get_file_mtime(path: str) -> float` — 使用 `os.path.getmtime()` 获取文件修改时间
5. 实现 `_sort_results(paths: list[str], sort_by: str) -> list[str]` — 支持 "modified"（按修改时间降序）和 "path"（按路径字母序）
</action>
<verify>
- 文件存在且无语法错误
- 类型注解完整
- `_resolve_path` 处理绝对路径和相对路径
- `_sort_results` 对空列表不报错
</verify>
<acceptance_criteria>
- `src/agent/tools/glob.py` 存在
- `uv run python -c "from agent.tools.glob import _resolve_path, _sort_results, _get_file_mtime"` 成功
- `_resolve_path("src", "/project")` 返回 `/project/src`
- `_resolve_path("/abs", "/project")` 返回 `/abs`
- `_sort_results([], "modified")` 返回 `[]`
</acceptance_criteria>
</task>

## 2. 核心逻辑（Wave 1）

<task id="T2" wave="1" depends_on="T1">
<objective>实现 execute_glob() 核心执行函数</objective>
<read_first>
- src/agent/tools/grep.py — 参考 execute_grep() 的结构
- src/agent/tools/glob.py — T1 创建的辅助函数
- openspec/changes/f11-glob-tool/design.md — 输出格式定义
</read_first>
<action>
1. 实现 `execute_glob(input: dict[str, Any], context: ToolUseContext) -> ToolResult`
2. 逻辑流程：
   - 检查 context.abort_controller.is_aborted
   - 解析参数（pattern, path, max_results, sort_by）
   - 调用 `_resolve_path()` 解析路径
   - 使用 `pathlib.Path(abs_path).glob(pattern)` 执行匹配
   - 调用 `_sort_results()` 排序
   - 截断到 max_results
   - 格式化输出：每行一个路径 + 末尾总数
3. 错误处理：路径不存在、pattern 无效、权限错误
</action>
<verify>
- 函数签名完整
- 错误通过 ToolResult(is_error=True) 返回，不抛异常
- 输出格式：路径列表 + "(共 N 个文件)"
</verify>
<acceptance_criteria>
- `execute_glob({"pattern": "*.py"}, context)` 返回 ToolResult 且 is_error=False
- 输出包含 "(共 N 个文件)" 后缀
- `execute_glob({"pattern": "*.py", "max_results": 2}, context)` 返回不超过 2 个文件
- `execute_glob({"pattern": "*.py", "sort_by": "path"}, context)` 按字母序排列
- `execute_glob({"pattern": "*.py", "path": "/nonexistent"}, context)` 返回 is_error=True
</acceptance_criteria>
</task>

## 3. 输入校验（Wave 1）

<task id="T3" wave="1" depends_on="T1">
<objective>实现 validate_glob_input() 校验函数</objective>
<read_first>
- src/agent/tools/grep.py — 参考 validate_grep_input() 的校验模式
- src/agent/tools/glob.py — T1 创建的文件
</read_first>
<action>
1. 实现 `validate_glob_input(raw_input: dict[str, Any], context: ToolUseContext) -> ValidationResult`
2. 校验规则：
   - pattern 必须存在、是字符串、非空
   - path 如果提供，必须是非空字符串且路径存在
   - max_results 如果提供，必须是正整数
   - sort_by 如果提供，必须是 "modified" 或 "path"
</action>
<verify>
- 返回 ValidationResult.success() 或 ValidationResult.failure(msg)
- 校验顺序：pattern → path → max_results → sort_by
</verify>
<acceptance_criteria>
- `validate_glob_input({}, ctx)` 返回 failure（pattern 缺失）
- `validate_glob_input({"pattern": ""}, ctx)` 返回 failure（pattern 为空）
- `validate_glob_input({"pattern": "*.py"}, ctx)` 返回 success
- `validate_glob_input({"pattern": "*.py", "path": "/nonexistent"}, ctx)` 返回 failure
- `validate_glob_input({"pattern": "*.py", "max_results": -1}, ctx)` 返回 failure
- `validate_glob_input({"pattern": "*.py", "sort_by": "invalid"}, ctx)` 返回 failure
</acceptance_criteria>
</task>

## 4. 工具注册（Wave 2）

<task id="T4" wave="2" depends_on="T1,T2,T3">
<objective>定义参数 Schema 并注册 glob_tool</objective>
<read_first>
- src/agent/tools/grep.py — 参考 GREP_PARAMETERS 和 grep_tool 注册
- src/agent/tools/glob.py — T1-T3 创建的所有函数
- src/agent/tools/__init__.py — 了解导出模式
</read_first>
<action>
1. 定义 `GLOB_PARAMETERS` JSON Schema：
   ```python
   {
       "type": "object",
       "properties": {
           "pattern": {"type": "string", "description": "glob 模式，如 **/*.py"},
           "path": {"type": "string", "description": "搜索路径，默认当前工作目录"},
           "max_results": {"type": "integer", "description": "最大结果数，默认 100", "default": 100},
           "sort_by": {"type": "string", "enum": ["modified", "path"], "description": "排序方式，默认 modified", "default": "modified"},
       },
       "required": ["pattern"],
   }
   ```
2. 使用 `build_tool()` 注册 `glob_tool`，传入所有必要参数
3. 更新 `src/agent/tools/__init__.py`：
   - 添加 `from agent.tools.glob import glob_tool`
   - 在 `__all__` 中添加 `"glob_tool"`
</action>
<verify>
- `uv run python -c "from agent.tools import glob_tool; print(glob_tool.name)"` 输出 "glob"
- glob_tool.parameters 包含 pattern, path, max_results, sort_by
- glob_tool.is_read_only({}) 返回 True
- glob_tool.is_concurrency_safe({}) 返回 True
</verify>
<acceptance_criteria>
- `src/agent/tools/__init__.py` 导出 glob_tool
- `uv run python -c "from agent.tools import glob_tool"` 无错误
- glob_tool.name == "glob"
- glob_tool.description 包含 "glob" 或 "文件" 或 "模式"
- glob_tool.is_read_only({}) == True
- glob_tool.is_concurrency_safe({}) == True
</acceptance_criteria>
</task>

## 5. 测试（Wave 2）

<task id="T5" wave="2" depends_on="T4">
<objective>创建完整测试文件，覆盖正常路径和错误路径</objective>
<read_first>
- src/agent/tools/glob.py — 完整实现
- tests/ — 了解测试模式和 conftest.py 配置
- openspec/changes/f11-glob-tool/tasks.md — 测试场景列表
</read_first>
<action>
1. 创建 `tests/test_glob.py`
2. 测试辅助函数：
   - `_resolve_path` — 绝对路径、相对路径
   - `_sort_results` — 按修改时间、按路径、空列表
   - `_get_file_mtime` — 存在文件、不存在文件
3. 测试输入校验：
   - `validate_glob_input` — pattern 缺失/空/有效、path 不存在、max_results 无效、sort_by 无效
4. 测试核心执行：
   - 简单模式（`*.py`）
   - 递归模式（`**/*.py`）
   - 排序（`sort_by: "path"` vs `"modified"`）
   - 限制（`max_results: 2`）
5. 测试边界情况：
   - 空结果（不存在的模式）
   - 超大结果集（`max_results` 截断）
</action>
<verify>
- `uv run pytest tests/test_glob.py -v` 全部通过
- 测试覆盖：辅助函数、校验、执行、边界
</verify>
<acceptance_criteria>
- `uv run pytest tests/test_glob.py -v` 退出码 0
- 测试文件包含至少 10 个测试用例
- 覆盖 _resolve_path、_sort_results、validate_glob_input、execute_glob
- 覆盖正常路径和错误路径
</acceptance_criteria>
</task>

## 6. 集成验证（Wave 3）

<task id="T6" wave="3" depends_on="T5">
<objective>运行完整验证，确保不破坏现有功能</objective>
<read_first>
- src/agent/tools/__init__.py — 确认 glob_tool 已导出
- Makefile — 了解 check 命令
</read_first>
<action>
1. 运行 `uv run pytest tests/test_glob.py -v` — 新测试通过
2. 运行 `uv run mypy src/agent/tools/glob.py --strict` — 类型检查通过
3. 运行 `uv run make check` — 全量测试通过，无回归
</action>
<verify>
- 所有验证命令退出码 0
- 无类型错误
- 无现有测试失败
</verify>
<acceptance_criteria>
- `uv run pytest tests/test_glob.py -v` 退出码 0
- `uv run mypy src/agent/tools/glob.py --strict` 退出码 0
- `uv run make check` 退出码 0
</acceptance_criteria>
</task>
</tasks>

<verification>
1. `uv run pytest tests/test_glob.py -v` — 所有 Glob 测试通过
2. `uv run mypy src/agent/tools/glob.py --strict` — 无类型错误
3. `uv run make check` — 全量验证通过，无回归
4. 手动验证：`from agent.tools import glob_tool` 可导入
</verification>

<success_criteria>
- [ ] glob.py 实现完整，遵循 grep.py 架构模式
- [ ] 测试覆盖辅助函数、校验、执行、边界情况
- [ ] 类型注解完整（strict mode 通过）
- [ ] __init__.py 正确导出 glob_tool
- [ ] 全量测试无回归
- [ ] 输出格式对齐 design.md 定义
</success_criteria>

<must_haves>
<truths>
- glob_tool 使用 pathlib.Path.glob() 作为底层实现
- 支持 **/*.py 等递归 glob 模式
- 默认按修改时间排序（降序），可选按路径排序
- 默认 max_results=100
- 输出格式：每行一个路径 + 末尾 "(共 N 个文件)"
- is_read_only 返回 True
- is_concurrency_safe 返回 True
- validate_glob_input 校验 pattern、path、max_results、sort_by
- 错误通过 ToolResult(is_error=True) 返回，不抛异常
</truths>
<prohibitions>
- 不使用外部依赖（仅标准库 pathlib + os）
- 不实现文件内容搜索（那是 Grep 的职责）
- 不支持正则匹配（glob 模式足够）
- 不修改现有工具代码（仅新增 + 更新 __init__.py 导出）
</prohibitions>
</must_haves>

<artifacts>
## Artifacts this phase produces

**New files:**
- `src/agent/tools/glob.py` — Glob 工具实现模块
- `tests/test_glob.py` — Glob 工具测试文件

**Modified files:**
- `src/agent/tools/__init__.py` — 添加 glob_tool 导出

**New symbols:**
- `glob_tool` (ToolImpl instance) — Glob 工具实例
- `execute_glob()` — 核心执行函数
- `validate_glob_input()` — 输入校验函数
- `_resolve_path()` — 路径解析辅助函数
- `_get_file_mtime()` — 获取文件修改时间
- `_sort_results()` — 结果排序函数
- `GLOB_PARAMETERS` — JSON Schema 参数定义
- `DEFAULT_MAX_RESULTS` — 默认最大结果数常量
</artifacts>

---

*Phase: F11 — Glob Tool*
*Plan created: 2026-06-23*
