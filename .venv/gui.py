import tkinter as tk
import customtkinter as ctk
import main

ctk.set_default_color_theme("dark-blue")
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.geometry("500x300")
        self.title("DCM to STL Converter")

        self.label = ctk.CTkLabel(self, text="DCM to STL Converter", font=("Ariel Black", 18))
        self.label.pack(pady=20)

        self.folder = tk.StringVar()
        self.button = ctk.CTkButton(self, text="Select Folder", command=main.main)
        self.button.pack(pady=20)

        self.check_var = ctk.StringVar()
        self.checkbox = ctk.CTkCheckBox(self, text="Convert common DCM file names",
                                        command=self.checkbox_event, variable=self.check_var)
        self.checkbox.pack(pady=20)

        self.info_field = ctk.CTkLabel(self, text="", height=3)
        self.info_field.pack(pady=20)

        self.mainloop()
    def checkbox_event(self):
        if self.checkvar.get() == 0:
            self.checkbox.config(text="Convert all DCMs")

App()