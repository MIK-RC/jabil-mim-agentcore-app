"""
Configuration Loader Module

Simple functions to load YAML configuration files.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

# Cached raw configs
_raw_configs: dict[str, dict] = {}
_config_dir: Path | None = None


def _get_config_dir() -> Path:
    """Resolve the configuration directory path."""
    global _config_dir

    if _config_dir is not None:
        return _config_dir

    # Try environment variable
    env_config_dir = os.environ.get("AIOPS_CONFIG_DIR")
    if env_config_dir:
        _config_dir = Path(env_config_dir)
        return _config_dir

    # Walk up from current file to find config directory
    current = Path(__file__).parent
    while current != current.parent:
        config_path = current / "config"
        if config_path.exists():
            _config_dir = config_path
            return _config_dir
        current = current.parent

    # Fallback to relative path
    _config_dir = Path("config")
    return _config_dir


def _load_yaml(filename: str) -> dict:
    """Load a YAML file and cache it."""
    if filename in _raw_configs:
        return _raw_configs[filename]

    filepath = _get_config_dir() / filename

    if not filepath.exists():
        _raw_configs[filename] = {}
        return {}

    with open(filepath) as f:
        data = yaml.safe_load(f) or {}
        _raw_configs[filename] = data
        return data


def load_settings() -> dict:
    """
    Load settings.yaml as a dictionary.

    Returns:
        Settings configuration dict.

    Usage:
        settings = load_settings()
        region = settings.get("aws", {}).get("region", "us-east-1")
    """
    return _load_yaml("settings.yaml")


def load_tools_config() -> dict:
    """
    Load tools.yaml as a dictionary.

    Returns:
        Tools configuration dict.

    Usage:
        tools = load_tools_config()
        datadog_config = tools.get("datadog", {})
    """
    return _load_yaml("tools.yaml")


def load_agents_config() -> dict:
    """
    Load agents.yaml as a dictionary.

    Returns:
        Agents configuration dict.

    Usage:
        agents = load_agents_config()
        orchestrator = agents.get("orchestrator", {})
    """
    return _load_yaml("agents.yaml")


def get_agent_config(agent_name: str) -> dict:
    """
    Get configuration for a specific agent.

    Args:
        agent_name: Name of the agent (orchestrator, datadog, coding, servicenow, s3).

    Returns:
        Agent configuration dict with defaults applied.

    Usage:
        config = get_agent_config("orchestrator")
        model_id = config.get("model_id")
    """
    agents = load_agents_config()
    defaults = agents.get("defaults", {})
    agent_config = agents.get(agent_name, {})

    # Merge defaults with agent-specific config
    result = {**defaults, **agent_config}

    # Ensure required fields have defaults
    result.setdefault("name", agent_name)
    result.setdefault("description", f"{agent_name} agent")
    result.setdefault("model_id", "us.anthropic.claude-sonnet-4-20250514-v1:0")
    result.setdefault("max_tokens", 4096)
    result.setdefault("system_prompt", "")

    return result


def reload_configs() -> None:
    """Clear cached configs to force reload on next access."""
    global _raw_configs
    _raw_configs.clear()


# =============================================================================
# Pydantic Models (for backward compatibility with existing code)
# =============================================================================


class AgentConfig(BaseModel):
    """Configuration for a single agent."""

    name: str
    description: str = ""
    model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    max_tokens: int = 4096
    system_prompt: str = ""


# =============================================================================
# Legacy ConfigLoader class (for backward compatibility)
# =============================================================================


class ConfigLoader:
    """
    Legacy configuration loader class.

    Kept for backward compatibility. New code should use the simple functions:
    - load_settings()
    - load_tools_config()
    - load_agents_config()
    - get_agent_config(name)
    """

    _instance: "ConfigLoader | None" = None

    def __new__(cls, config_dir: str | None = None) -> "ConfigLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_dir: str | None = None):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

    @property
    def settings(self) -> Any:
        """Get settings as an object with attribute access."""
        return _DictWrapper(load_settings())

    @property
    def tools(self) -> Any:
        """Get tools config as an object with attribute access."""
        return _DictWrapper(load_tools_config())

    @property
    def agents(self) -> Any:
        """Get agents config as an object with attribute access."""
        return _DictWrapper(load_agents_config())

    def get_agent_config(self, agent_name: str) -> AgentConfig:
        """Get typed agent configuration."""
        config = get_agent_config(agent_name)
        return AgentConfig(**config)

    def get_raw_config(self, config_name: str) -> dict:
        """Get raw configuration dictionary."""
        if config_name == "settings":
            return load_settings()
        elif config_name == "tools":
            return load_tools_config()
        elif config_name == "agents":
            return load_agents_config()
        return {}

    def reload(self) -> None:
        """Reload all configurations."""
        reload_configs()


class _DictWrapper:
    """Wrapper to allow dict access via attributes."""

    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        value = self._data.get(name)
        if isinstance(value, dict):
            return _DictWrapper(value)
        return value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


def get_config(config_dir: str | None = None) -> ConfigLoader:
    """
    Get the configuration loader instance.

    For new code, prefer using the simple functions directly:
    - load_settings()
    - load_tools_config()
    - load_agents_config()
    - get_agent_config(name)
    """
    return ConfigLoader(config_dir)
