"""Core conversion logic for DCM to STL conversion.

This module consolidates the conversion logic previously duplicated
between gui.py and main.py.
"""
import os
from enum import Enum
from typing import Optional, Callable, List
from .sdx_interface import SDXInterface, SDXError
from .file_utils import list_files, identify_dcm, get_stl_output_path, filter_target_files


class ConversionMode(Enum):
    """Conversion mode enum."""
    ALL_FILES = '0'  # Convert all DCM files found
    TARGET_ONLY = '1'  # Convert only target files from config


class DCMConverter:
    """Handles DCM to STL file conversion operations.

    This class provides the main conversion logic, supporting both
    "convert all" and "selective target" modes.

    Attributes:
        mode: Current conversion mode
        target_filenames: List of target filenames for selective mode
        progress_callback: Optional callback for progress updates
    """

    def __init__(self,
                 mode: str = '0',
                 target_filenames: Optional[List[str]] = None,
                 progress_callback: Optional[Callable[[str], None]] = None):
        """Initialize converter.

        Args:
            mode: Conversion mode ('0' = all, '1' = targets only)
            target_filenames: List of target filenames for mode '1'
            progress_callback: Optional callback function for progress updates
        """
        if mode not in ('0', '1'):
            raise ValueError(f"Invalid mode: {mode}. Must be '0' or '1'")

        self.mode = mode
        self.target_filenames = target_filenames or []
        self.progress_callback = progress_callback

    def _report_progress(self, message: str) -> None:
        """Report progress to callback if available.

        Args:
            message: Progress message
        """
        if self.progress_callback:
            self.progress_callback(message)

    def discover_files(self, directory: str) -> List[str]:
        """Discover DCM files to convert in directory.

        Args:
            directory: Root directory to search

        Returns:
            List of DCM file paths to convert (filtered by mode)

        Raises:
            ValueError: If directory doesn't exist
        """
        if not os.path.exists(directory):
            raise ValueError(f"Directory does not exist: {directory}")

        # Find all DCM files
        all_dcm_files = []
        for filepath in list_files(directory):
            if identify_dcm(filepath):
                all_dcm_files.append(filepath)

        # Filter based on mode
        if self.mode == ConversionMode.ALL_FILES.value:
            return all_dcm_files
        elif self.mode == ConversionMode.TARGET_ONLY.value:
            return filter_target_files(all_dcm_files, self.target_filenames)
        else:
            raise ValueError(f"Invalid mode: {self.mode}")

    def convert_file(self, input_file: str, sdx: SDXInterface) -> None:
        """Convert a single DCM file to STL.

        Args:
            input_file: Path to input DCM file
            sdx: Attached SDX interface

        Raises:
            ValueError: If input file is invalid
            SDXError: If conversion fails
        """
        if not os.path.isfile(input_file):
            raise ValueError(f"Input file does not exist: {input_file}")

        # Generate output path
        output_file = get_stl_output_path(input_file)

        # Convert using SDX
        sdx.convert_file(
            input_file=os.path.abspath(input_file),
            output_file=os.path.abspath(output_file),
            progress_callback=self.progress_callback
        )

    def convert_directory(self, directory: str, sdx_interface: Optional[SDXInterface] = None) -> int:
        """Convert all DCM files in directory (respecting mode).

        Args:
            directory: Root directory to search and convert
            sdx_interface: Optional pre-attached SDX interface. If None, creates temporary connection.

        Returns:
            Number of files successfully converted

        Raises:
            ValueError: If directory is invalid
            SDXError: If SDX operations fail
        """
        # Discover files to convert
        self._report_progress("Discovering DCM files...")
        conversion_list = self.discover_files(directory)

        if not conversion_list:
            self._report_progress("No DCM files found")
            return 0

        self._report_progress(f"Found {len(conversion_list)} DCM file(s) to convert")

        # Use provided SDX or create temporary one
        converted_count = 0
        if sdx_interface and sdx_interface.is_attached:
            # Use existing attached SDX connection
            for input_file in conversion_list:
                try:
                    self.convert_file(input_file, sdx_interface)
                    converted_count += 1
                    self._report_progress(f"Converted {converted_count}/{len(conversion_list)}")
                except Exception as e:
                    self._report_progress(f"Error converting {input_file}: {e}")
                    # Continue with next file instead of aborting
        else:
            # Create temporary SDX connection (legacy behavior)
            with SDXInterface() as sdx:
                self._report_progress("Connected to SDX")

                for input_file in conversion_list:
                    try:
                        self.convert_file(input_file, sdx)
                        converted_count += 1
                        self._report_progress(f"Converted {converted_count}/{len(conversion_list)}")
                    except Exception as e:
                        self._report_progress(f"Error converting {input_file}: {e}")
                        # Continue with next file instead of aborting

        self._report_progress(f"Conversion complete: {converted_count}/{len(conversion_list)} files")
        return converted_count


def convert_directory_simple(directory: str,
                             mode: str = '0',
                             target_filenames: Optional[List[str]] = None) -> int:
    """Simple function interface for directory conversion.

    Convenience function for one-off conversions without creating a converter object.

    Args:
        directory: Directory to search and convert
        mode: Conversion mode ('0' = all, '1' = targets only)
        target_filenames: List of target filenames for mode '1'

    Returns:
        Number of files successfully converted
    """
    converter = DCMConverter(mode=mode, target_filenames=target_filenames)
    return converter.convert_directory(directory)
