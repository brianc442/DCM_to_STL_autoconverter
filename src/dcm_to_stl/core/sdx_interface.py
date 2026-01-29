"""SDX COM interface wrapper for DCM to STL conversion.

This module provides a clean interface to the Delcam SDX COM object,
consolidating error handling and connection management.
"""
import time
from typing import Optional, Callable
import win32com.client as win32
from win32com.client import Dispatch


class SDXError(Exception):
    """Base exception for SDX-related errors."""
    pass


class SDXInterface:
    """Wrapper for the Delcam SDX COM interface.

    Provides context manager support for automatic connection/disconnection
    and consolidated error handling.

    Example:
        with SDXInterface() as sdx:
            sdx.convert_file('input.dcm', 'output.stl')
    """

    def __init__(self):
        self._sdx: Optional[Dispatch] = None

    def attach(self) -> Dispatch:
        """Initialize and attach to the SDX COM interface.

        Returns:
            The attached SDX Dispatch object.

        Raises:
            SDXError: If connection fails.
        """
        try:
            self._sdx = win32.Dispatch("sdx.DelcamExchange")
            self._sdx.Attach()
            return self._sdx
        except Exception as e:
            raise SDXError(f"Failed to attach to SDX COM interface: {e}")

    def detach(self) -> None:
        """Disconnect from the SDX COM interface."""
        if self._sdx:
            try:
                self._sdx.Detach()
            except Exception:
                pass  # Ignore errors during detach
            finally:
                self._sdx = None

    @property
    def is_attached(self) -> bool:
        """Check if currently attached to SDX.

        Returns:
            True if attached, False otherwise.
        """
        return self._sdx is not None

    def __enter__(self):
        """Context manager entry."""
        self.attach()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.detach()
        return False

    @property
    def sdx(self) -> Dispatch:
        """Get the underlying SDX Dispatch object.

        Returns:
            The SDX Dispatch object.

        Raises:
            SDXError: If not attached.
        """
        if self._sdx is None:
            raise SDXError("Not attached to SDX. Call attach() first.")
        return self._sdx

    def convert_file(self,
                    input_file: str,
                    output_file: str,
                    input_format: str = "3Shape",
                    output_format: str = "STL",
                    progress_callback: Optional[Callable[[str], None]] = None) -> None:
        """Convert a DCM file to STL format.

        Args:
            input_file: Absolute path to input DCM file
            output_file: Absolute path to output STL file
            input_format: Input format (default: "3Shape")
            output_format: Output format (default: "STL")
            progress_callback: Optional callback for progress updates

        Raises:
            SDXError: If conversion fails
        """
        if self._sdx is None:
            raise SDXError("Not attached to SDX. Call attach() first.")

        # Configure SDX
        self._sdx.SetOption("INPUT_FORMAT", input_format)
        self._sdx.SetOption("OUTPUT_FORMAT", output_format)
        self._sdx.SetOption("INPUT_FILE", input_file)
        self._sdx.SetOption("OUTPUT_FILE", output_file)

        # Execute conversion
        state = self._sdx.Execute()

        if state == 0:
            # Wait for conversion to complete
            while not self._sdx.Finished:
                if progress_callback:
                    progress_callback("converting...")
                time.sleep(1)

            if progress_callback:
                progress_callback(f"Converted: {input_file}")
        else:
            # Handle error
            error_msg = self._handle_error(state)
            raise SDXError(error_msg)

    def _handle_error(self, state: int) -> str:
        """Map SDX error codes to error messages.

        Args:
            state: SDX error code

        Returns:
            Error message string
        """
        error_messages = {
            -1: "The whole world has gone bonkers",
            1: "No input file specified",
            2: "No output file specified",
            3: "No output format specified",
            4: "Powershape/Camtek option passed but no voucher given",
            5: "Can't translate from the input format",
            6: "Can't translate to the output format",
            7: "The calling client is not attached",
            8: "Extract CATIA requested but input file is not CATIA",
            9: "Extract CATIA requested, input file is CATIA but extraction failed",
            10: "Decrypt proe requested but input file is not proe",
            11: "Decrypt proe requested, input file is proe but decryption failed",
            12: "The passed voucher is invalid for the given input file",
            13: "No PAF/Flex/Voucher exists for the input file",
            14: "Input file is the same as the output file"
        }

        msg = error_messages.get(state, f"Unknown error code: {state}")
        return f"COM Error {state}: {msg}"
