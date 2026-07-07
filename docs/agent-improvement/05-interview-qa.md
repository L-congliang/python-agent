# 面试问答

## Q：这个项目现在到底是什么？

A：

这是一个参考 Claude Code / Codex 思路实现的本地 Python code agent demo。我重点做的是 agent loop、工具系统、权限确认、文件编辑安全和回归测试，不是完整复刻 Claude Code。

## Q：它的核心闭环是什么？

A：

`用户输入 -> AgentLoop -> 模型输出 tool call -> ToolRegistry 执行工具 -> tool result 回注 -> 下一轮或最终答案`

## Q：为什么要有 ToolRegistry？

A：

因为工具不只是“能调到”就够了，还需要统一管理：

- 注册
- 查询
- schema
- 输入校验
- 权限检查
- 执行

这样 loop 不需要知道每个工具的实现细节。

## Q：你怎么处理高风险工具确认？

A：

权限分成 `ALLOW / ASK / DENY`。`ASK` 不会默认执行，必须通过 CLI confirmation handler 得到用户批准。非交互环境下继续 fail-closed。

## Q：为什么 ASK 不能默认执行？

A：

因为 ASK 的含义就是“需要额外确认”。如果 ASK 还能自动执行，那权限系统只是形式上存在，实际没有安全边界。

## Q：为什么 `file_edit` 要有 diff preview？

A：

因为代码修改最重要的是“改了什么”。diff preview 解决可见性，原子写入解决失败保护，这两件事都比“先做完整 rollback”更适合当前 demo 阶段。

## Q：workspace guard 解决什么问题？

A：

防止 `read / write / edit / grep / glob` 越出当前 workspace。哪怕是只读搜索，如果能越界，也可能暴露不该给 agent 的内容。

## Q：入口 smoke test 证明了什么？

A：

它证明默认入口装配没坏，包括：

- 基础工具确实注册了
- loop 能构建
- CLI 能构建
- confirmation handler 接上了
- `/reset` 和 `/compact` 不是假按钮

## Q：为什么现在还不是 production-ready？

A：

因为还缺：

- OS-level sandbox
- 完整 rollback
- 更完整的 integration / smoke coverage
- 更成熟的 session 级权限策略
- 真实远程 LLM 回归链路

## Q：你怎么处理长工具输出导致的上下文膨胀？

A：

我实现了 Observation Budget 契约，核心是"preview + artifact 双层机制"：

1. **preview**：截断后的预览内容，回灌到消息历史（模型可见）
2. **artifact**：完整输出保存到文件，路径记录在 metadata 中（用户可追溯）

这样模型只看到 bounded preview，不会被长输出撑爆上下文，但用户仍能找到完整结果。

## Q：不同工具的截断策略有什么区别？

A：

- **bash**：保留尾部（tail 策略）——命令输出的有用信息在最后（测试结果、错误信息）
- **read/grep/glob**：保留头部（head 策略）——代码结构在开头（imports、类定义、函数签名）

这是根据不同工具的实际使用场景设计的。

## Q：这个设计对简历有什么价值？

A：

可以写成："实现 bounded observation reinjection 和 artifact-backed tool outputs，解决 tool-using agents 的上下文膨胀问题"

这比"又加一个工具"更有系统设计味道，很像真正 agent 系统的工程点。

具体来说：
- preview + artifact 双层契约：模型只看到 bounded preview，用户能追溯完整结果
- 统一截断策略：bash 保留尾部，read/grep/glob 保留头部
- 自动 artifact 保存：长输出自动落盘，路径记录在 metadata 中
- CLI 能显示截断提示和 artifact 路径，ASK 权限确认后 observation 不丢失
- 所有 tool result（包括中断、重复、路径逃逸、权限拒绝等）都能在默认 CLI 路径显示
- 消息处理器保留已有回调（callback chaining），避免覆盖外部配置的观察/埋点回调

## Q：为什么不在 CLI 中显示完整输出？

A：

因为完整输出可能很长（几千行），直接显示会刷屏。CLI 只显示 preview，但会提示"完整结果已保存到 xxx"。用户如果需要完整结果，可以自己去查看 artifact 文件。

## Q：你怎么处理文件编辑的回退问题？

A：

我实现了 Backup / Rollback / Edit History 机制：

1. **写前备份**：write/edit 操作前自动创建备份文件
2. **历史记录**：记录每次操作的 tool_name、file_path、action（created/modified）、backup_path、before_hash、after_hash、preview
3. **回退支持**：rollback latest 可以回退最近一次修改
   - created：删除新建的文件
   - modified：从备份恢复原内容
4. **CLI 命令**：/history 显示最近 10 条历史，/rollback latest 回退最近一次修改

这个设计让文件修改不再只是"尽量安全"，而是"出了问题能回退，改动有记录"。

## Q：这个改动会破坏现有测试吗？

A：

不会。我保持了向后兼容：
- `ToolResult.output` 保持完整（向后兼容）
- `observation` 是可选字段
- 没有 observation 时，loop 回注逻辑回退到原来的 output 行为
- 现有测试全部通过（916 passed, 3 skipped）
