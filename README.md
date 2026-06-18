# Python Agent

学习 Claude Code 架构的 Python Agent 实现。

## 项目结构

```
python-agent/
├── src/agent/
│   ├── core/          # 核心模块
│   │   ├── types.py   # 类型定义
│   │   ├── loop.py    # Agent 主循环
│   │   └── state.py   # 状态管理
│   ├── tools/         # 工具实现
│   │   ├── base.py    # Tool 基类
│   │   └── ...        # 具体工具
│   ├── permissions/   # 权限系统
│   └── context/       # 上下文管理
├── tests/             # 测试
└── examples/          # 使用示例
```

## 核心概念

### 1. Tool 接口
所有工具都实现 `Tool` Protocol，提供统一的调用方式。

### 2. 主循环
`loop.py` 实现 Agent 的核心运行逻辑：
- 调用 LLM
- 解析工具调用
- 执行工具
- 返回结果
- 循环直到完成

### 3. 错误处理
工具执行失败时，通过 `is_error` 标记让 LLM 自我修正。

## 学习路径

本项目按照 Claude Code 源码学习，逐步实现：

- [x] 类型定义
- [ ] Tool 接口
- [ ] 主循环
- [ ] 错误处理
- [ ] 上下文压缩
- [ ] 并发执行
- [ ] 权限系统
- [ ] 子 Agent

## 运行示例

```bash
# 安装依赖
pip install -e .

# 运行示例
python examples/demo.py
```

## 参考

- [Claude Code 源码](https://github.com/anthropics/claude-code)
