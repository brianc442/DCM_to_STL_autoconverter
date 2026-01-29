"""Main entry point for running as module: python -m dcm_to_stl

By default, launches the GUI application.
Use --cli flag for command-line interface.
"""
import sys

if __name__ == '__main__':
    # Check for CLI flag
    if '--cli' in sys.argv:
        from .cli.main import main
        sys.exit(main())
    else:
        from .gui.app import main
        main()
