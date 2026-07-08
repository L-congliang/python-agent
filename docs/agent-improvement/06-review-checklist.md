# 评审清单

## 入口和 README

- `main.py` 的装配函数是否还存在
- `README.md` 是否仍与真实代码一致
- 是否又把未实现能力写进 README

## 默认入口

- `create_default_registry()` 是否仍注册基础工具
- `create_agent_loop()` 是否仍能构建默认 runtime
- `create_agent_app()` 是否仍挂载 confirmation handler

## CLI 行为

- `/reset` 是否仍调用真实 loop reset
- `/compact` 是否仍调用真实 loop compact
- 非 UTF-8 fallback 是否仍可启动

## 权限和安全

- `ASK` 是否仍需确认
- 无 handler 时是否仍 fail-closed
- `write` 是否仍默认不覆盖
- `edit` 是否仍有 preview
- workspace guard 是否仍覆盖搜索类工具

## 文档真实性

- fake-model e2e 是否被误写成真实 LLM e2e
- 是否把当前项目写成生产级
- 是否把 Nanobot 写成自己做的
