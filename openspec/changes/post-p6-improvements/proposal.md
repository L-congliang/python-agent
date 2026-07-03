## Why

P0-P6 已完成，项目功能完整。但对比 pico（同类型项目）发现三个可快速补齐的改进：bash 工具泄露全部环境变量（含 API_KEY）、缺少标准 Python 入口点、未利用 API 的 prompt cache 能力。三个改动总计 ~40 行，投入产出比高。

## What Changes

- **Shell 环境变量白名单**：bash 工具的 subprocess.run 当前继承全部环境变量，需过滤为安全子集
- **CLI 入口点**：pyproject.toml 已有但缺 `[project.scripts]`，需添加 `agent` 命令入口
- **Prompt Cache**：对 system prompt 做 SHA-256 哈希，传给 API 做 server-side 缓存（需验证 mimo API 是否支持）

## Capabilities

### New Capabilities

- `shell-env-sandbox`: Shell 环境变量沙箱 — 定义安全 env var 白名单，bash 执行时只传递白名单内的变量
- `cli-entry`: CLI 入口点 — pyproject.toml 添加 console_scripts，支持 `agent` 命令直接启动
- `prompt-cache`: Prompt 缓存 — system prompt 哈希 + API cache_key 参数，减少重复计算

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- **代码**：`tools/bash.py`（env 白名单）、`core/model.py`（cache key）、`core/loop.py`（传递 cache key）、`pyproject.toml`（入口点）
- **测试**：新增 env 白名单测试、cache key 生成测试
- **依赖**：无新增依赖
- **风险**：mimo API 可能不支持 prompt_cache_key，需先验证
