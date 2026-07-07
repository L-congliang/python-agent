# 当前状态

更新时间：2026-07-06

## 当前定位

这个项目现在最合适的定位是：

`Demo / 展示级（可现场演示、可复习、可写进简历）`

不是：

- 生产级 Claude Code 替代品
- 完整 MCP 平台
- WebUI 产品
- 多 agent 并行系统

## 当前已经稳定落地的能力

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
- **Observation Budget 契约**：工具输出的 preview + artifact 双层机制
- **统一截断逻辑**：bash/read/grep/glob/edit 的长输出统一处理
- **CLI 截断提示**：用户能看到"输出已截断，完整结果在 xxx"

## 当前最适合演示的点

- agent 能读取代码
- agent 能通过 `edit` 修改代码
- 高风险写操作会请求确认
- 修改前能看到 diff
- 修改后能运行测试
- workspace 外访问会被拦截

## 当前成熟度为什么还是 Demo

因为虽然主链路、权限、编辑、安全边界和 e2e 已经比较扎实，但仍然缺少：

- 完整 rollback
- production-ready sandbox
- 真实远程 LLM e2e 回归
- session 级 permission policy
- 更完整的 integration / smoke 覆盖

## 当前是否可以写进简历

可以，但必须按真实能力写：

- 可以写 agent loop、tool system、permission confirmation、diff preview、workspace guard、e2e regression
- 不能写 MCP、WebUI、多 agent 并行、完整 rollback、production-ready sandbox
