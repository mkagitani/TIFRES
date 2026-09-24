"""Portable defaults. The launcher overrides processing paths in memory."""
import os
from pathlib import Path
_root = Path(__file__).resolve().parent
_data = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TIFRES"
current_dir = str(_root) + os.sep
original_path = str(_data / "raw") + os.sep
fits_path = str(_data / "fits") + os.sep
png_path = str(_data / "png") + os.sep
fileCsv = str(_data / "datasets.csv")
spice_kernel_path = str(_data / "spice") + os.sep
fitsICam_path = str(_data / "fitsICam") + os.sep
ICam_path = str(_data / "ICam") + os.sep
psfRelationCsv = str(_data / "psf-relation.csv")
pythonide = "tifres-noninteractive"
flgWpos = False
Wposx = 0
Wpoxy = 0
RESET=chr(27)+"[0m"
RED=chr(27)+"[31m"
GRN=chr(27)+"[32m"
YEL=chr(27)+"[33m"
BLU=chr(27)+"[34m"
BLUE=BLU
BOLD=chr(27)+"[1m"
