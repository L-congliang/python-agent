## 1. Shell 环境变量白名单

- [x] 1.1 在 `tools/bash.py` 定义 `SAFE_ENV_VARS` 常量（14 个安全变量）
- [x] 1.2 新增 `_build_safe_env()` 函数，从 `os.environ` 过滤白名单变量
- [x] 1.3 修改 `execute_bash()` 中的 `subprocess.run` 调用，传入 `env` 参数
- [x] 1.4 编写测试：白名单变量传递、敏感变量排除、Windows 变量保留
- [x] 1.5 运行 `uv run pytest tests/ -x -v` 验证

## 2. CLI 入口点

- [x] 2.1 确认 `agent.main:main` 函数签名和入口逻辑
- [x] 2.2 在 `pyproject.toml` 添加 `[project.scripts]` 配置
- [x] 2.3 运行 `uv sync` 后测试 `agent` 命令是否可用
- [x] 2.4 运行 `uv run make check` 验证

## 3. Prompt Cache ⏭️ 跳过

mimo API 不支持 prompt caching（测试验证：接受参数但不返回缓存指标，无实际效果）。

- [x] 3.1 验证 mimo API 是否支持 `prompt_cache_key` 参数 → 不支持
- ~~3.2 - 3.6~~ 跳过
