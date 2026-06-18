# CLAUDE.md

本项目通过逐步实现，学习 Claude Code 的 Agent 架构。

## 项目概览

- **目标**: 从零构建一个 Python Agent，理解 tool 调用、主循环、错误处理、上下文管理等核心机制
- **技术栈**: Python 3.12+, anthropic SDK, pydantic, pytest
- **结构**: `src/agent/` (core/tools/permissions/context), `tests/`, `docs/`

## 验证命令

每次完成改动后，必须运行以下命令确认没有破坏：

```bash
# 激活环境
source .venv/Scripts/activate

# 安装/更新依赖
pip install -e ".[dev]"

# 类型检查（如果配置了 mypy）
mypy src/ --strict

# 运行测试
python -m pytest tests/ -x -v

# 完整验证（全部通过才能提交）
make check
```

**没有通过验证的代码不能提交。**

## 开发流程

```
1. 读 feature_list.json → 确认当前要做的功能
2. 读 claude-progress.md → 了解上次 session 做到哪了
3. 写代码
4. 运行验证命令
5. 验证通过 → 更新 progress → git commit → git push
6. 验证失败 → 修复 → 重新验证
```

## 核心规则

### 一次只做一个功能

从 `feature_list.json` 中选一个未完成的功能，做完再做下一个。不允许同时开三个功能然后都做一半。

### 每次改动必须推送 Git

每完成一个功能、改进或修复：
1. `git add` 相关文件
2. `git commit` 写清楚改了什么
3. `git push` 推送到远程

不允许本地堆积多个未推送的提交。

### 完成标准

一个功能"完成"必须满足：
- 代码写完且通过验证命令
- 有对应的测试（如适用）
- `feature_list.json` 中标记为 done
- `claude-progress.md` 中记录了本次改动

### 代码风格

- 类型注解：所有函数签名必须有类型注解
- 文档字符串：公开接口必须有 docstring
- 简单优先：不为未来写代码，只解决当前问题

### Session 结束前

- 更新 `claude-progress.md`
- 更新 `feature_list.json`
- 记录未完成的工作和阻塞点
- 确保 git 状态干净（全部已提交推送）
