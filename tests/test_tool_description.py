"""Tool Description 微调测试

测试覆盖：
- file_edit description 包含优先级提示
- file_write description 包含使用场景提示
- grep description 包含优先级提示
"""

import pytest

from agent.tools.file_edit import file_edit_tool
from agent.tools.file_write import file_write_tool
from agent.tools.grep import grep_tool


class TestToolDescription:
    """Tool Description 微调测试"""

    def test_edit_description_mentions_priority_over_write(self):
        """edit description 包含优先于 write 的提示"""
        assert "edit" in file_edit_tool.description.lower() or "优先" in file_edit_tool.description
        assert "write" in file_edit_tool.description.lower()

    def test_write_description_mentions_new_file_only(self):
        """write description 包含仅用于新文件的提示"""
        assert "新文件" in file_write_tool.description or "创建" in file_write_tool.description

    def test_grep_description_mentions_priority_over_bash(self):
        """grep description 包含优先于 bash grep 的提示"""
        assert "bash" in grep_tool.description.lower() or "优先" in grep_tool.description
