import json, os, time, threading
from os import PathLike
from tkinter.filedialog import askdirectory
from customtkinter import CTk

from icecream import ic
import win32com.client as win32
from win32com.client import Dispatch

ic.configureOutput(includeContext=True)


def handle_COM_error(state: int) -> None:
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
def initialize_sdx_COM() -> Dispatch:
    ic('initializing')
    sdx = win32.Dispatch("sdx.DelcamExchange")  # connect to sdx COM interface
    ic('sdx initialized')
    sdx.Attach()  # attach sdx COM interface
    return sdx
def stl_to_dcm(input_file: str, sdx: Dispatch) -> None:
    if not os.path.isfile(input_file):  # validate input
        raise ValueError("item to convert must be a valid PathLike object")
    else:
        input_file = ic(os.path.abspath(input_file))    # ensure absolute path is passed

        output_file_dir = ic(os.path.splitext(input_file)[0])   # set output file to have same name with new '.stl' ext
        output_file = ic(f"{output_file_dir}.stl")

        # if sdx.CheckOk != 1:
        #     sdx = initialize_sdx_COM()

        # pass options to sdx
        sdx.SetOption("INPUT_FORMAT", "3Shape")
        sdx.SetOption("OUTPUT_FORMAT", 'STL')
        sdx.SetOption("INPUT_FILE", os.path.abspath(input_file))
        sdx.SetOption("OUTPUT_FILE", os.path.abspath(output_file))

        state = ic(sdx.Execute())   # run sdx conversion

        if state == 0:  # wait for conversion to finish
            while not sdx.Finished:
                ic('waiting')
                time.sleep(1)
            ic(f'{input_file} converted')
        else:
            handle_COM_error(state) # handle errors
def disconnect_sdx_COM(sdx: Dispatch) -> None:
    sdx.Detach()  # disconnect from COM interface
def list_files(directory: PathLike) -> PathLike:
  for root, directories, files in os.walk(directory):
    for filename in files:
      yield os.path.join(root, filename)
def identify_dcm(path: PathLike) -> PathLike:
    """
    # returns filepath if ext is '.dcm', otherwise None
    :param path:
    :return: PathLike | None
    """
    if os.path.splitext(path)[1].lower() == '.dcm':
        return path
def get_path() -> PathLike:
    return askdirectory(title='Select Folder', mustexist=True)
def main() -> None:
    conversion_list = []
    
    path = get_path()  # shows dialog box and return the path
    if not os.path.exists(path):
        raise ValueError("invalid path")

    script_path = os.path.abspath(__file__)
    os.chdir(os.path.dirname(script_path))
    with open("target_config.ini", 'r') as f: # load target contfiguration into target_dict
        target_dict = json.load(f)
    with open("mode.ini", 'r') as f:    # load mode
        mode = json.load(f).__getitem__('mode')

    for filename in list_files(path):   # os.walk selected path and return individual filepaths
        if identify_dcm(filename):  # returns filepath if ext is '.dcm', otherwise None
            possible_target = ic(filename)
            if mode == '0':
                ic(conversion_list.append(possible_target))
            elif mode == '1':
                if os.path.split(possible_target)[1] in target_dict.values():
                    ic(conversion_list.append(possible_target))
            else:
                raise ValueError("invalid mode")
                sys.exit(1)
    ic(conversion_list)
    sdx = initialize_sdx_COM()
    for target in conversion_list:
        stl_to_dcm(target, sdx)
    disconnect_sdx_COM(sdx)

if __name__ == '__main__':
    main()