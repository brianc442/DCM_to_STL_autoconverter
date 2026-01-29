"""Command-line interface for DCM to STL conversion.

This is a simplified CLI version of the converter that uses the shared
core conversion logic.
"""
import atexit
import sys
from tkinter.filedialog import askdirectory
from ..core.converter import DCMConverter
from ..core.sdx_interface import SDXInterface
from ..config.registry import get_mode
from ..config.settings import get_target_filenames


def progress_callback(message: str) -> None:
    """Print progress messages to console.

    Args:
        message: Progress message to print
    """
    print(f"[PROGRESS] {message}")


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    sdx = None
    try:
        # Initialize persistent SDX connection
        print("Initializing SDX connection...")
        sdx = SDXInterface()
        sdx.attach()
        atexit.register(sdx.detach)
        print("✓ SDX connected")

        # Get directory from user
        print("\nDCM to STL Converter - Select folder")
        directory = askdirectory(title='Select Folder', mustexist=True)

        if not directory:
            print("No folder selected. Exiting.")
            return 1

        # Get mode from registry
        mode = get_mode()
        print(f"Conversion mode: {mode} ({'All files' if mode == '0' else 'Target files only'})")

        # Get target filenames if in selective mode
        target_filenames = []
        if mode == '1':
            target_filenames = get_target_filenames()
            print(f"Target files: {', '.join(target_filenames)}")

        # Create converter and run with persistent SDX connection
        converter = DCMConverter(
            mode=mode,
            target_filenames=target_filenames,
            progress_callback=progress_callback
        )

        converted_count = converter.convert_directory(directory, sdx)

        print(f"\n✓ Conversion complete: {converted_count} file(s) converted")
        return 0

    except KeyboardInterrupt:
        print("\n✗ Conversion cancelled by user")
        return 1
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
