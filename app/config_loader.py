import yaml
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")

_config_cache: Dict[str, Any] = {}


def load_workflow_config(workflow_type: str) -> Dict[str, Any]:
    """Load workflow config from YAML. Cached after first load."""
    if workflow_type in _config_cache:
        return _config_cache[workflow_type]

    config_path = os.path.join(CONFIG_DIR, "workflows", f"{workflow_type}.yaml")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"No workflow config found for: {workflow_type}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    _config_cache[workflow_type] = config
    logger.info(f"Loaded config: {workflow_type} v{config.get('workflow', {}).get('version', '?')}")
    return config


def reload_workflow_config(workflow_type: str) -> Dict[str, Any]:
    """Force reload - use this when config file changes. No restart needed."""
    if workflow_type in _config_cache:
        del _config_cache[workflow_type]
    return load_workflow_config(workflow_type)


def list_available_workflows() -> list:
    workflows_dir = os.path.join(CONFIG_DIR, "workflows")
    if not os.path.exists(workflows_dir):
        return []
    return sorted(f.replace(".yaml", "") for f in os.listdir(workflows_dir) if f.endswith(".yaml"))
