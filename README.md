# PulseNode

PulseNode is an agentic system that processes messages from multiple channels (Telegram, email, file, etc.) using LLMs with tool-calling capabilities.

## Architecture Overview

PulseNode uses a modular architecture with several key components:

- **Agent**: Main runtime that processes messages through triage and execution
- **Memory Management**: Three-tier memory system (agent, channel, session)
- **Tool System**: Secure tool execution with approval workflows
- **MCP Integration**: Connects to LLM providers via MCP protocol

## Configuration

Configuration is managed through:
- `Settings` class: System-wide settings (heartbeat interval, memory limits, etc.)
- `agents.yaml`: Defines which agents to run at startup with their channels and LLM configs
- Per-agent `config.yaml`: Agent-specific settings (tools, permissions, session config)

## Class Reference

### Agent Core

#### `main.Agent`
Main runtime class that processes messages from channels. Uses a heartbeat loop to poll channels, triage incoming messages, and execute tasks using the capable LLM with tool support.

#### `main.Context`
Simple context dataclass holding the current timestamp. Used for time-sensitive operations.

#### `main.ChannelMcp` (Protocol)
Protocol defining the interface for channel implementations. Channels must implement `receive_messages()` async generator.

#### `loader.AgentLoader`
Loads agents from `agents.yaml` configuration. Creates channel instances, LLM clients, and assembles configured Agent instances.

### Configuration

#### `AgentConfig`
Dataclass holding all configuration for an agent:
- `name`, `purpose`: Identity
- `session_config`: Session management settings
- `tools`: Tool permissions (shell, file, http)
- `llm`: LLM configuration (mcp_url, models, tokens)
- `channels`: Channel definitions

#### `AgentConfigManager`
Manages loading and saving agent configurations from YAML files in `~/.pulsenode/agents/{name}/`.

#### `LlmConfig`
LLM configuration for an agent:
- `mcp_url`: MCP server endpoint
- `auth_token`: Authentication token
- `triage_model`, `capable_model`: Model names for triage vs capable LLMs
- `triage_max_tokens`, `capable_max_tokens`: Token limits

#### `ChannelDefinition`
Channel configuration:
- `type`: Channel type (file, telegram, email)
- `identifier`: Channel identifier
- `file_path`: For file channels
- `sleep_seconds`: Polling interval

#### `Settings` (config/settings.py)
System-wide settings (Pydantic BaseSettings):
- `heartbeat_interval_seconds`: How often to check for new messages
- `pulsenode_directory`: Base data directory (default: ~/.pulsenode)
- Memory limits: max_agent_memory_chars, max_channel_memory_chars, etc.
- Tool settings: tools_enabled, default_workspace_dir, etc.

#### `LLMProxyConfig`
LLM proxy server configuration:
- `enabled`: Enable/disable proxy
- `provider_default`: Default provider (ollama or llamacpp)
- `endpoint`: Base URL for provider
- `model`: Default model name

### Sessions & Memory

#### `SessionManager`
Manages sessions, memory, and file system operations:
- `get_or_create_session()`: Get or create session for agent/channel
- `get_agent_memory()`: Get cross-channel agent memory
- `get_channel_memory()`: Get channel-specific memory
- `_ensure_agent_dir()`: Ensure agent directories exist

#### `Session`
Represents a conversation session with:
- `session_id`: Unique identifier (channel:identifier:time)
- `messages`: List of Message objects
- File paths: session_file, agent_memory_path, channel_memory_path

#### `SessionConfig`
Session management configuration:
- `session_mode`: time_based or thread_based
- `time_granularity`: daily or weekly
- `min_messages_threshold`: Messages before archive consideration

#### `Message`
Simple dataclass with `role` (user/agent) and `content`.

#### `MemoryManager`
High-level memory management providing `get_context_for_llm()` which aggregates:
- Agent memory (cross-channel knowledge)
- Channel memory (channel-specific facts)
- Session summary (recent messages)

#### `MemoryTools`
Tools for LLM to manage memory:
- `update_agent_memory()`: Add facts to agent memory
- `update_channel_memory()`: Add facts to channel memory
- `query_archivedsessions()`: Search past sessions

### Tool System

#### `ToolExecutor`
Executes tool calls with security checks and approval handling.

#### `SecurityChecker`
Validates tool operations:
- Shell: Command allowlist
- File: Directory restrictions, sensitive file detection
- HTTP: Host allowlist/blocklist

#### `ApprovalManager`
Manages approval workflow for high-risk operations with timeout support.

#### `ToolRegistry`
Manages available tools and parses LLM tool calls. Registers tool definitions for LLM prompts.

#### `ToolCall`
Dataclass representing a tool call request:
- `tool_type`: shell, file, http
- `action`: exec, read, write, get, etc.
- `args`: Tool arguments

#### `ToolResult`
Result of tool execution:
- `success`: Boolean success flag
- `output`: Result text
- `error`: Error message if failed
- `execution_time`: Time taken

#### `ApprovalRequest`
Pending approval request with risk assessment.

#### `HttpTool`
HTTP request execution with:
- Host allowlist/blocklist
- Timeout configuration
- Metrics tracking

#### `ToolCallParser` (ABC)
Abstract base for parsing LLM tool calls. See `OpenAIToolCallParser`.

#### `OpenAIToolCallParser`
Parser for OpenAI-style function calling format.

### LLM Integration

#### `LlmMcp` (agent/llm_mcp.py)
Client for LLM via MCP protocol:
- `generate_triage_response()`: Quick triage decision
- `generate_response()`: Full response with optional tool calling

#### `TriageResponse`
Response from triage LLM with `needed` (bool) and `reason` (str).

#### `LlmResponse`
Response from capable LLM with `content` (str) and `tool_calls` (list).

#### `OllamaClient`
HTTP client for Ollama provider.

#### `LlamaCppClient`
HTTP client for llama.cpp server.

#### `LLMProxyServer`
MCP server that proxies LLM requests to configured providers (Ollama or llama.cpp). Supports chat completions and tool calling.

### Channels

#### `FileChannelMcp`
File-based channel for debugging. Reads messages from a text file:
- `+++` separates message batches
- `---` separates individual messages within a batch

### Models

#### `ChannelMCP` (ABC)
Abstract base class for channel implementations.

## Directory Structure

```
~/.pulsenode/
├── agents.yaml              # Agent list to run at startup
├── agents/
│   ├── {agent_name}/
│   │   ├── config.yaml     # Agent-specific config
│   │   ├── purpose.md      # Agent purpose definition
│   │   ├── agent_memory.md # Cross-channel memory
│   │   └── channels/
│   │       └── {channel_type}/
│   │           └── {identifier}/
│   │               ├── long_term_memory.md
│   │               └── sessions/
│   │                   ├── current.md
│   │                   ├── index.json
│   │                   └── archived/
└── system_capabilities.json # Available tools/capabilities
```

## Usage

1. Copy `sample_agents.yaml` to `~/.pulsenode/agents.yaml`
2. Customize agent configurations
3. Run the agent: `python -m pulsenode.agent.main`

## Environment Variables

Settings can be overridden via environment variables:
- `LLM_PROXY_*`: LLM proxy configuration
- Other settings: See `Settings` class documentation
