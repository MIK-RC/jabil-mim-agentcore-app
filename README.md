# jabil-mim-agentcore-app

## Setup

- *Requirements*: Python Version = 3.12

```bash
# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your credentials
```

## Architecture & Flow

### Agent Initialization

When an agent is instantiated (e.g., `ServiceNowAgent()` or `OrchestratorAgent()`):

1. **Configuration Loading** (`config_loader.py`)
   - Validates that `agents.yaml` exists in the `config/` directory
   - If missing, raises `FileNotFoundError` with clear message
   - Loads agent-specific configuration from `agents.yaml` using `get_agent_config(agent_type)`
   - Returns configuration as a plain dictionary (no validation overhead)
   - Settings include: `name`, `description`, `model_id`, `max_tokens`, `system_prompt`

2. **Base Agent Setup** (`base.py`)
   - Generates unique agent ID: `{agent_type}-{uuid}`
   - Stores configuration as plain dict in `self._config`
   - Initializes logger with agent-specific name and ID
   - Creates `AgentState` for tracking invocations and action history

3. **Bedrock Model Initialization**
   - Configures AWS Bedrock model with specified or default `model_id`
   - Uses region from settings or defaults to `us-east-1`
   - Creates `BedrockModel` instance for LLM operations

4. **Strands Agent Creation**
   - Calls `get_tools()` method (implemented by each agent subclass)
   - Creates Strands `Agent` with:
     - Configured Bedrock model
     - System prompt from config
     - Agent-specific tools
     - Agent name and description
     - Optional session manager for persistence

### Agent Invocation Flow

When `agent.invoke(message)` is called:

1. **Pre-Invocation**
   - Records start time
   - Logs invocation with truncated message preview

2. **Execution**
   - Passes message to underlying Strands agent (`self._agent(message)`)
   - Strands agent processes with LLM and available tools
   - Tools are executed as needed by the agent

3. **Post-Invocation**
   - Calculates execution duration
   - Records action in history via `record_action()`:
     - Action type, description
     - Input/output summaries (truncated to 500 chars)
     - Success/failure status
     - Duration in milliseconds
   - Updates agent state metrics:
     - `total_invocations`
     - `successful_invocations` or `failed_invocations`
     - `last_activity` timestamp
   - Returns response as string

4. **Error Handling**
   - On exception: records failed action with error message
   - Logs error and re-raises exception

### Tool System

Tools are **Python functions**:

- Defined in `src/tools/` using `@tool` decorator from Strands SDK
- Each agent imports specific tools (e.g., `create_incident`, `search_incidents`)
- Returned as a list from agent's `get_tools()` method
- Passed to Strands Agent during initialization
- Example: `ServiceNowAgent` provides ServiceNow-specific tools
- If new service requires tools, a file can be created with abstract tools and imported where needed.

### Configuration Structure

**agents.yaml** - Agent configurations:
```yaml
servicenow:
  name: "ServiceNow Agent"
  description: "Handles ServiceNow incident operations"
  model_id: "us.anthropic.claude-sonnet-4-20250514-v1:0"
  max_tokens: 4096
  system_prompt: "You are a ServiceNow specialist..."
```

**models.yaml** - Additional model configurations (optional)

### State Tracking

Each agent maintains state via `AgentState`:
- Unique agent ID and name
- Creation and last activity timestamps
- Complete action history with detailed metrics
- Success/failure counters
- Accessible via `agent.state` property

### Design Principles

- **Zero validation overhead**: Plain dicts instead of Pydantic models (CI handles validation)
- **Required config file**: `agents.yaml` must exist or initialization fails immediately
- **Action tracking**: Full audit trail of all agent invocations
- **Logging**: Structured logs with agent ID for traceability
- **Tool isolation**: Each agent only has access to its specific tools
