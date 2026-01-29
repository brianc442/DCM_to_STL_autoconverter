"""Target configuration file generator for DCM to STL Autoconverter.

This module creates the target_config.ini file that lists common DCM filenames
to convert in selective mode (mode 1).
"""
import json
from pathlib import Path


def generate_target_config(output_path: str = None) -> dict:
    """Generate the default target configuration.

    Args:
        output_path: Optional path to write the config file. If None, only returns dict.

    Returns:
        Dictionary mapping numbers to target DCM filenames.
    """
    config = {
        1: "PrePreparationScan.dcm",
        2: "Raw Preparation scan.dcm",
        3: "PreparationScan.dcm",
        4: "AntagonistScan.dcm",
        5: "Raw Antagonist scan.dcm",
        6: "AbutmentAlignmentScan.dcm",
        7: "Raw Bite scan.dcm",
        8: "Raw Bite scan2.dcm"
    }

    if output_path:
        output_file = Path(output_path)
        with open(output_file, 'w') as f:
            json.dump(config, f, indent="")

    return config


if __name__ == "__main__":
    # Generate target_config.ini in current directory when run as script
    generate_target_config('target_config.ini')
    print("Generated target_config.ini")
