# 修复日志

## Phase 1

- 默认入口补齐基础工具注册
- CLI `/reset`、`/compact` 接线
- Windows 非 UTF-8 终端 fallback
- `run()` / `run_stream()` Plan Mode 行为对齐
- `grep / glob` 纳入 workspace guard
- Windows shell fallback 修复
- ASK fail-closed
- `write` 默认拒绝覆盖
- `edit` 增加 diff / preview

## Phase 2

- 实现真实 permission confirmation channel
- `file_edit` 增加原子写入失败保护
- 新增任务级 e2e regression

## Phase 2.1

### Fix 1：补默认入口 smoke test

修改：
- `src/agent/main.py`
- `tests/test_main_smoke.py`

内容：
- 拆出 `create_default_registry()`
- 拆出 `create_agent_loop()`
- 拆出 `create_agent_app()`
- 用 smoke test 验证默认 registry、默认 loop、CLI confirmation handler、`/reset`、`/compact` 和 ASCII fallback
- self-audit follow-up：新增直接调用 `main()` 的入口 smoke，确认默认装配路径真正被锁住，而不是只测 isolated helper

结果：
- 现在不容易再出现“模块测试全绿，但真实入口装配断线”的问题

### Fix 2：README 改成真实 demo 版本

修改：
- `README.md`

内容：
- 删除过度包装和过时描述
- 写清真实能力、运行方式、测试方式、安全边界和当前限制
- 明确区分 fake-model 测试演示与真实 CLI 演示

结果：
- 别人第一次看仓库时，不会被误导成“生产级 Claude Code 克隆”

### Fix 3：新增 demo / resume / interview 文档

新增：
- `08-demo-walkthrough.md`
- `09-resume-version.md`
- `10-interview-review-guide.md`

结果：
- 项目现在更适合现场演示
- 简历和面试表达更容易保持真实、一致、可复述
- demo walkthrough 已明确标出：哪些演示路线需要 API key，哪些是 fake-model / local test

## Phase 3.1 Task 1

### Fix 1：无损 Session Persistence + Resume

新增：
- `tests/test_session_resume.py`

修改：
- `src/agent/core/loop.py`：增加 session_store、session_id、export_session_state、import_session_state、save_session
- `src/agent/main.py`：增加 --resume 参数、_handle_resume 函数

内容：
- SessionStore 二层结构：raw resumable state（供程序恢复）+ summary/preview（供展示）
- main.py 增加 --resume latest 和 --resume \<session_id\> 参数
- AgentLoop 增加 export_session_state / import_session_state 接口
- 默认 session 目录：workspace/.agent/sessions

结果：
- 新启动 CLI session 会生成 session_id
- 完成一次用户消息后，session 可自动保存
- --resume latest 能恢复最近一个 session
- --resume \<session_id\> 能恢复指定 session
- /reset 后开启新 session
- 没有 session 时 --resume latest 给清晰提示
- 测试基线从 997 提升到 1017

## Phase 2.3C

### Fix 1：真实远程 LLM Smoke 回归

新增：
- `tests/test_real_llm_smoke.py`

内容：
- 环境门控：RUN_REAL_LLM_SMOKE=1，MIMO_API_KEY 缺失时自动 skip
- client smoke：验证配置读取、client 初始化、远程 API 可达、基本响应格式
- agent loop smoke：验证默认装配路径、tool use -> observation -> final answer
- 收敛 prompt：client 用"reply with exactly OK"，agent loop 用"read hello.txt"
- 网络/API 异常时，报错能区分是远程问题，不伪装成本地逻辑回归

结果：
- 默认 pytest tests -q 不依赖真实 API
- 开启 env 后，真实 client smoke 能跑
- 开启 env 后，最小 agent loop smoke 能跑
- 测试基线从 994 提升到 997

## Phase 2.3B

### Fix 1：Session 级 Permission Policy

新增：
- `src/agent/permissions/session_policy.py`
- `tests/test_permission_session_policy.py`

修改：
- `src/agent/core/types.py`：新增 PermissionConfirmationResult 数据结构
- `src/agent/core/loop.py`：接入 session policy 查询，确认后记录 allow-once/allow-session，reset 时清空
- `src/agent/cli/app.py`：CLI 确认支持 y/a/n/Enter

内容：
- session_policy.py：内存态 store，支持 allow-once / allow-session
- bash 按精确 command 匹配，write/edit 按规范化路径匹配
- CLI 交互：y=本次允许，a=本 session 允许，n/Enter=拒绝
- DENY 不被 session allow 绕过
- /reset 清空 session policy

结果：
- 第一次高风险操作会询问
- 选择 a 后，相同命令/相同文件不再询问
- 选择 y 后，只当前一次放行
- 测试基线从 971 提升到 994

## Phase 2.3A

### Fix 1：Backup / Rollback / Edit History

新增：
- `src/agent/persistence/edit_history_store.py`
- `tests/test_edit_history_store.py`
- `tests/test_rollback_flow.py`

修改：
- `src/agent/core/context.py`：ToolUseContext 增加 edit_history_store 字段
- `src/agent/core/loop.py`：LoopConfig 增加 edit_history_dir，创建 context 时注入 store
- `src/agent/main.py`：create_agent_loop 设置默认 edit_history_dir，create_agent_app 注册 rollback/history 回调
- `src/agent/tools/file_write.py`：写入前记录历史，成功后创建 backup
- `src/agent/tools/file_edit.py`：编辑前记录历史，成功后创建 backup
- `src/agent/cli/app.py`：新增 /history 和 /rollback 命令

内容：
- edit_history_store.py：最小持久化存储，支持 record_write/record_edit/record_rollback/get_latest/rollback_latest
- 新建文件记录为 created，修改文件记录为 modified
- rollback latest：created 删除文件，modified 恢复备份
- CLI 命令：/history 显示最近 10 条历史，/rollback latest 回退最近一次修改
- 默认历史目录：workspace/.agent/file-history

结果：
- write/edit 的成功修改都可追溯
- 至少支持回退最近一次成功修改
- 新建文件和修改已有文件都能正确回退
- CLI 可演示 /history 和 /rollback latest
- 测试基线从 943 提升到 979

## Phase 2.2

### Fix 1：统一 Observation Budget 契约

修改：
- `src/agent/core/types.py`
- `tests/test_observation_contract.py`

内容：
- 新增 `ObservationMetadata` 数据类
- `ToolResult` 增加可选 `observation` 字段
- 保持向后兼容：旧用法不传 observation，行为不变

结果：
- 工具输出可以同时提供 preview（模型可见）和 artifact（用户可追溯）
- 为后续统一截断和 loop 回注奠定基础

### Fix 2：工具层输出截断与 Artifact 化统一

新增/修改：
- `src/agent/tools/observation_helper.py`（新增共享模块）
- `src/agent/tools/bash.py`
- `src/agent/tools/file_read.py`
- `src/agent/tools/grep.py`
- `src/agent/tools/glob.py`
- `src/agent/tools/file_edit.py`
- `tests/test_observation_truncation.py`

内容：
- 创建统一的 `observation_helper` 模块
- bash 保留尾部（命令输出有用信息在最后）
- read/grep/glob 保留头部（代码结构在开头）
- 长输出自动保存到 artifact 文件
- preview 中提示"完整输出已保存到 xxx"

结果：
- 所有工具的长输出处理不再各自散落
- 用户能找到完整结果，模型只看到 bounded preview

### Fix 3：Loop 侧 Observation Reinjection Hardening

修改：
- `src/agent/core/loop.py`
- `tests/test_loop_compaction.py`

内容：
- 修改 `_handle_tool_results()` 优先使用 observation.preview
- 新增 `_resolve_observation_content()` 方法
- 保持 output 兼容：没有 observation 时回退到 output

结果：
- 长工具输出不再无脑完整回灌到消息历史
- 模型看到的是 bounded preview，不是 full observation
- 现有 e2e 主链路和入口 smoke 不退化

### Fix 4：CLI 与 Run Artifact 可见性补强

修改：
- `src/agent/cli/app.py`
- `src/agent/core/types.py`
- `tests/test_cli_observation.py`
- `tests/test_cli.py`

内容：
- `show_tool_result` 支持 observation 参数
- 新增 `_show_observation_hint` 方法
- `StreamEvent` 增加 observation 字段
- CLI 面板显示截断提示和 artifact 路径

结果：
- 用户能知道完整输出没丢，只是没全部塞回模型
- 截断提示清晰显示 artifact 路径

### Fix 5：打通 artifact 落盘（Code Review 修复）

修改：
- `src/agent/core/context.py`：ToolUseContext 增加 artifact_dir 字段
- `src/agent/core/loop.py`：LoopConfig 增加 artifact_dir，创建 context 时传入
- `src/agent/main.py`：create_agent_loop 设置默认 artifact_dir
- `src/agent/tools/bash.py`：传入 context.artifact_dir
- `src/agent/tools/file_read.py`：传入 context.artifact_dir，修复 "full + preview" 双层
- `src/agent/tools/grep.py`：传入 context.artifact_dir
- `src/agent/tools/glob.py`：传入 context.artifact_dir
- `src/agent/tools/file_edit.py`：传入 context.artifact_dir
- `tests/test_observation_integration.py`：新增 integration 测试

内容：
- 5 个工具的 build_observation 调用现在传入 context.artifact_dir
- 默认 artifact_dir 为 workspace/.artifacts
- read 工具现在是真正的 "full output + bounded preview" 双层
- 长输出自动保存到 artifact 文件

结果：
- artifact 落盘功能真正打通
- loop 里的 artifact 提示分支和 CLI 里的 artifact 路径展示分支现在能走到
- 测试基线从 916 提升到 926

### Fix 6：CLI 事件链路与 ASK 权限 observation 保留（Code Review 修复）

修改：
- `src/agent/core/loop.py`：LoopConfig 增加 on_tool_result 回调，_execute_tool_calls 调用回调
- `src/agent/main.py`：create_message_handler 注册回调，yield tool_result 事件
- `tests/test_observation_e2e.py`：新增端到端 integration 测试

内容：
- CLI 现在能显示 tool_result 事件和 artifact 提示
- ASK 权限确认后 observation 被保留（不丢弃）
- 端到端测试验证 "真实工具执行 -> ToolResult.observation -> loop 注入 -> 事件回调" 链路

结果：
- 默认 CLI 演示路径真正打通
- bash/edit 等 ASK 工具的 observation 不再丢失
- 测试基线从 926 提升到 933

### Fix 7：CLI 事件链路完整性与消息处理器测试（Code Review 修复）

修改：
- `src/agent/main.py`：create_message_handler 增加尾部 flush，保留已有 on_tool_result 回调（callback chaining）
- `src/agent/core/loop.py`：所有分支（中断、重复、路径逃逸、校验失败、权限拒绝、ASK 未确认）都调用 on_tool_result 回调
- `tests/test_cli_event_flow.py`：新增消息处理器的事件编排与 flush 行为测试

内容：
- create_message_handler 现在在流结束后 flush 所有剩余的 tool_result 事件
- 所有 early return 分支都调用 on_tool_result 回调，确保 CLI 能看到所有 tool result
- 保留已有的 on_tool_result 回调，避免覆盖外部配置的观察/埋点回调
- 测试验证消息处理器的事件编排与 flush 行为（不经过真实 AgentApp）

结果：
- 默认 CLI 路径的 tool_result 事件链路现在完整无遗漏
- 测试基线从 933 提升到 943
