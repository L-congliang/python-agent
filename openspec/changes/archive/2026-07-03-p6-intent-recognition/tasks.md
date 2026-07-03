## 1. System Prompt 优化

- [x] 1.1 创建 `src/agent/prompts/` 模块，实现 SystemPromptBuilder 类
- [x] 1.2 实现 Identity 部分（agent 名称、角色描述、能力列表）
- [x] 1.3 实现 Behavioral Guidelines 部分（通用原则 + 具体规则）
- [x] 1.4 实现 Tool Selection Guide 部分（工具选择映射 + 工具关系说明）
- [x] 1.5 重构 `_build_system_prompt()` 使用 SystemPromptBuilder 组装
- [x] 1.6 编写 System Prompt 优化测试

## 2. Tool Description 微调

- [x] 2.1 修改 file_edit 工具 description，加"优先于 write 使用"
- [x] 2.2 修改 file_write 工具 description，加"仅用于创建新文件"
- [x] 2.3 修改 grep 工具 description，加"优先于 bash grep"
- [x] 2.4 编写 Tool Description 微调测试

## 3. Plan Mode 实现

- [x] 3.1 在 PermissionChecker 中添加 mode 字段（normal/plan）
- [x] 3.2 实现 Plan Mode 权限控制（write/edit/bash 写命令返回 deny）
- [x] 3.3 在 LoopConfig 中添加 plan_mode 配置项
- [x] 3.4 在 `_build_system_prompt()` 中添加 Plan Mode 标记注入
- [x] 3.5 实现 Plan Mode 激活逻辑（检测用户规划意图）
- [x] 3.6 实现 Plan Mode 确认/修改/取消流程
- [x] 3.7 编写 Plan Mode 测试

## 4. Prompt Ablation Experiment

- [x] 4.1 创建 `src/agent/experiments/` 模块结构
- [x] 4.2 实现 Prompt Ablation 实验框架（支持 4 个配置对比）
- [x] 4.3 创建测试任务集（至少 20 个任务，覆盖所有工具类型）
- [x] 4.4 实现工具选择准确率指标（first_try_accuracy、tool_accuracy）
- [x] 4.5 运行 Prompt Ablation Experiment
- [x] 4.6 生成实验报告到 `docs/test-reports/P6-prompt-ablation.md`

## 5. Benchmark 对比

- [x] 5.1 运行 benchmark 对比 Phase 5
- [x] 5.2 生成 benchmark 对比报告到 `docs/test-reports/P6-benchmark.md`

## 6. 测试与验证

- [x] 6.1 运行全量测试（uv run pytest tests/ -x -v）
- [x] 6.2 运行类型检查（uv run mypy src/ --strict）
- [x] 6.3 更新 feature_list.json 标记 P6 完成
- [x] 6.4 更新 claude-progress.md 记录本次改动
