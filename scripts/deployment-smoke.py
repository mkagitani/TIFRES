"""Synthetic relocated-package verification; never runs scientific reduction."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import numpy as np
from astropy.io import fits

package, work = map(lambda p: Path(p).resolve(), sys.argv[1:3])
manifest=json.loads((package/"manifest.json").read_text())
for name,digest in manifest["Files"].items():
    assert hashlib.sha256((package/name).read_bytes()).hexdigest()==digest,name
for path in package.rglob("*"):
    if path.is_file():
        assert path.suffix.lower() not in (".fits",".fit",".fts",".png",".csv",".pyc",".pdb"),path
        assert "__pycache__" not in path.parts
sys.path.insert(0,str(package/"python"))
import tifres_launcher as launcher
import tifres_viewer, tifres_status, tifres_dependencies, tifres_provenance, tifres_publication, tifres_quicklook
for module in (launcher,tifres_viewer,tifres_status,tifres_dependencies,tifres_provenance,tifres_publication,tifres_quicklook):
    assert Path(module.__file__).resolve().is_relative_to(package)
for path in list(package.rglob("*.py"))+[package/"Tifres.App.dll"]:
    raw=path.read_bytes().lower()
    for text in ("c:"+chr(92)+"work"+chr(92)+"tifres", "anaconda3", "miniconda3"):
        assert text.encode() not in raw and text.encode("utf-16-le") not in raw, path
legacy=package/"python/legacy"
data=np.tile(np.arange(7,dtype=float),(120,1))
h=fits.Header(dict(NFIBX=10,NFIBY=12,CTYPE1="WAVE",CTYPE2="FIBERID",CRVAL1=500.,CDELT1=.1,CRPIX1=1.,CUNIT1="nm"))
fits.HDUList([fits.PrimaryHDU(data,h),fits.ImageHDU(np.arange(120),name="FIBERS"),fits.ImageHDU(np.arange(120),name="IFIBERS")]).writeto(work/"synthetic.w5wc.fits")
csv=work/"dataset.csv";csv.write_text("DSNO,DATATYPE,FILENAME\n123,SKY,synthetic.fits\n")
columns,rows=launcher.read_table(csv)
cfg=launcher.configure(legacy,csv,work,work,str(work/"png"))
assert Path(cfg.fileCsv)==csv
assert Path(cfg.original_path)==work
sys.path.insert(0,str(legacy))
with launcher.adapters(csv,columns,rows,[123]):
    for name in ("mkSpFrames4f","mkFibFit4c","mkFibSpec4d","mkWavMap4d","mkWcalSpec4d"):
        module=importlib.import_module(name)
        assert callable(getattr(module,name))
for name in ("psgrad548-568.txt","psgrad586-596.txt","psgrad625-635.txt","psgrad760-780.txt"):
    assert (legacy/"psg"/name).is_file()
print("PASS: manifest, package exclusions, backend imports, five legacy imports, portable cfg and solar references")
