## 1. 基础结构

- [ ] 1.1 创建 `src/agent/tools/glob.py` 文件
- [ ] 1.2 定义常量（DEFAULT_MAX_RESULTS=100）
- [ ] 1.3 实现 `_resolve_path()` 辅助函数

## 2. 核心逻辑

- [ ] 2.1 实现 `_get_file_mtime()` 获取文件修改时间
- [ ] 2.2 实现 `_sort_results()` 排序函数（按修改时间/按路径）
- [ ] 2.3 实现 `execute_glob()` 核心执行函数

## 3. 输入校验

- [ ] 3.1 实现 `validate_glob_input()` 校验函数
- [ ] 3.2 校验 pattern（必须存在、是字符串、非空）
- [ ] 3.3 校验 path（如果提供，必须存在）
- [ ] 3.4 校验 max_results（必须是正整数）

## 4. 工具注册

- [ ] 4.1 定义 GLOB_PARAMETERS（JSON Schema）
- [ ] 4.2 使用 build_tool() 注册 glob_tool
- [ ] 4.3 更新 `src/agent/tools/__init__.py` 导出 glob_tool

## 5. 测试

- [ ] 5.1 创建 `tests/test_glob.py`
- [ ] 5.2 测试辅助函数（_resolve_path, _sort_results）
- [ ] 5.3 测试输入校验（pattern、path、max_results）
- [ ] 5.4 测试核心执行（简单模式、递归模式、排序、限制）
- [ ] 5.5 测试边界情况（空结果、超大结果集）

## 6. 验证

- [ ] 6.1 运行 `uv run pytest tests/test_glob.py -v`
- [ ] 6.2 运行 `uv run mypy src/agent/tools/glob.py --strict`
- [ ] 6.3 运行 `uv run make check` 确保全量测试通过
