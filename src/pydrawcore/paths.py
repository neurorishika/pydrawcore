from __future__ import annotations

import os
from pathlib import Path


DEFAULT_CONFIG_DIRNAME = ".drawcore"
DEFAULT_MOTION_PROFILE_NAME = "motion.json"
DEFAULT_WORKSPACE_PROFILE_NAME = "workspace.json"
DEFAULT_DEVICE_MODEL_MAP_NAME = "devices.json"
CONFIG_DIR_ENV_VAR = "PYDRAWCORE_CONFIG_DIR"


def resolve_config_dir(config_dir: str | None = None) -> Path:
    configured = config_dir or os.environ.get(CONFIG_DIR_ENV_VAR)
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / DEFAULT_CONFIG_DIRNAME).resolve()


def default_motion_profile_path(config_dir: str | None = None) -> Path:
    return resolve_config_dir(config_dir) / DEFAULT_MOTION_PROFILE_NAME


def default_workspace_profile_path(config_dir: str | None = None) -> Path:
    return resolve_config_dir(config_dir) / DEFAULT_WORKSPACE_PROFILE_NAME


def default_device_model_map_path(config_dir: str | None = None) -> Path:
    return resolve_config_dir(config_dir) / DEFAULT_DEVICE_MODEL_MAP_NAME


def ensure_config_dir(config_dir: str | None = None) -> Path:
    resolved = resolve_config_dir(config_dir)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved