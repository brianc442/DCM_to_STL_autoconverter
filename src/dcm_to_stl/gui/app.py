"""GUI application for DCM to STL conversion.

This module provides a CustomTkinter-based GUI for the converter,
refactored to use the shared core conversion logic.
"""
import atexit
import ctypes
import os
import sys
import threading
from queue import Queue
from tkinter.filedialog import askdirectory

import customtkinter as ctk
from customtkinter import CTk
import pythoncom

from ..core.converter import DCMConverter
from ..core.sdx_interface import SDXInterface
from ..config.registry import get_mode, toggle_mode, RegistryConfigError
from ..config.settings import get_target_filenames, get_icon_path
from .events import Ticket, TicketPurpose


# Configure CustomTkinter appearance
ctk.set_default_color_theme("dark-blue")
ctk.set_appearance_mode("dark")


class ToolTip:
    """Simple tooltip for CustomTkinter widgets."""

    def __init__(self, widget):
        self.widget = widget
        self.tip_window = None
        self.text = ""

    def show(self, text: str):
        """Show tooltip with given text."""
        self.text = text
        if self.tip_window or not self.text:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20

        self.tip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        label = ctk.CTkLabel(
            tw,
            text=self.text,
            fg_color=("gray75", "gray25"),
            corner_radius=6,
            padx=8,
            pady=4
        )
        label.pack()

    def hide(self):
        """Hide tooltip."""
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

# Set Windows AppUserModelID for taskbar icon
myappid = "Creo.DCM.to.STL.Autoconverter.1.0"
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


class App(ctk.CTk):
    """Main GUI application window."""

    def __init__(self):
        """Initialize the application window."""
        super().__init__()
        self.geometry("300x350")
        self.resizable(False, False)
        self.title("DCM to STL Converter")

        # Set icon (handle both dev and bundled modes)
        try:
            icon_path = get_icon_path()
            self.iconbitmap(str(icon_path))
        except Exception:
            # Fallback to _internal path for backwards compatibility
            try:
                self.iconbitmap(r"_internal\icon.ico")
            except Exception:
                pass  # No icon available

        # Initialize UI frame first
        self.frame = self.draw_frame()
        self.frame.pack()

        # SDX status indicator - pinned to window's lower right corner
        self.sdx_status = ctk.CTkLabel(
            self,
            text="●",
            font=("Arial", 16),
            text_color="red",
            cursor="hand2",
            width=20,
            height=20
        )
        self.sdx_status._current_color = "red"  # Track current state
        self.sdx_status.place(relx=1.0, rely=1.0, x=-10, y=-10, anchor="se")
        self.sdx_status.bind("<Button-1>", self._on_status_click)

        # Tooltip for status indicator
        self.sdx_tooltip = ToolTip(self.sdx_status)
        self.sdx_status.bind("<Enter>", self._on_status_enter)
        self.sdx_status.bind("<Leave>", self._on_status_leave)

        self.queue_message = Queue()
        self.bind("<<CheckQueue>>", self.handle_progress_event)

        # Initialize SDX interface (but don't attach yet)
        self.sdx = SDXInterface()
        # Register cleanup on exit
        atexit.register(self.sdx.detach)

        # Schedule SDX attachment after GUI appears (non-blocking)
        self.after(100, self._attach_sdx_background)

    def draw_frame(self) -> ctk.CTkFrame:
        """Create and populate the main UI frame.

        Returns:
            The configured frame widget
        """
        self.frame = ctk.CTkFrame(self, fg_color="gray10")

        self.label1 = ctk.CTkLabel(
            self.frame,
            text="DCM to STL Converter",
            font=("Ariel Black", 18)
        )
        self.label1.pack(pady=20)

        self.folder = ctk.StringVar()
        self.button1 = ctk.CTkButton(
            self.frame,
            text="Select Folder",
            command=self.button1_event
        )
        self.button1.pack(pady=20)

        self.button2 = ctk.CTkButton(
            self.frame,
            text="Toggle mode",
            command=self.button2_event
        )
        self.button2.pack(pady=20)

        # Show current mode
        mode = get_mode()
        self.label2 = ctk.CTkLabel(self.frame)
        if mode == '0':
            self.label2.configure(text="Convert all DCM files")
        elif mode == '1':
            self.label2.configure(text="Convert common DCM files")
        self.label2.pack(pady=20)

        self.info_field = ctk.CTkLabel(
            self.frame,
            height=3,
            text_color="grey",
            text="Select folder to begin"
        )
        self.info_field.pack(pady=5)

        return self.frame

    def button1_event(self) -> None:
        """Handle Select Folder button click.

        Starts conversion process in background thread.
        """
        self.generate_progress_event('Starting...')
        thread = threading.Thread(
            target=self.main,
            name='converter',
            daemon=False
        )
        thread.start()

    def button2_event(self) -> None:
        """Handle Toggle Mode button click.

        Toggles between convert-all and convert-targets mode.
        """
        try:
            mode = toggle_mode()

            self.generate_progress_event("Mode changed")

            if mode == '0':
                self.label2.configure(text="Convert all DCM files")
            elif mode == '1':
                self.label2.configure(text="Convert common DCM files")
            else:
                raise ValueError("invalid mode")

        except (RegistryConfigError, ValueError) as e:
            self.generate_progress_event(f"Error: {e}")

    def handle_progress_event(self, event) -> None:
        """Handle progress update events from converter thread.

        Args:
            event: Tkinter event (unused but required by event handler signature)
        """
        msg: Ticket = self.queue_message.get()

        if msg.ticket_type == TicketPurpose.UPDATE_PROGRESS:
            self.info_field.configure(text=msg.ticket_value)

    def generate_progress_event(self, text: str) -> None:
        """Generate a progress update event for the UI.

        Args:
            text: Progress message to display
        """
        ticket = Ticket(
            ticket_type=TicketPurpose.UPDATE_PROGRESS,
            ticket_value=f"{text}"
        )

        self.queue_message.put(ticket)
        self.event_generate("<<CheckQueue>>")

    def _update_sdx_status(self, color: str) -> None:
        """Update the SDX status indicator color.

        Args:
            color: Color name ("red", "yellow", or "green")

        Note: Thread-safe - can be called from any thread.
        """
        # Schedule UI update on main thread
        def update():
            self.sdx_status.configure(text_color=color)
            # Update cursor - only clickable when red
            cursor = "hand2" if color == "red" else "arrow"
            self.sdx_status.configure(cursor=cursor)
            # Store current color for tooltip
            self.sdx_status._current_color = color

        self.after(0, update)

    def _attach_sdx(self) -> None:
        """Attach to SDX and update status indicator (runs in background thread)."""
        # Initialize COM for this thread
        pythoncom.CoInitialize()
        try:
            self._update_sdx_status("yellow")
            try:
                self.sdx.attach()
                self._update_sdx_status("green")
            except Exception as e:
                self._update_sdx_status("red")
                print(f"Warning: Failed to initialize SDX connection: {e}")
        finally:
            # Uninitialize COM for this thread
            pythoncom.CoUninitialize()

    def _attach_sdx_background(self) -> None:
        """Start SDX attachment in background thread."""
        threading.Thread(
            target=self._attach_sdx,
            name='sdx_init',
            daemon=True
        ).start()

    def _on_status_click(self, event) -> None:
        """Handle click on SDX status indicator.

        Only works when red (disconnected) - attempts to reconnect.

        Args:
            event: Tkinter event
        """
        # Only allow reconnection when red (disconnected)
        current_color = getattr(self.sdx_status, '_current_color', 'red')
        if current_color == "red" and not self.sdx.is_attached:
            self.generate_progress_event("Reconnecting to SDX...")
            threading.Thread(
                target=self._attach_sdx,
                name='sdx_reconnect',
                daemon=True
            ).start()

    def _on_status_enter(self, event) -> None:
        """Show tooltip when mouse enters status indicator.

        Args:
            event: Tkinter event
        """
        current_color = getattr(self.sdx_status, '_current_color', 'red')
        tooltip_text = {
            'red': 'Disconnected - click to reconnect',
            'yellow': 'Connecting to SDX...',
            'green': 'Connected to SDX'
        }.get(current_color, '')

        if tooltip_text:
            self.sdx_tooltip.show(tooltip_text)

    def _on_status_leave(self, event) -> None:
        """Hide tooltip when mouse leaves status indicator.

        Args:
            event: Tkinter event
        """
        self.sdx_tooltip.hide()

    def main(self) -> None:
        """Main conversion logic (runs in background thread).

        This method is called in a separate thread when the user selects a folder.
        """
        try:
            # Get directory from user
            directory = askdirectory(title='Select Folder', mustexist=True)

            if not directory or not os.path.exists(directory):
                self.generate_progress_event("Invalid path or cancelled")
                return

            # Get mode and target filenames
            mode = get_mode()
            target_filenames = []
            if mode == '1':
                target_filenames = get_target_filenames()

            # Create converter with progress callback
            converter = DCMConverter(
                mode=mode,
                target_filenames=target_filenames,
                progress_callback=self.generate_progress_event
            )

            # Run conversion with persistent SDX connection (if available)
            converted_count = converter.convert_directory(directory, self.sdx)

            # Show completion message
            self.generate_progress_event(
                f"Complete: {converted_count} file(s)\nSelect folder to begin"
            )

        except Exception as e:
            self.generate_progress_event(f"Error: {e}")
        finally:
            # Update SDX status after conversion
            if self.sdx.is_attached:
                self._update_sdx_status("green")
            else:
                self._update_sdx_status("red")


def main() -> None:
    """Entry point for GUI application."""
    app = App()
    app.mainloop()


if __name__ == '__main__':
    main()
