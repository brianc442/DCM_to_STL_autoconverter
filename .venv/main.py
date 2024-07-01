import os.path
from icecream import ic
import win32com.client as win32

import time

def stl_to_dcm(input_file: str) -> None:
    if os.path.isfile(input_file):
        input_file = os.path.abspath(input_file)
        ic(input_file)
        output_file_dir = os.path.splitext(input_file)[0]
        ic(output_file_dir)
        output_file = f"{output_file_dir}.stl"
        ic(output_file)
        ic('initializing')
        sdx = win32.Dispatch("sdx.DelcamExchange")
        ic('sdx initialized')
        sdx.Attach()
        sdx.SetOption("INPUT_FORMAT", "3Shape")
        sdx.SetOption("OUTPUT_FORMAT", 'STL')
        sdx.SetOption("INPUT_FILE", os.path.abspath(input_file))
        sdx.SetOption("OUTPUT_FILE", os.path.abspath(output_file))
        state = sdx.Execute()
        ic(state)
        if state == 0:
            while not sdx.Finished:
                ic('waiting')
                time.sleep(0.1)
        sdx.Detach()

def main() -> None:

    stl_to_dcm('test.dcm')

if __name__ == '__main__':
    main()