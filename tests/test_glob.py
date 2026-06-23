"""Glob 工具测试 - 文件发现功能验证"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

from agent.core.context import AbortController, ToolUseContext
from agent.core.types import ValidationResult
from agent.tools.glob import (
    _resolve_path,
    _get_file_mtime,
    _sort_results,
    execute_glob,
    validate_glob_input,
    GLOB_PARAMETERS,
    DEFAULT_MAX_RESULTS,
    glob_tool,
)


# ============================================================
# 测试辅助
# ============================================================


def _make_context(cwd: str | None = None, aborted: bool = False) -> ToolUseContext:
    """创建测试用的 ToolUseContext"""
    ctx = MagicMock(spec=ToolUseContext)
    ctx.cwd = cwd or os.getcwd()
    ctx.abort_controller = MagicMock(spec=AbortController)
    ctx.abort_controller.is_aborted = aborted
    return ctx


# ============================================================
# 导入和基础结构验证
# ============================================================


class TestImports:
    """验证所有导入正确"""

    def test_import_resolve_path(self):
        """_resolve_path 可以导入"""
        assert callable(_resolve_path)

    def test_import_get_file_mtime(self):
        """_get_file_mtime 可以导入"""
        assert callable(_get_file_mtime)

    def test_import_sort_results(self):
        """_sort_results 可以导入"""
        assert callable(_sort_results)

    def test_import_execute_glob(self):
        """execute_glob 可以导入"""
        assert callable(execute_glob)

    def test_import_validate_glob_input(self):
        """validate_glob_input 可以导入"""
        assert callable(validate_glob_input)

    def test_import_glob_parameters(self):
        """GLOB_PARAMETERS 可以导入"""
        assert isinstance(GLOB_PARAMETERS, dict)

    def test_import_default_max_results(self):
        """DEFAULT_MAX_RESULTS 可以导入"""
        assert DEFAULT_MAX_RESULTS == 100


# ============================================================
# _resolve_path 测试
# ============================================================


class TestResolvePath:
    """路径解析测试"""

    def test_absolute_path_unchanged(self):
        """绝对路径不变"""
        result = _resolve_path("/absolute/path", "/cwd")
        assert result == "/absolute/path"

    def test_relative_path_resolved(self):
        """相对路径拼接 cwd"""
        result = _resolve_path("relative", "/cwd")
        assert os.path.isabs(result)
        assert result.endswith(os.path.join("cwd", "relative"))

    def test_dot_path(self, tmp_path):
        """当前目录"""
        result = _resolve_path(".", str(tmp_path))
        assert result == str(tmp_path)


# ============================================================
# _get_file_mtime 测试
# ============================================================


class TestGetFileMtime:
    """文件修改时间测试"""

    def test_existing_file(self, tmp_path):
        """存在的文件返回修改时间"""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        mtime = _get_file_mtime(str(f))
        assert mtime > 0

    def test_nonexistent_file(self):
        """不存在的文件返回 0.0"""
        mtime = _get_file_mtime("/nonexistent/file.txt")
        assert mtime == 0.0


# ============================================================
# _sort_results 测试
# ============================================================


class TestSortResults:
    """排序函数测试"""

    def test_empty_list(self):
        """空列表返回空列表"""
        assert _sort_results([], "modified") == []
        assert _sort_results([], "path") == []

    def test_sort_by_path(self):
        """按路径排序"""
        paths = ["/b/file.txt", "/a/file.txt", "/c/file.txt"]
        result = _sort_results(paths, "path")
        assert result == ["/a/file.txt", "/b/file.txt", "/c/file.txt"]

    def test_sort_by_modified(self, tmp_path):
        """按修改时间排序（降序）"""
        f1 = tmp_path / "old.txt"
        f1.write_text("old")
        f2 = tmp_path / "new.txt"
        f2.write_text("new")
        # 用固定时间戳，不依赖 sleep
        os.utime(str(f1), (1000, 1000))
        os.utime(str(f2), (2000, 2000))

        result = _sort_results([str(f1), str(f2)], "modified")
        assert result[0] == str(f2)  # 最新的在前


# ============================================================
# validate_glob_input 测试
# ============================================================


class TestValidateGlobInput:
    """输入校验测试"""

    def test_missing_pattern(self):
        """pattern 缺失返回 failure"""
        result = validate_glob_input({}, _make_context())
        assert not result.is_valid

    def test_empty_pattern(self):
        """pattern 为空返回 failure"""
        result = validate_glob_input({"pattern": ""}, _make_context())
        assert not result.is_valid

    def test_valid_pattern(self):
        """有效 pattern 返回 success"""
        result = validate_glob_input({"pattern": "*.py"}, _make_context())
        assert result.is_valid

    def test_nonexistent_path(self):
        """不存在的 path 返回 failure"""
        result = validate_glob_input(
            {"pattern": "*.py", "path": "/nonexistent"}, _make_context()
        )
        assert not result.is_valid

    def test_invalid_max_results(self):
        """无效 max_results 返回 failure"""
        result = validate_glob_input(
            {"pattern": "*.py", "max_results": -1}, _make_context()
        )
        assert not result.is_valid

    def test_invalid_sort_by(self):
        """无效 sort_by 返回 failure"""
        result = validate_glob_input(
            {"pattern": "*.py", "sort_by": "invalid"}, _make_context()
        )
        assert not result.is_valid

    def test_valid_path(self, tmp_path):
        """有效 path 返回 success"""
        result = validate_glob_input(
            {"pattern": "*.py", "path": str(tmp_path)}, _make_context()
        )
        assert result.is_valid


# ============================================================
# execute_glob 测试
# ============================================================


class TestExecuteGlob:
    """核心执行函数测试"""

    def test_simple_pattern(self, tmp_path):
        """简单模式匹配"""
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.py").write_text("b")
        (tmp_path / "c.txt").write_text("c")

        ctx = _make_context(cwd=str(tmp_path))
        result = execute_glob({"pattern": "*.py"}, ctx)
        assert not result.is_error
        assert "a.py" in result.output
        assert "b.py" in result.output
        assert "c.txt" not in result.output
        assert "共 2 个文件" in result.output

    def test_recursive_pattern(self, tmp_path):
        """递归模式匹配"""
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("deep")
        (tmp_path / "root.py").write_text("root")

        ctx = _make_context(cwd=str(tmp_path))
        result = execute_glob({"pattern": "**/*.py"}, ctx)
        assert not result.is_error
        assert "deep.py" in result.output
        assert "root.py" in result.output

    def test_max_results_limit(self, tmp_path):
        """max_results 限制返回数量"""
        for i in range(5):
            (tmp_path / f"f{i}.py").write_text(str(i))

        ctx = _make_context(cwd=str(tmp_path))
        result = execute_glob({"pattern": "*.py", "max_results": 2}, ctx)
        assert not result.is_error
        assert "共 5 个文件" in result.output
        # 过滤掉总数行和空行，只计算文件路径行
        lines = [l for l in result.output.strip().split("\n") if l and not l.startswith("(")]
        assert len(lines) == 2

    def test_sort_by_path(self, tmp_path):
        """按路径排序"""
        (tmp_path / "b.py").write_text("b")
        (tmp_path / "a.py").write_text("a")

        ctx = _make_context(cwd=str(tmp_path))
        result = execute_glob({"pattern": "*.py", "sort_by": "path"}, ctx)
        assert not result.is_error
        lines = [l for l in result.output.strip().split("\n") if not l.startswith("\n(共")]
        assert lines[0].endswith("a.py")
        assert lines[1].endswith("b.py")

    def test_empty_result(self, tmp_path):
        """空结果"""
        ctx = _make_context(cwd=str(tmp_path))
        result = execute_glob({"pattern": "*.xyz"}, ctx)
        assert not result.is_error
        assert result.output == "No files found"

    def test_nonexistent_path(self):
        """不存在的路径返回错误"""
        ctx = _make_context()
        result = execute_glob({"pattern": "*.py", "path": "/nonexistent"}, ctx)
        assert result.is_error
        assert "不存在" in result.output

    def test_aborted(self, tmp_path):
        """中断检查"""
        ctx = _make_context(cwd=str(tmp_path), aborted=True)
        result = execute_glob({"pattern": "*.py"}, ctx)
        assert result.is_error


# ============================================================
# glob_tool 注册测试
# ============================================================


class TestGlobToolRegistration:
    """工具注册验证"""

    def test_tool_name(self):
        """工具名称为 glob"""
        assert glob_tool.name == "glob"

    def test_tool_description(self):
        """工具描述包含关键词"""
        assert "glob" in glob_tool.description.lower() or "模式" in glob_tool.description

    def test_is_read_only(self):
        """工具标记为只读"""
        assert glob_tool.is_read_only({}) is True

    def test_is_concurrency_safe(self):
        """工具标记为并发安全"""
        assert glob_tool.is_concurrency_safe({}) is True

    def test_parameters_schema(self):
        """参数 schema 包含必要字段"""
        props = GLOB_PARAMETERS["properties"]
        assert "pattern" in props
        assert "path" in props
        assert "max_results" in props
        assert "sort_by" in props
        assert "pattern" in GLOB_PARAMETERS["required"]
