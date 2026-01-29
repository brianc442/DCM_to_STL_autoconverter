"""Configuration management."""
from .registry import (
    get_mode,
    set_mode,
    toggle_mode,
    initialize_registry,
    RegistryConfigError
)
from .settings import (
    get_resource_path,
    load_target_config,
    get_target_filenames,
    get_icon_path,
    get_mode_ini_path
)
from .target_config import generate_target_config

__all__ = [
    'get_mode',
    'set_mode',
    'toggle_mode',
    'initialize_registry',
    'RegistryConfigError',
    'get_resource_path',
    'load_target_config',
    'get_target_filenames',
    'get_icon_path',
    'get_mode_ini_path',
    'generate_target_config',
]
