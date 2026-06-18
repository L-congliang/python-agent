# 进度日志

## Session 4 — 2026-06-18 家（当前）

### 完成
- F01 模型层实现完成
  - `core/model.py`: MimoClient + ModelConfig + load_config
  - 同步对话 chat()、流式对话 chat_stream()
  - 指数退避重试机制（限流、超时、连接错误）
  - 错误分类处理（认证错误不重试）
  - 日志记录（调用次数、token 数、耗时）
  - 配置管理（环境变量）
- `tests/test_model.py`: 15 个测试通过
  - 配置加载、客户端初始化
  - 同步/流式对话
  - 重试机制、错误处理
  - 集成测试（需要 API key）
- 更新 `core/__init__.py` 导出新模块

### 当前状态
- F01 status: done
- F02-F10 status: pending
- F01-F03 spec 已完成，F04-F10 spec 待写

### 下次从这里开始
1. 实现 F02 CLI 框架（`cli/app.py`）
2. 对应 spec: `specs/F02-cli.md`
3. 关键任务：rich 渲染 + prompt_toolkit 交互

### 阻塞点
- （无）

---

## Session 2 — 2026-06-18 公司

### 完成
- 学习 OpenSpec，决定用手写 spec 方式
- 写了 F01 Tool Protocol spec（后来改为 F03）
- 更新 README 项目结构
- 添加 DEV_SYNC.md 跨地点同步机制

---

## Session 1 — 2026-06-18 家

### 完成
- 项目初始化，创建虚拟环境
- 修复 hatchling 构建错误（pyproject.toml 添加 wheel packages 配置）
- 搭建 harness 基础设施（CLAUDE.md, feature_list.json, Makefile, init.sh, claude-progress.md）
- 创建 types.py（6 个 dataclass：Role, ToolInput, ToolOutput, ToolCall, ToolResult, Message, StreamEvent）
- 学习 harness engineering 理念

### 下次从这里开始
- 写 F01 的 spec 文件
