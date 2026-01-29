"""File utility functions for DCM file discovery and processing."""
import os
from pathlib import Path
from typing import Generator, Optional


def list_files(directory: str) -> Generator[str, None, None]:
    """Recursively walk directory and yield all file paths.

    Args:
        directory: Root directory to walk

    Yields:
        Absolute file paths
    """
    for root, directories, files in os.walk(directory):
        for filename in files:
            yield os.path.join(root, filename)


def identify_dcm(path: str) -> Optional[str]:
    """Check if file is a DCM file by extension.

    Args:
        path: File path to check

    Returns:
        The filepath if extension is '.dcm' (case-insensitive), otherwise None
    """
    if os.path.splitext(path)[1].lower() == '.dcm':
        return path
    return None


def get_stl_output_path(dcm_input_path: str) -> str:
    """Generate STL output path from DCM input path.

    Args:
        dcm_input_path: Path to input DCM file

    Returns:
        Path to output STL file (same directory and name, different extension)

    Example:
        >>> get_stl_output_path('/path/to/scan.dcm')
        '/path/to/scan.stl'
    """
    base_path = os.path.splitext(dcm_input_path)[0]
    return f"{base_path}.stl"


def filter_target_files(file_list: list[str], target_filenames: list[str]) -> list[str]:
    """Filter file list to only include target filenames.

    Args:
        file_list: List of full file paths
        target_filenames: List of filenames to match (basename only)

    Returns:
        Filtered list of paths whose basenames match target_filenames

    Example:
        >>> files = ['/a/b/foo.dcm', '/a/b/bar.dcm']
        >>> targets = ['foo.dcm']
        >>> filter_target_files(files, targets)
        ['/a/b/foo.dcm']
    """
    return [
        filepath for filepath in file_list
        if os.path.basename(filepath) in target_filenames
    ]
