# 当前状态

更新时间：2026-07-06

## 当前定位

这个项目现在最合适的定位是：

`偏扎实的 Demo / 展示级，接近 Prototype 边缘`

不是：

- 生产级 Claude Code 替代品
- 完整 MCP 平台
- WebUI 产品
- 多 agent 并行系统

## 当前已经稳定落地的能力

### 基础能力（Phase 0-1）
- `AgentLoop / ToolRegistry / tools` 的多轮工具调用闭环
- 基础工具：`bash / read / write / edit / grep / glob`
- `ALLOW / ASK / DENY` 权限系统
- CLI confirmation handler
- `file_edit` diff preview
- `file_edit` 原子写入失败保护
- workspace guard
- 任务级 e2e regression
- 默认入口 smoke test
- 中文文档包、简历版材料、面试复习材料

### 上下文工程（Phase 2.2）
- **Observation Budget 契约**：工具输出的 preview + artifact 双层机制
- **统一截断逻辑**：bash/read/grep/glob/edit 的长输出统一处理
- **CLI 截断提示**：用户能看到"输出已截断，完整结果在 xxx"
- **artifact 落盘**：长输出自动保存到 .artifacts 目录
- **CLI 事件链路**：所有 tool_result 事件都能在默认 CLI 路径显示

### 可恢复能力（Phase 2.3A）
- **Backup / Rollback / Edit History**：write/edit 前自动备份
- **历史记录**：记录 tool_name、file_path、action、backup_path、before_hash、after_hash、preview
- **CLI 命令**：/history 和 /rollback latest
- **两种回退**：created（删除文件）、modified（恢复备份）

### 权限体验（Phase 2.3B）
- **Session 级 Permission Policy**：减少重复 ASK
- **allow-once / allow-session**：按精确 command 或规范化路径匹配
- **CLI 交互**：y=本次允许，a=本 session 允许，n/Enter=拒绝
- **安全边界**：DENY 不被 session allow 绕过，/reset 清空 session policy

### 真实远程链路（Phase 2.3C）
- **真实远程 LLM Smoke**：验证真实 API 链路没断
- **环境门控**：RUN_REAL_LLM_SMOKE=1，MIMO_API_KEY 缺失时自动 skip
- **收敛 prompt**：client 用"reply with exactly OK"，agent loop 用"read hello.txt"
- **错误区分**：网络/API 异常时，报错能区分是远程问题

## 测试基线

| 指标 | 数值 |
|------|------|
| 测试总数 | 997 passed, 6 skipped |
| 新增测试（2.2-2.3C） | +139 |
| 工具数 | 6（bash/read/write/edit/grep/glob） |
| CLI 命令 | /help, /clear, /reset, /compact, /history, /rollback |
| 权限模式 | allow-once, allow-session, DENY |
| 截断策略 | tail（bash）, head（read/grep/glob） |

## 当前最适合演示的点

1. **上下文膨胀控制**：长 grep/bash 输出不会撑爆上下文，模型看到 bounded preview
2. **文件修改可回退**：write/edit 前自动备份，/rollback latest 可恢复
3. **权限确认不再笨重**：相同命令/文件可 session 复用批准
4. **真实远程链路可验证**：不只是 fake-model e2e，真实 API 也没断

## 当前成熟度为什么是"接近 Prototype 边缘"

因为虽然主链路、权限、编辑、安全边界和 e2e 已经比较扎实，但仍然缺少：

- session 持久化（当前只在内存中）
- workspace 快照与恢复
- run/resume/inspect 成为一等能力
- 更完整的 integration / smoke 覆盖

## 当前是否可以写进简历

可以，但必须按真实能力写：

### 可以写的
- agent loop、tool system、permission confirmation、diff preview、workspace guard、e2e regression
- Observation Budget 契约、preview + artifact 双层机制
- Backup / Rollback / Edit History
- Session 级 Permission Policy
- 真实远程 LLM Smoke 回归

### 不能写的
- MCP、WebUI、多 agent 并行
- 完整 rollback（只支持 latest）
- 真实完整 e2e benchmark
- production-ready sandbox
- memory / session 产品化
