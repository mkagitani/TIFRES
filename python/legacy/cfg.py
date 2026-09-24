
import os

# config.py
original_path = 'd:\\data\\andor7\\' 
spice_kernel_path = 'd:\\data\\spice\\kernels\\naif.jpl.nasa.gov\\pub\\naif\\generic_kernels\\'
current_dir   = os.path.dirname(os.path.abspath(__file__))+'\\'
fits_path     = os.path.dirname(os.path.abspath(__file__))+'\\fits\\'
fitsICam_path   = os.path.dirname(os.path.abspath(__file__))+'\\fitsICam\\'
ICam_path       = 'd:\\data\\asi178mm2\\' 
psfRelationCsv = r"D:\data\hmew\merc2025b\png\fitRHapke4ICam\fitRHapke4ICam_results_20260702140358.csv"
#fileCsv       = current_dir+'hmew202508py.csv'
#fileCsv       = current_dir+'hmew202508MeBpy.csv'
fileCsv       = current_dir+'hmew202510MeBpy.csv'
pythonide     = 'vscode'
flgWpos=False; Wposx=0; Wpoxy=-1080
#pythonide     = 'spyder'
# print() in color, print(RED + "Red" + RESET)
RESET = "\033[0m"
RED   = "\033[31m"
GRN   = "\033[32m"
YEL   = "\033[33m"
BLU  = "\033[34m"
BLUE = "\033[34m"
BOLD  = "\033[1m"

# Shared PNG root; callers may override this in memory. Keep a trailing separator.
png_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'png') + os.sep
