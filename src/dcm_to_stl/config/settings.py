"""Settings and resource path management.

This module handles loading configuration files and resolving resource paths
for both development and PyInstaller-bundled modes.
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict


def get_resource_path(relative_path: str) -> Path:
    """Get absolute path to resource, works for dev and PyInstaller bundled modes.

    When running from source, resources are in the resources/ directory.
    When running as PyInstaller bundle, resources are in sys._MEIPASS.

    Args:
        relative_path: Relative path from resource root (e.g., 'icons/icon.ico')

    Returns:
        Absolute path to the resource

    Example:
        >>> get_resource_path('icons/icon.ico')
        Path('C:/path/to/resources/icons/icon.ico')  # in dev mode
        Path('C:/Temp/_MEI.../icons/icon.ico')  # in bundled mode
    """
    if hasattr(sys, '_MEIPASS'):
        # Running as PyInstaller bundle
        base_path = Path(sys._MEIPASS)
    else:
        # Running from source - go up to project root then to resources
        # Current file: src/dcm_to_stl/config/settings.py
        # Project root: ../../.. from here
        base_path = Path(__file__).parent.parent.parent.parent / 'resources'

    return base_path / relative_path


def load_target_config(config_path: Optional[str] = None) -> Dict[int, str]:
    """Load target configuration file.

    Args:
        config_path: Optional custom path to config file. If None, uses default location.

    Returns:
        Dictionary mapping numbers to target DCM filenames

    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If config file is invalid JSON
    """
    if config_path is None:
        config_path = get_resource_path('config/target_config.ini')
    else:
        config_path = Path(config_path)

    with open(config_path, 'r') as f:
        return json.load(f)


def get_target_filenames(config_path: Optional[str] = None) -> list[str]:
    """Get list of target DCM filenames from configuration.

    Args:
        config_path: Optional custom path to config file

    Returns:
        List of target DCM filenames (e.g., ['PrePreparationScan.dcm', ...])
    """
    config = load_target_config(config_path)
    return list(config.values())


def get_icon_path(icon_name: str = 'icon.ico') -> Path:
    """Get path to application icon file.

    Args:
        icon_name: Icon filename (default: 'icon.ico')

    Returns:
        Absolute path to icon file

    Raises:
        FileNotFoundError: If icon doesn't exist
    """
    icon_path = get_resource_path(f'icons/{icon_name}')

    if not icon_path.exists():
        raise FileNotFoundError(f"Icon not found: {icon_path}")

    return icon_path


def get_mode_ini_path() -> Path:
    """Get path to legacy mode.ini file (for reference/migration).

    Note: Mode is now stored in Windows Registry, but this function is kept
    for backwards compatibility during migration.

    Returns:
        Path to mode.ini file
    """
    return get_resource_path('config/mode.ini')
