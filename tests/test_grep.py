"""Grep 工具测试 - 基础结构验证"""

from __future__ import annotations

import os
from unittest.mock import patch

from agent.tools.grep import (
    _check_ripgrep_installed,
    _resolve_path,
    GREP_PARAMETERS,
    DEFAULT_MAX_RESULTS,
)


# ============================================================
# 导入和基础结构验证
# ============================================================


class TestImports:
    """验证所有导入正确"""

    def test_import_check_ripgrep_installed(self):
        """_check_ripgrep_installed 可以导入"""
        assert callable(_check_ripgrep_installed)

    def test_import_resolve_path(self):
        """_resolve_path 可以导入"""
        assert callable(_resolve_path)

    def test_import_grep_parameters(self):
        """GREP_PARAMETERS 可以导入"""
        assert isinstance(GREP_PARAMETERS, dict)

    def test_import_default_max_results(self):
        """DEFAULT_MAX_RESULTS 可以导入"""
        assert isinstance(DEFAULT_MAX_RESULTS, int)


# ============================================================
# _check_ripgrep_installed 测试
# ============================================================


class TestCheckRipgrepInstalled:
    """ripgrep 安装检测测试"""

    @patch("shutil.which", return_value="/usr/bin/rg")
    def test_returns_true_when_installed(self, mock_which):
        """rg 存在时返回 True"""
        assert _check_ripgrep_installed() is True

    @patch("shutil.which", return_value=None)
    def test_returns_false_when_not_installed(self, mock_which):
        """rg 不存在时返回 False"""
        assert _check_ripgrep_installed() is False


# ============================================================
# _resolve_path 测试
# ============================================================


class TestResolvePath:
    """路径解析测试"""

    def test_absolute_path_unchanged(self):
        """绝对路径不变"""
        result = _resolve_path("/tmp/test", "/home/user")
        assert result == "/tmp/test"

    def test_relative_path_resolved(self):
        """相对路径基于 cwd 解析"""
        result = _resolve_path("src/main.py", "/home/user/project")
        assert result == os.path.abspath("/home/user/project/src/main.py")

    def test_empty_path_resolved(self):
        """空路径解析为 cwd"""
        result = _resolve_path("", "/home/user/project")
        assert result == os.path.abspath("/home/user/project")

    def test_dot_path_resolved(self):
        """当前目录路径解析"""
        result = _resolve_path(".", "/home/user/project")
        assert result == os.path.abspath("/home/user/project")


# ============================================================
# GREP_PARAMETERS 测试
# ============================================================


class TestGrepParameters:
    """参数定义测试"""

    def test_type_is_object(self):
        """参数 schema 类型为 object"""
        assert GREP_PARAMETERS["type"] == "object"

    def test_required_fields(self):
        """pattern 是必填字段"""
        assert "pattern" in GREP_PARAMETERS["required"]

    def test_pattern_property(self):
        """pattern 属性定义正确"""
        props = GREP_PARAMETERS["properties"]
        assert "pattern" in props
        assert props["pattern"]["type"] == "string"

    def test_path_property(self):
        """path 属性定义正确"""
        props = GREP_PARAMETERS["properties"]
        assert "path" in props
        assert props["path"]["type"] == "string"

    def test_include_property(self):
        """include 属性定义正确"""
        props = GREP_PARAMETERS["properties"]
        assert "include" in props
        assert props["include"]["type"] == "string"

    def test_max_results_property(self):
        """max_results 属性定义正确"""
        props = GREP_PARAMETERS["properties"]
        assert "max_results" in props
        assert props["max_results"]["type"] == "integer"
        assert props["max_results"]["default"] == DEFAULT_MAX_RESULTS

    def test_case_sensitive_property(self):
        """case_sensitive 属性定义正确"""
        props = GREP_PARAMETERS["properties"]
        assert "case_sensitive" in props
        assert props["case_sensitive"]["type"] == "boolean"
        assert props["case_sensitive"]["default"] is False

    def test_context_lines_property(self):
        """context_lines 属性定义正确"""
        props = GREP_PARAMETERS["properties"]
        assert "context_lines" in props
        assert props["context_lines"]["type"] == "integer"
        assert props["context_lines"]["default"] == 0

    def test_all_expected_properties_present(self):
        """所有预期属性都存在"""
        expected = {"pattern", "path", "include", "max_results", "case_sensitive", "context_lines"}
        actual = set(GREP_PARAMETERS["properties"].keys())
        assert expected == actual

    def test_default_max_results_value(self):
        """默认最大结果数为 100"""
        assert DEFAULT_MAX_RESULTS == 100
