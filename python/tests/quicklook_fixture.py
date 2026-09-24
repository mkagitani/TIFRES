"""Synthetic-only fixture for the headless GUI Quick Look regression."""
from pathlib import Path
import sys
root=Path(sys.argv[1])
scripts,raw,output=[root/n for n in ('scripts','raw','fits')]
for p in (scripts,raw,output):p.mkdir(exist_ok=True)
helper="""from pathlib import Path
import numpy as np
from astropy.io import fits
def make(path,kind):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    h=fits.Header()
    if kind in ('raw','frame'): data=np.ones((12,10),dtype=np.float32)
    else:
        h['NFIBX']=10;h['NFIBY']=12
        data=np.ones((8,120,3) if kind=='trace' else (12,10) if kind=='image' else (120,8),dtype=np.float32)
    h['DATE-OBS']='2026-09-14T12:00:00';h['EXPTIME']=10.
    if kind in ('calibrated','image'):
        for k,v in dict(WAVMIN=588.,WAVMAX=588.7,WAVSTEP=.1,CRVAL1=588.,CDELT1=.1,CRPIX1=1.,CTYPE1='WAVE',CTYPE2='FIBERID',CUNIT1='nm').items():h[k]=v
    hdus=[fits.PrimaryHDU(data,h)]
    if kind not in ('raw','frame'):
        hdus.extend([fits.ImageHDU(np.arange(120),name='FIBERS'),fits.ImageHDU(np.arange(120),name='IFIBERS')])
    if kind=='trace':hdus.append(fits.ImageHDU(np.arange(8),name='YFIB'))
    if kind=='spectrum':
        hdus.extend([fits.ImageHDU(data,name='spDat'),fits.ImageHDU(data,name='spDk')])
    fits.HDUList(hdus).writeto(path,overwrite=True)
"""
(scripts/'mock_products.py').write_text(helper)
sys.path.insert(0,str(scripts))
from mock_products import make
for i in (1,2):make(raw/f'new_{i:04d}.fits','raw')
for name,kind in [('dark.sp.fits','frame'),('flat.sp.fib.fits','trace'),('flat.sp.w5fsp.fits','spectrum'),('sky.sp.w5fsp.fits','spectrum'),('cal.w5wmp.fits','map'),('sky.sp.w5wc.fits','calibrated')]:
    make(output/name,kind)
(scripts/'cfg.py').write_text("fileCsv='unused'\n")
for step,signature in [('mkSpFrames4f','overwrite=True,flgPause=True,nxFig=2,nyFig=5'),
                        ('mkFibSpec4d','flgPause=False,flgShowAll=False,fibintwid=5,overwrite=True'),
                        ('mkWcalSpec4d','flgPlot=False,fibintwid=5,overwrite=True,flgNoWLflat=False')]:
    (scripts/(step+'.py')).write_text(f"""def {step}(dsno,{signature}):
    import csv,cfg
    from pathlib import Path
    from tifres_dependencies import contract
    from mock_products import make
    with open(cfg.fileCsv,encoding='utf-8') as f:rows=list(csv.DictReader(f))
    row=next(r for r in rows if r['DSNO']==str(dsno[0]))
    plan=contract('{step}',row,{{'fibintwid':5}})
    for rel,kind in plan.products.items():make(Path(cfg.fits_path)/rel,kind)
""")
