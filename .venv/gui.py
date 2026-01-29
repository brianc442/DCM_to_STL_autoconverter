import atexit, ctypes, json, os, sys, threading, time, winreg
from os import PathLike

from enum import Enum, auto
import tkinter as tk
from tkinter.filedialog import askdirectory
from queue import Queue

from icecream import ic
import customtkinter as ctk
from customtkinter import CTk
import pythoncom
import win32com.client as win32
from win32com.client import Dispatch

ic.configureOutput(includeContext=True)

ctk.set_default_color_theme("dark-blue")
ctk.set_appearance_mode("dark")
myappid = "Creo.DCM.to.STL.Autoconverter.1.0"
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

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

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.geometry("300x350")
        self.resizable(False, False)
        self.title("DCM to STL Converter")

        # Set icon with proper PyInstaller path handling
        try:
            # Try PyInstaller bundled path first
            if hasattr(sys, '_MEIPASS'):
                icon_path = os.path.join(sys._MEIPASS, '_internal', 'withholding-icon-transparent.ico')
            else:
                icon_path = r"withholding-icon-transparent.ico"
            self.iconbitmap(icon_path)
        except Exception:
            # Try alternative icon locations
            try:
                self.iconbitmap("withholding-icon-transparent.ico")
            except Exception:
                pass  # No icon available, continue without it

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

        # Initialize persistent SDX connection (in background after GUI loads)
        self.sdx = None
        atexit.register(self._cleanup_sdx)
        # Schedule SDX attachment after GUI appears
        self.after(100, self._attach_sdx_background)
    def draw_frame(self) -> ctk.CTkFrame:
        self.frame = ctk.CTkFrame(self, fg_color="gray10")

        self.label1 = ctk.CTkLabel(self.frame, text="DCM to STL Converter", font=("Ariel Black", 18))
        self.label1.pack(pady=20)

        self.folder = ctk.StringVar()
        self.button1 = ctk.CTkButton(self.frame, text="Select Folder", command=self.button1_event)
        self.button1.pack(pady=20)

        self.button2 = ctk.CTkButton(self.frame, text="Toggle mode", command=self.button2_event)
        self.button2.pack(pady=20)

        mode = self.get_mode()
        self.label2 = ctk.CTkLabel(self.frame)
        if mode == '0':
            self.label2.configure(text="Convert all DCM files")
        elif mode == '1':
            self.label2.configure(text="Convert common DCM files")
        self.label2.pack(pady=20)

        self.info_field = ctk.CTkLabel(self.frame, height=3, text_color="grey", text="Select folder to begin")
        self.info_field.pack(pady=5)

        return self.frame
    def get_mode(self) -> str:
        # script_path = os.path.abspath(__file__)
        # os.chdir(os.path.dirname(script_path))
        #
        # mode_path = os.path.join(
        #     os.path.split(script_path)[0],
        #     r"mode.ini")
        #
        # with open(mode_path, 'r') as f:  # load mode
        #     return json.load(f).__getitem__('mode')
        # return os.getenv("mode")
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\CreoDent Prosthetics', access=winreg.KEY_ALL_ACCESS)
        value = winreg.QueryInfoKey(key)
        mode = winreg.QueryValueEx(key, 'mode')[0]
        return mode
    def toggle_mode(self) -> str:
        # script_path = os.path.abspath(__file__)
        # os.chdir(os.path.dirname(script_path))
        #
        # mode_path = os.path.join(
        #     os.path.split(script_path)[0],
        #     r"mode.ini")
        #
        # mode = self.get_mode()
        # mode = os.getenv('mode')
        # try:
        #     if mode == '0':
        #         # with open(mode_path, 'w') as f:
        #         #     json.dump({"mode": "1"}, f)
        #         os.environ["mode"] = "1"
        #     elif mode == '1':
        #         # with open(mode_path, 'w') as f:
        #         #     json.dump({"mode": "0"}, f)
        #         os.environ["mode"] = "0"
        #     else:
        #         raise ValueError("invalid mode")
        # except ValueError:
        #     raise ValueError("invalid mode")
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\CreoDent Prosthetics', access=winreg.KEY_ALL_ACCESS)
        value = winreg.QueryInfoKey(key)
        # get current state
        mode = self.get_mode()
        # toggle mode
        try:
            if mode == '0':
                winreg.SetValueEx(key, 'mode', 0, winreg.REG_SZ, '1')
                mode = winreg.QueryValueEx(key, 'mode')[0]
            elif mode == '1':
                winreg.SetValueEx(key, 'mode', 0, winreg.REG_SZ, '0')
                mode = winreg.QueryValueEx(key, 'mode')[0]
            else:
                raise ValueError('invalid mode')
        except ValueError:
            raise ValueError('invalid mode')
        # return new mode
        mode = self.get_mode()
        return mode
    def button1_event(self) -> None:
        self.generate_progress_event('converting')
        thread = threading.Thread(target=self.main(), name='converter', daemon=False).start()
    def button2_event(self):
        mode = self.toggle_mode()

        ticket = ic(Ticket(ticket_type=TicketPurpose.UPDATE_PROGRESS,
                        ticket_value="Mode changed"))

        self.queue_message.put(ticket)
        self.event_generate("<<CheckQueue>>")

        try:
            if mode == '0':
                self.label2.configure(text="Convert all DCM files")
            elif mode == '1':
                self.label2.configure(text="Convert common DCM files")
            else:
                raise ValueError("invalid mode")
        except ValueError:
            raise ValueError("invalid mode")
    def handle_progress_event(self, event):
        msg: Ticket
        msg = self.queue_message.get(event)

        if msg.ticket_type == TicketPurpose.UPDATE_PROGRESS:
            self.info_field.configure(text=msg.ticket_value)
    def generate_progress_event(self, text: str):
        ticket = Ticket(ticket_type=TicketPurpose.UPDATE_PROGRESS,
                        ticket_value=f"{text}")
        ic(text)

        self.queue_message.put(ticket)
        self.event_generate("<<CheckQueue>>")
    # from main
    def handle_COM_error(self, state: int) -> None:
        if state == -1:
            raise RuntimeError("COM: -1 - The whole world has gone bonkers")
        elif state == 1:
            raise ValueError("COM: 1 - No input file specified")
        elif state == 2:
            raise ValueError("COM: 2 - No output file specified")
        elif state == 3:
            raise ValueError("COM: 3 - No output format specified")
        elif state == 4:
            raise RuntimeError("COM: 4 - Powershape/Camtek option passed but no voucher given")
        elif state == 5:
            raise RuntimeError("COM: 5 - Cant translate from the input format")
        elif state == 6:
            raise RuntimeError("COM: 6 - Cant translate to the output format")
        elif state == 7:
            raise RuntimeError("COM: 7 - The calling client is not attached")
        elif state == 8:
            raise RuntimeError("COM: 8 - Extract CATIA requested but input file is not CATIA")
        elif state == 9:
            raise RuntimeError("COM: 9 - Extract CATIA requested, input file is CATIA but extraction failed")
        elif state == 10:
            raise RuntimeError("COM: 10 - Decrypt proe requested but input file is not proe")
        elif state == 11:
            raise RuntimeError("COM: 11 - Decrypt proe requested,input file is proe but decryption failed")
        elif state == 12:
            raise RuntimeError("COM: 12 - The passed voucher is invalid for the given input file")
        elif state == 13:
            raise RuntimeError("COM: 13- No PAF/Flex/Voucher exists for the input file")
        elif state == 14:
            raise ValueError("COM: 14- Input file is the same as the output file")
    def initialize_sdx_COM(self) -> Dispatch:
        sdx = win32.Dispatch("sdx.DelcamExchange")  # connect to sdx COM interface

        self.generate_progress_event('sdx initialized')
        sdx.Attach()  # attach sdx COM interface
        return sdx
    def stl_to_dcm(self, input_file: str, sdx: Dispatch) -> None:
        if not os.path.isfile(input_file):  # validate input
            self.generate_progress_event("item to convert must be a valid PathLike object")
            raise ValueError("item to convert must be a valid PathLike object")
        else:
            input_file = os.path.abspath(input_file) # ensure absolute path is passed

            output_file_dir = os.path.splitext(input_file)[0]  # set output file to have same name with new '.stl' ext
            output_file = f"{output_file_dir}.stl"

            # if sdx.CheckOk != 1:
            #     sdx = initialize_sdx_COM()

            # pass options to sdx
            sdx.SetOption("INPUT_FORMAT", "3Shape")
            sdx.SetOption("OUTPUT_FORMAT", 'STL')
            sdx.SetOption("INPUT_FILE", os.path.abspath(input_file))
            sdx.SetOption("OUTPUT_FILE", os.path.abspath(output_file))

            state = sdx.Execute()  # run sdx conversion

            if state == 0:  # wait for conversion to finish
                while not sdx.Finished:
                    # self.generate_progress_event('waiting')
                    time.sleep(1)
                self.generate_progress_event(f'{input_file} converted')
            else:
                handle_COM_error(state)  # handle errors
    def disconnect_sdx_COM(self, sdx: Dispatch) -> None:
        sdx.Detach()  # disconnect from COM interface
        self.generate_progress_event("sdx connection closed")
    def list_files(self, directory: PathLike) -> PathLike:
        for root, directories, files in os.walk(directory):
            for filename in files:
                yield os.path.join(root, filename)
    def identify_dcm(self, path: PathLike) -> PathLike:
        """
        # returns filepath if ext is '.dcm', otherwise None
        :param path:
        :return: PathLike | None
        """
        if os.path.splitext(path)[1].lower() == '.dcm':
            return path
    def get_path(self) -> PathLike:
        return askdirectory(title='Select Folder', mustexist=True)

    def _update_sdx_status(self, color: str) -> None:
        """Update the SDX status indicator color (thread-safe)."""
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
                self.sdx = self.initialize_sdx_COM()
                self._update_sdx_status("green")
            except Exception as e:
                self._update_sdx_status("red")
                print(f"Warning: Failed to initialize SDX connection: {e}")
                self.sdx = None
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

    def _cleanup_sdx(self) -> None:
        """Cleanup SDX connection on exit."""
        if self.sdx:
            try:
                self.sdx.Detach()
            except Exception:
                pass

    def _on_status_click(self, event) -> None:
        """Handle click on SDX status indicator (only works when red)."""
        # Only allow reconnection when red (disconnected)
        current_color = getattr(self.sdx_status, '_current_color', 'red')
        if current_color == "red" and self.sdx is None:
            self.generate_progress_event("Reconnecting to SDX...")
            threading.Thread(
                target=self._attach_sdx,
                name='sdx_reconnect',
                daemon=True
            ).start()

    def _on_status_enter(self, event) -> None:
        """Show tooltip when mouse enters status indicator."""
        current_color = getattr(self.sdx_status, '_current_color', 'red')
        tooltip_text = {
            'red': 'Disconnected - click to reconnect',
            'yellow': 'Connecting to SDX...',
            'green': 'Connected to SDX'
        }.get(current_color, '')

        if tooltip_text:
            self.sdx_tooltip.show(tooltip_text)

    def _on_status_leave(self, event) -> None:
        """Hide tooltip when mouse leaves status indicator."""
        self.sdx_tooltip.hide()

    # main
    def main(self) -> None:
        conversion_list = []

        path = self.get_path()  # shows dialog box and return the path
        if not os.path.exists(path):
            self.generate_progress_event("invalid path")
            raise ValueError("invalid path")

        script_path = os.path.abspath(__file__)
        os.chdir(os.path.dirname(script_path))

        target_config_path = os.path.join(
            os.path.split(script_path)[0],
            r"target_config.ini")

        # mode_path = os.path.join(
        #     os.path.split(script_path)[0],
        #     r"mode.ini")

        with open(target_config_path, 'r') as f:  # load target contfiguration into target_dict
            target_dict = json.load(f)
        # with open(mode_path, 'r') as f:  # load mode
        #     mode = json.load(f).__getitem__('mode')
        mode = self.get_mode()

        for filename in self.list_files(path):  # os.walk selected path and return individual filepaths
            if self.identify_dcm(filename):  # returns filepath if ext is '.dcm', otherwise None
                possible_target = filename
                if mode == '0':
                    ic(conversion_list.append(possible_target))
                elif mode == '1':
                    if os.path.split(possible_target)[1] in target_dict.values():
                        conversion_list.append(possible_target)
                else:
                    self.generate_progress_event("invalid mode")
                    raise ValueError("invalid mode")
                    sys.exit(1)
        # ic(conversion_list)
        # Use persistent SDX connection if available, otherwise create temporary one
        if self.sdx:
            sdx = self.sdx
            use_persistent = True
        else:
            sdx = self.initialize_sdx_COM()
            use_persistent = False

        try:
            for target in conversion_list:
                self.stl_to_dcm(target, sdx)
        finally:
            # Only disconnect if using temporary connection
            if not use_persistent:
                self.disconnect_sdx_COM(sdx)
            # Update status indicator
            if self.sdx:
                self._update_sdx_status("green")
            else:
                self._update_sdx_status("red")

        self.generate_progress_event("Conversion complete\nSelect folder to begin")
class TicketPurpose(Enum):
    UPDATE_PROGRESS = auto()
class Ticket:
    def __init__(self,
                 ticket_type: TicketPurpose,
                 ticket_value: str):
        self.ticket_type = ticket_type
        self.ticket_value = ticket_value

if __name__ == '__main__':
    app = App()
    app.mainloop()