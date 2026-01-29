"""DCM to STL Autoconverter - Convert 3Shape DCM files to STL format.

This package provides both GUI and CLI interfaces for converting dental scan
files from 3Shape DCM format to STL format using the Delcam SDX COM interface.

Main modules:
    - core: Conversion logic and SDX interface
    - config: Configuration and registry management
    - gui: CustomTkinter GUI application
    - cli: Command-line interface

Example:
    >>> from dcm_to_stl import DCMConverter
    >>> converter = DCMConverter(mode='0')
    >>> converter.convert_directory('/path/to/dcm/files')
"""
from .core import (
    DCMConverter,
    ConversionMode,
    SDXInterface,
    SDXError,
    convert_directory_simple
)
from .config import (
    get_mode,
    set_mode,
    toggle_mode,
    get_target_filenames
)

__version__ = '1.0.0'
__author__ = 'CreoDent Prosthetics'

__all__ = [
    'DCMConverter',
    'ConversionMode',
    'SDXInterface',
    'SDXError',
    'convert_directory_simple',
    'get_mode',
    'set_mode',
    'toggle_mode',
    'get_target_filenames',
]
