"""Windows Registry management for conversion mode settings.

This module manages the conversion mode setting stored in Windows Registry.
Registry path: HKEY_CURRENT_USER\\Software\\CreoDent Prosthetics
"""
import winreg
from typing import Literal


REGISTRY_PATH = r'Software\CreoDent Prosthetics'
MODE_KEY = 'mode'


class RegistryConfigError(Exception):
    """Exception raised for registry configuration errors."""
    pass


def initialize_registry() -> None:
    """Create registry key if it doesn't exist, with default mode '0'.

    Raises:
        RegistryConfigError: If registry operations fail
    """
    try:
        # Try to create the key (does nothing if already exists)
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH)

        # Check if mode value exists
        try:
            winreg.QueryValueEx(key, MODE_KEY)
        except FileNotFoundError:
            # Mode doesn't exist, create it with default value '0'
            winreg.SetValueEx(key, MODE_KEY, 0, winreg.REG_SZ, '0')

        winreg.CloseKey(key)
    except Exception as e:
        raise RegistryConfigError(f"Failed to initialize registry: {e}")


def get_mode() -> Literal['0', '1']:
    """Get the current conversion mode from registry.

    Returns:
        '0' for convert all DCM files, '1' for convert target files only

    Raises:
        RegistryConfigError: If registry read fails or mode is invalid
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REGISTRY_PATH,
            access=winreg.KEY_READ
        )
        mode, _ = winreg.QueryValueEx(key, MODE_KEY)
        winreg.CloseKey(key)

        if mode not in ('0', '1'):
            raise RegistryConfigError(f"Invalid mode value in registry: {mode}")

        return mode
    except FileNotFoundError:
        # Registry key doesn't exist, initialize it
        initialize_registry()
        return '0'
    except Exception as e:
        raise RegistryConfigError(f"Failed to read mode from registry: {e}")


def set_mode(mode: Literal['0', '1']) -> None:
    """Set the conversion mode in registry.

    Args:
        mode: '0' for convert all, '1' for convert target files only

    Raises:
        RegistryConfigError: If mode is invalid or registry write fails
    """
    if mode not in ('0', '1'):
        raise RegistryConfigError(f"Invalid mode: {mode}. Must be '0' or '1'")

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REGISTRY_PATH,
            access=winreg.KEY_WRITE
        )
        winreg.SetValueEx(key, MODE_KEY, 0, winreg.REG_SZ, mode)
        winreg.CloseKey(key)
    except FileNotFoundError:
        # Registry key doesn't exist, initialize and retry
        initialize_registry()
        set_mode(mode)
    except Exception as e:
        raise RegistryConfigError(f"Failed to write mode to registry: {e}")


def toggle_mode() -> Literal['0', '1']:
    """Toggle between conversion modes.

    Returns:
        The new mode value after toggling

    Raises:
        RegistryConfigError: If registry operations fail
    """
    current_mode = get_mode()

    if current_mode == '0':
        new_mode = '1'
    elif current_mode == '1':
        new_mode = '0'
    else:
        raise RegistryConfigError(f"Invalid current mode: {current_mode}")

    set_mode(new_mode)
    return new_mode
