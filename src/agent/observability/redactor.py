"""敏感信息脱敏器 - 自动替换 API key、token 等敏感信息

设计决策:
- 为什么用正则匹配？
  简单高效，不需要外部依赖。
  敏感信息通常有固定模式（sk-xxx, Bearer xxx 等）。

- 为什么是替换而不是删除？
  保留上下文，方便调试。
  替换为 <redacted> 明确表示"这里有敏感信息"。
"""

from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger("agent.observability.redactor")


class Redactor:
    """敏感信息脱敏器

    自动检测并替换 API key、token、secret 等敏感信息。

    使用方式:
        redactor = Redactor()
        safe_text = redactor.redact("api_key: sk-abc123xyz")
        # 结果: "api_key: <redacted>"
    """

    # 脱敏规则：(正则表达式, 替换模板)
    PATTERNS: list[tuple[str, str]] = [
        # API key 前缀（sk-, key-, token-, secret-）
        (
            r'(api[_-]?key|token|secret|password)["\s:=]+["\']?([a-zA-Z0-9_\-]{20,})',
            r'\1: "<redacted>"',
        ),
        # Bearer token
        (
            r'Bearer\s+[a-zA-Z0-9._\-]+',
            'Bearer <redacted>',
        ),
        # OpenAI style key (sk-...)
        (
            r'sk-[a-zA-Z0-9]{20,}',
            '<redacted>',
        ),
        # 环境变量中的敏感信息
        (
            r'((?:API|SECRET|TOKEN|PASSWORD|KEY)[_A-Z]*)=([^\s]+)',
            r'\1=<redacted>',
        ),
    ]

    def __init__(self) -> None:
        """初始化脱敏器"""
        # 预编译正则表达式，提高性能
        self._compiled_patterns = [
            (re.compile(pattern), replacement)
            for pattern, replacement in self.PATTERNS
        ]

    def redact(self, text: str) -> str:
        """对文本进行脱敏

        Args:
            text: 原始文本

        Returns:
            脱敏后的文本
        """
        result = text
        for pattern, replacement in self._compiled_patterns:
            result = pattern.sub(replacement, result)
        return result

    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """对字典中的值进行脱敏

        Args:
            data: 原始字典

        Returns:
            脱敏后的字典（新字典，不修改原字典）
        """
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.redact(value)
            elif isinstance(value, dict):
                result[key] = self.redact_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.redact_dict(item) if isinstance(item, dict)
                    else self.redact(item) if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result
