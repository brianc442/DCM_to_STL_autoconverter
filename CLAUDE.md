# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DCM to STL Autoconverter is a Windows desktop application that converts 3Shape DCM (dental scan) files to STL format using the Delcam SDX COM interface. The application provides both a GUI and PowerShell helper script for batch conversions.

## Architecture

### Core Components

**GUI Application (`.venv/gui.py`)**
- Main entry point for the desktop application
- Built with CustomTkinter (dark-themed UI)
- Uses threading to prevent UI blocking during conversions
- Queue-based message passing between converter thread and UI thread
- Reads/writes configuration to Windows Registry (`HKEY_CURRENT_USER\Software\CreoDent Prosthetics`)

**Core Logic (`.venv/main.py`)**
- Standalone conversion logic (can be used without GUI)
- Contains the COM interface handling for SDX
- File discovery and filtering logic

**Registry Mode Handler (`.venv/reg_mode.py`)**
- Manages conversion mode stored in Windows Registry
- Mode '0': Convert all DCM files in directory
- Mode '1': Convert only common DCM files (filtered by `target_config.ini`)

**Configuration (`.venv/target_config.ini`)**
- JSON file listing common DCM filenames to convert in selective mode
- Examples: "PrePreparationScan.dcm", "Raw Preparation scan.dcm", "AntagonistScan.dcm"

### COM Interface Integration

The application relies on the Delcam SDX COM interface (`sdx.DelcamExchange`):
- Must call `Attach()` before use and `Detach()` when done
- Configuration via `SetOption()` or `Option()` property
- Required options: `INPUT_FORMAT`, `OUTPUT_FORMAT`, `INPUT_FILE`, `OUTPUT_FILE`
- Execute via `Execute()` method, returns error codes (0 = success)
- Check completion with `Finished` property

### PowerShell Helper (`convert-helper.ps1`)

Alternative conversion interface for power users:
- Source the script to get the `convert` function
- Maintains persistent SDX COM connection across conversions
- Includes auto-reconnection logic if SDX detaches
- Handles network share delays with retry logic
- Usage: `. .\convert-helper.ps1` then `convert [path]` or `convert -r [path]`

## Build and Packaging

**Build with PyInstaller:**
```bash
# Activate virtual environment
.venv\Scripts\activate

# Build executable
pyinstaller "DCM to STL Autoconverter.spec"
```

**Build outputs:**
- `dist/DCM to STL Autoconverter/` - Application bundle directory
- Packaged with `mode.ini` and `target_config.ini` as data files
- Icon: `withholding-icon.ico`

## Development

**Virtual Environment:**
```bash
# Activate
.venv\Scripts\activate

# Run GUI directly
python .venv\gui.py

# Run standalone converter
python .venv\main.py
```

**Key Dependencies:**
- `customtkinter` - Modern UI framework
- `pywin32` - Windows COM interface access
- `icecream` - Debug logging (enabled in code)
- `Gooey` - Appears in venv but not actively used in current code

## Important Notes

### File Organization
- Source files are located in `.venv/` directory (non-standard location)
- Built application expects `_internal/icon.ico` path for GUI icon
- Config files must be in same directory as executable when deployed

### Mode System
- Mode stored in Windows Registry (legacy: was stored in `mode.ini`)
- Mode '0' = Convert all .dcm files recursively
- Mode '1' = Convert only specific filenames from `target_config.ini`
- GUI provides toggle button to switch modes

### COM Error Handling
State codes from SDX Execute():
- 0: Success
- 1-14: Various error conditions (see `handle_COM_error()` in main.py/gui.py)
- 7: Client not attached (requires `Attach()` call)

### Threading Model
GUI uses:
- Main thread: UI event loop
- Worker thread: File conversion operations
- Queue + custom events (`<<CheckQueue>>`) for thread-safe UI updates

### File Discovery
- Uses `os.walk()` to recursively find all files
- `identify_dcm()` filters by `.dcm` extension (case-insensitive)
- Mode '1' applies secondary filter against `target_config.ini` filenames

## PowerShell Helper Details

The `convert-helper.ps1` provides an optimized batch conversion workflow:
- Pre-initializes SDX COM connection (faster for multiple conversions)
- Handles SDX detachment errors with automatic reconnection
- Adds delays for network share file synchronization
- Provides visual progress feedback with checkmarks/crosses
- Use `disconnect-convert` to cleanup when done
