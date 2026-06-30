## ADDED Requirements

### Requirement: MCP 工具描述

系统 SHALL 支持将内部工具转换为 MCP 格式的工具描述。MCP 描述包含：name、description、inputSchema（JSON Schema）。

#### Scenario: 转换单个工具

- **WHEN** 将 read_file 工具转换为 MCP 格式
- **THEN** 输出包含 name="read_file"、description、inputSchema

#### Scenario: 转换所有工具

- **WHEN** 调用 to_mcp_tools() 传入所有内部工具
- **THEN** 返回 MCP 格式的工具列表

### Requirement: MCP Server

系统 SHALL 实现 MCP Server，让其他 MCP 客户端可以调用本 agent 的工具。Transport 使用 stdio（JSON-RPC over stdin/stdout）。

#### Scenario: 启动 MCP Server

- **WHEN** 运行 `agent --mcp-server`
- **THEN** 启动 MCP Server，监听 stdin

#### Scenario: 响应工具列表请求

- **WHEN** 客户端发送 tools/list 请求
- **THEN** 返回所有可用工具的 MCP 描述

#### Scenario: 响应工具调用

- **WHEN** 客户端发送 tools/call 请求
- **THEN** 执行工具并返回结果

### Requirement: MCP Client

系统 SHALL 实现 MCP Client，让本 agent 可以调用第三方 MCP Server 的工具。

#### Scenario: 连接 MCP Server

- **WHEN** 配置 mcp_servers=[{"command": "npx", "args": ["-y", "@anthropic/mcp-filesystem"]}]
- **THEN** 启动 MCP Server 子进程，建立 stdio 连接

#### Scenario: 调用第三方工具

- **WHEN** agent 需要使用第三方 MCP Server 的工具
- **THEN** 通过 MCP Client 发送 tools/call 请求

#### Scenario: 第三方工具失败

- **WHEN** 第三方 MCP Server 返回错误
- **THEN** 错误信息注入到消息历史，agent 可以重试或换工具

### Requirement: 协议兼容性

系统 SHALL 兼容 MCP 协议版本 2024-11-05。支持的方法：initialize、tools/list、tools/call。

#### Scenario: 版本协商

- **WHEN** 客户端发送 initialize 请求，version="2024-11-05"
- **THEN** 服务器确认版本兼容

#### Scenario: 不支持的版本

- **WHEN** 客户端发送 initialize 请求，version="99.0.0"
- **THEN** 服务器返回版本不兼容错误
