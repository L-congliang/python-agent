"""模型适配器实现。

每个模型的差异在这里封装，AgentLoop 不需要知道具体实现。
"""

from .mimo_adapter import MimoAdapter
from .deepseek_adapter import DeepSeekAdapter

__all__ = ["MimoAdapter", "DeepSeekAdapter"]
