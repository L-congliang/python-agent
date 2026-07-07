# 设计决策

## 决策 1：入口装配拆成可测试函数

为什么：

- `main()` 里全写死时，不容易做稳定 smoke test
- README、demo 和简历都要建立在“默认入口可验证”之上

实现：

- `create_default_registry()`
- `create_agent_loop()`
- `create_agent_app()`

收益：

- 测试可以覆盖真实入口装配，但不依赖 API key

## 决策 2：README 不再按“功能越多越好”写

为什么：

- 当前目标是可演示、可复习、可投递
- 夸大能力会让面试追问时更被动

策略：

- 只写真实落地能力
- 明确列出当前限制
- 把 MCP / WebUI / 多 agent 等还没准备好的部分排除在主叙事之外

## 决策 3：Demo walkthrough 以测试路径为主，CLI 路径为辅

为什么：

- e2e 更稳定
- 面试现场更容易复现
- CLI 真跑仍依赖 API key

所以：

- 路线 A 用 e2e 测试证明闭环
- 路线 B 再补真实 CLI 演示

## 决策 4：简历和面试材料单独文档化

为什么：

- README 解决”别人怎么看仓库”
- `09-resume-version.md` 解决”简历怎么写”
- `10-interview-review-guide.md` 解决”自己怎么复习和表达”

这样三种使用场景不互相混淆。

## 决策 5：Observation Budget 契约采用双层机制

为什么：

- 长工具输出（grep/bash/read）如果全部回灌到消息历史，会导致上下文膨胀
- 直接截断会丢失信息，用户无法找到完整结果
- 需要同时满足：模型看到 bounded preview + 用户能找到 full output

实现：

- `ObservationMetadata` 数据类：preview、artifact_path、was_truncated、full_output_chars
- `ToolResult` 增加可选 observation 字段（向后兼容）
- `observation_helper.py` 共享模块：统一截断逻辑和 artifact 保存

收益：

- 模型上下文不会被长输出撑爆
- 用户仍能找到完整结果（通过 artifact 路径）
- 不同工具可以有不同的截断策略（tail/head）

## 决策 6：不同工具使用不同的截断策略

为什么：

- bash 命令输出的有用信息在最后（测试结果、错误信息）
- read/grep/glob 的代码结构在开头（imports、类定义、函数签名）
- 统一用 head 或 tail 都不适合所有场景

实现：

- bash：tail 策略（保留尾部）
- read/grep/glob：head 策略（保留头部）
- 截断头信息会明确提示”truncated X lines from head/tail”

收益：

- 用户看到的是最有用的部分
- 截断行为可预测、可解释

## 决策 7：Loop 回注优先使用 preview

为什么：

- 旧工具不传 observation，仍用 output 字段，行为不变
- 新工具返回 observation 时，loop 优先使用 preview
- 这样既能解决上下文膨胀，又不破坏现有测试

实现：

- `_handle_tool_results()` 调用 `_resolve_observation_content()`
- 优先使用 observation.preview，回退到 output
- 如果有 artifact_path，附加提示”[完整输出已保存到: xxx]”

收益：

- 向后兼容：现有测试全部通过（916 passed, 3 skipped）
- 渐进式改进：新工具自动受益，旧工具无需修改
