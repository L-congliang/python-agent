# Phase 3.1 源码理解笔记

更新时间：2026-07-06

## 1. Phase 3.1 目标

把 session 从"运行时内存状态"推进成"可恢复对象"，让 run / resume / inspect 成为一等能力。

**核心交付：**
- Task 1：session 可持久化、可恢复
- Task 4：autosave 进入默认使用体验
- Task 2：session/run/workspace/checkpoint 状态可见
- Task 3：resume 前能判断 freshness

**测试基线：** 1061 passed, 6 skipped

## 2. 源码阅读顺序

```
src/agent/main.py
  ↓
src/agent/core/loop.py
  ↓
src/agent/persistence/session_store.py
  ↓
src/agent/cli/app.py
  ↓
tests/test_session_resume.py
tests/test_session_autosave.py
tests/test_cli_session_commands.py
tests/test_resume_freshness.py
```

**为什么这个顺序：**
- main.py 是入口，看装配链路
- loop.py 是核心，看 session state 导入导出
- session_store.py 是持久化，看 raw state vs summary
- app.py 是 CLI，看用户怎么看到这些能力
- 测试是保护，看边界和回归

## 3. 五个关键问题与答案

### Q1：默认入口怎么完成 session lifecycle 装配？

**main.py 的装配链路：**

```
main() 
  → load_config() 
  → create_agent_loop(client, model, workspace_root)
    → LoopConfig(session_dir=workspace/.agent/sessions)
    → AgentLoop.__init__()
      → SessionStore(session_dir)
  → _handle_resume(loop, "latest")  # 如果有 --resume
    → session_store.load_latest()
    → loop.import_session_state(session_data)
    → _check_resume_freshness(loop, session_data)
  → create_agent_app(loop, model)
    → AgentApp(on_session=..., on_sessions=..., on_inspect=...)
```

**关键设计决策：**
- 装配逻辑放在 main.py，不放在 loop.py
- loop.py 只提供接口，不负责装配
- 这样 loop 可以被测试、被复用，不依赖入口

### Q2：为什么 session 要分 raw state 和 summary？

**raw resumable state（用于程序恢复）：**
- session_id
- messages（完整消息历史）
- turn_count、tool_call_count、total_tokens
- memory
- workspace_root
- last_run_id

**summary/preview（用于展示）：**
- id
- created_at
- workspace_root
- message_count

**为什么分层：**
- raw state 用于真正恢复，需要完整数据
- summary 用于展示，只需要摘要
- 如果只保存 summary，无法恢复
- 如果只保存 raw state，展示时会泄露敏感信息

**代码位置：**
- `session_store.py` line 61-99：save() 保存 raw state
- `session_store.py` line 140-164：list_sessions() 返回 summary
- `loop.py` line 918-933：export_session_state() 导出 raw state

### Q3：autosave 为什么这样设计？

**触发时机：**
- run() 成功返回前
- run_stream() 完整结束后
- 不在每个 chunk 保存

**为什么不在每个 chunk 保存：**
- 频繁 IO 会让测试和 CLI 都变慢
- 每个 chunk 保存会导致大量小文件
- 如果中断，保存半截脏状态会更糟

**为什么 reset 后清 session_id：**
- 保证新旧 session 分离
- 下次 save_session() 时自动生成新 session
- 如果不清，会把新对话覆盖进旧 session

**代码位置：**
- `loop.py` line 956-973：save_session() 检查 enable_autosave
- `loop.py` line 810-830：reset() 清空 session_id

### Q4：resume freshness 为什么只做检测和提示，不做自动恢复？

**四类状态：**
- full-valid：所有文件未变，可以正常恢复
- partial-stale：部分文件已变，允许恢复但警告
- invalid：核心文件删除，不静默恢复
- unavailable：没有 checkpoint

**为什么不做自动恢复：**
- 自动恢复会引入复杂逻辑（哪些文件恢复？怎么恢复？）
- 自动恢复可能覆盖用户手动修改
- 只做检测和提示，让用户决定
- 这是"保守但安全"的设计

**代码位置：**
- `checkpoint.py` line 218-291：check_freshness() 检测逻辑
- `main.py` line 227-270：_check_resume_freshness() 提示逻辑

### Q5：/inspect 这类命令为什么能提升项目含金量？

**/inspect 展示的内容：**
- Run：run_id、model、turns、tool_calls
- Session：session_id、messages
- Workspace：root、git_branch、commits
- Checkpoint：是否启用
- Freshness：status、message

**为什么能提升含金量：**
- 让底层能力变成"用户可见"
- 演示时一眼看出"当前跑的是哪个 session、哪个 run、在哪个 workspace"
- 面试时能讲清楚"系统状态可见性"
- 这是真正 agent 产品里很重要的运行态管理能力

**代码位置：**
- `loop.py` line 985-1070：摘要接口（get_session_summary、get_inspect_summary 等）
- `app.py` line 535-620：CLI 命令（/session、/sessions、/inspect）

## 4. 面试可讲口径

**一句话总结：**
> "我实现了 session/workspace lifecycle management，包括持久化、自动保存、状态检查、freshness 检测。resume 时能判断并展示当前恢复状态，/inspect 能看到当前 run/session/workspace/checkpoint/freshness 综合摘要。"

**可以展开讲的点：**
1. **装配链路**：main.py 负责装配，loop.py 只暴露接口，这样 loop 可以被测试、被复用
2. **raw state vs summary**：分层设计，raw state 用于恢复，summary 用于展示
3. **autosave 设计**：不在每个 chunk 保存，避免频繁 IO 和半截脏状态
4. **freshness 检测**：只做检测和提示，不做自动恢复，保守但安全
5. **/inspect 命令**：让底层能力变成用户可见，提升系统状态可见性

**不要讲成：**
- production-grade session system
- 完整 workspace restore
- 自动文件恢复
- run 管理系统

## 5. 复盘收获

**我已经理解了：**
- 默认入口怎么完成 session lifecycle 装配
- 为什么 session 要分 raw state 和 summary
- autosave 为什么这样设计
- resume freshness 为什么只做检测和提示
- /inspect 这类命令为什么能提升项目含金量

**下一阶段建议：**
- 不要立刻开新功能
- 先把这份复盘笔记固化到文档
- 再决定下一阶段方向
