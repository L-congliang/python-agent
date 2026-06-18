# CLAUDE.md

本项目的学习目标：通过逐步实现，理解 Claude Code 的 Agent 架构。

## 核心规则

### 每次改动必须推送 Git

每完成一个功能、改进或修复，都要：
1. `git add` 相关文件
2. `git commit` 写清楚改了什么
3. `git push` 推送到远程

不允许本地堆积多个未推送的提交。

### 代码风格

- 类型注解：所有函数签名必须有类型注解
- 文档字符串：公开接口必须有 docstring
- 简单优先：不为未来写代码，只解决当前问题

### 开发流程

```
写代码 → 验证 import/运行 → 写测试(如适用) → git commit → git push
```

### 模块实现顺序

按 LEARNING_PROGRESS.md 中的待实现列表顺序：
1. `tools/base.py` — Tool Protocol
2. `core/loop.py` — Agent 主循环
3. `tools/bash.py` — Bash 工具
4. 依此类推...

每完成一个模块，更新 LEARNING_PROGRESS.md 的进度。

### 虚拟环境

激活方式：
```bash
source .venv/Scripts/activate   # Windows Git Bash
```

安装依赖：
```bash
pip install -e ".[dev]"
```

### 测试

```bash
python -m pytest tests/
```
