"""History Formatter 测试"""

from agent.context.history_formatter import format_history


class TestFormatHistory:
    """format_history() 测试"""

    def test_empty_messages(self) -> None:
        """空消息列表返回空字符串"""
        assert format_history([]) == ""

    def test_user_text_preserved(self) -> None:
        """用户文本消息正常保留"""
        messages = [{"role": "user", "content": "What is the API_KEY?"}]
        result = format_history(messages)
        assert "What is the API_KEY?" in result

    def test_assistant_text_preserved(self) -> None:
        """助手文本消息正常保留"""
        messages = [{"role": "assistant", "content": [{"type": "text", "text": "The API_KEY is sk-xxx."}]}]
        result = format_history(messages)
        assert "The API_KEY is sk-xxx." in result

    def test_tool_result_read_summarized(self) -> None:
        """成功的 read tool_result 转为摘要行（短内容保留预览）"""
        messages = [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "read", "input": {"file_path": "/a.py"}}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "line1\nline2\nline3\nline4\nline5"}
            ]},
        ]
        result = format_history(messages)
        assert "read" in result
        assert "/a.py" in result
        # 短内容保留预览
        assert "[tool_result]" in result

    def test_tool_result_error_preserved(self) -> None:
        """失败的 tool_result 保留完整错误信息"""
        messages = [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "read", "input": {"file_path": "/missing.py"}}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "FileNotFoundError: /missing.py not found"}
            ]},
        ]
        result = format_history(messages)
        assert "FileNotFoundError" in result

    def test_tool_result_grep_summarized(self) -> None:
        """grep tool_result 转为摘要行"""
        messages = [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "grep", "input": {"pattern": "TODO", "path": "/src"}}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "file1.py:10: TODO fix this\nfile2.py:20: TODO fix that"}
            ]},
        ]
        result = format_history(messages)
        assert "grep" in result
        assert "TODO" in result

    def test_long_preview_truncated(self) -> None:
        """超长预览被截断并加 ...(truncated)"""
        long_content = "x" * 500
        messages = [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "read", "input": {"file_path": "/big.py"}}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": long_content}
            ]},
        ]
        result = format_history(messages)
        assert "truncated" in result.lower()

    def test_string_content_tool_result(self) -> None:
        """字符串格式的 tool_result 也能处理"""
        messages = [
            {"role": "user", "content": "What is X?"},
        ]
        result = format_history(messages)
        assert "What is X?" in result

    def test_max_tokens_respected(self) -> None:
        """超出 max_tokens 时从前面截断"""
        messages = []
        for i in range(20):
            messages.append({"role": "user", "content": f"Message {i} " + "x" * 200})
        result = format_history(messages, max_tokens=200)
        # 应该保留最近的消息
        assert len(result) > 0
