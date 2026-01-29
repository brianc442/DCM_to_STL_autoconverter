import time

import win32com.client as win32

sdx = win32.Dispatch("sdx.DelcamExchange")
sdx.Attach()
sdx.SetOption("INPUT_FORMAT", "3Shape")
sdx.SetOption("OUTPUT_FORMAT", "STL")
sdx.SetOption("INPUT_FILE", r"C:\Users\bconn\PycharmProjects\DCM to STL autoconverter\.venv\test.dcm")
sdx.SetOption("OUTPUT_FILE", r"C:\Users\bconn\PycharmProjects\DCM to STL autoconverter\.venv\test.stl")
sdx.Execute()
while not sdx.Finished:
    time.sleep(1)
sdx.Detach()

for filename in list_files(path):
    if os.path.splitext(filename)[1] == '.dcm':
        ic(filename)