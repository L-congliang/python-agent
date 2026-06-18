#!/bin/bash
# 每次 agent session 开始时运行此脚本
# 验证环境健康，确保可以开始开发

set -e

echo "=== 初始化环境 ==="

# 1. 检查 Python 版本
python --version

# 2. 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate 2>/dev/null
    echo "虚拟环境已激活"
else
    echo "错误: .venv 不存在，请先创建虚拟环境"
    exit 1
fi

# 3. 安装/更新依赖
pip install -e ".[dev]" -q

# 4. 验证核心模块可 import
python -c "from agent.core.types import ToolCall, ToolResult; print('核心模块 import 正常')"

# 5. 运行测试
python -m pytest tests/ -x -q 2>/dev/null || echo "暂无测试或测试失败"

echo "=== 环境就绪 ==="
