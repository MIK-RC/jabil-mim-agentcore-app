import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

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
    
def get_agent_config(agent_type: str) -> dict:
    """Get the configuration for a specific agent type."""
    filepath = _get_config_dir() / "agents.yaml"
    
    if not filepath.exists():
        raise FileNotFoundError(
            f"agents.yaml not found at {filepath}. "
            "This file is required for agent initialization."
        )
    
    return _load_yaml("agents.yaml").get(agent_type, {})

def load_settings() -> dict[str, Any]:
    """Load all settings from the configuration files."""
    return {
        "agents": _load_yaml("agents.yaml"),
        "models": _load_yaml("models.yaml")
    }
