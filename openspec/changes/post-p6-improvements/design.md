## Context

P0-P6 完成后，项目功能完整。对比 pico 项目发现三个小但有价值的改进点：
- bash 工具调用 `subprocess.run` 时未传 `env` 参数，继承全部环境变量（含 API_KEY 等敏感信息）
- pyproject.toml 已有但缺 `[project.scripts]`，无法 `pip install` 后直接用 `agent` 命令
- mimo API 兼容 Anthropic 协议，可能支持 prompt cache，未利用

## Goals / Non-Goals

**Goals:**
- bash 执行时只传递安全的环境变量子集
- `pip install .` 后能用 `agent` 命令启动
- 如果 API 支持，利用 prompt cache 减少重复 token 计算

**Non-Goals:**
- 不做完整的环境变量配置化（白名单硬编码即可）
- 不做命令行参数解析重构（现有 argparse 够用）
- 不做 prompt cache 的命中率统计（先做基础功能）

## Decisions

### D1: Shell env 白名单 — 硬编码白名单而非配置文件

**选择：** 在 bash.py 中定义 `SAFE_ENV_VARS` 集合，执行时过滤。

**替代方案：**
- A) 配置文件定义白名单 — 增加复杂度，目前无此需求
- B) 黑名单模式（排除敏感变量）— 容易遗漏，不安全

**白名单变量（14 个）：**
```
HOME, USER, PATH, SHELL, LANG, LC_ALL, TERM,
PWD, TMPDIR, TEMP, TMP, XDG_RUNTIME_DIR,
COMSPEC, SYSTEMROOT  # Windows 必需
```

**理由：** 白名单模式 fail-closed，新增变量默认不传递。硬编码足够，不需要配置化。

### D2: CLI 入口 — console_scripts 而非 __main__.py

**选择：** 在 pyproject.toml 添加 `[project.scripts]`，指向 `agent.cli.app:main`。

**替代方案：**
- A) 只用 `python -m agent` — 需要 `__main__.py`，用户体验差
- B) 两者都做 — 可以，但 console_scripts 是标准做法

**理由：** `pip install .` 后自动生成 `agent` 命令，最符合 Python CLI 工具惯例。

### D3: Prompt Cache — 先验证 API 支持再实现

**选择：** 在 MimoClient 的 chat_stream 中，对 system prompt 做 SHA-256 哈希，作为 cache_key 传给 API。

**替代方案：**
- A) 不做，等 API 文档确认 — 保守但慢
- B) 做客户端缓存（相同 prompt 不重复发送）— 没有意义，API 已经处理

**实现位置：**
- `core/model.py`：MimoClient 新增 `_compute_cache_key()` 方法
- `core/loop.py`：调用 chat_stream 时传入 system prompt

**风险：** mimo API 可能不支持 `prompt_cache_key`。实现时做 graceful degradation——传了不支持的参数不报错即可。

## Risks / Trade-offs

**[R1] env 白名单可能漏掉用户需要的变量**
→ 缓解：白名单包含 14 个常用变量。如果用户需要额外变量，后续可以扩展为可配置。

**[R2] mimo API 不支持 prompt cache**
→ 缓解：传 cache_key 作为额外参数，不支持时 API 忽略即可。不支持也不会报错。

**[R3] console_scripts 入口指向的模块路径可能不对**
→ 缓解：需要确认 `agent.cli.app:main` 是否存在，可能需要调整。
