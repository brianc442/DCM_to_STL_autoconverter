import os, time
from icecream import ic
import win32com.client as win32
from tkinter.filedialog import askdirectory


def handle_COM_error(state: int):
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
        else:
            handle_COM_error(state)

        sdx.Detach()


def main() -> None:
    path = askdirectory(title='Select Folder')  # shows dialog box and return the path
    ic(path)
    for file in os.listdir(path):
        ic(file)

    # stl_to_dcm('test.dcm')

if __name__ == '__main__':
    main()