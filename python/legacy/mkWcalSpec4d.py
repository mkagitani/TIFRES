### Last update on 15-APR-2025
### Last update on 20-MAR-2026, ..4c.py

import numpy as np
import matplotlib; matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.gridspec as gridspec
from scipy.interpolate import interp1d
from astropy.io import fits
from astropy.time import Time
from astropy.stats import sigma_clip
from astropy.modeling import models, fitting
import pandas as pd
import glob
import os
import sys
import shutil
from datetime import datetime
import cfg

def mkWcalSpec4d(dsno, flgPlot=True, fibintwid=5, overwrite=True,flgNoWLflat=False):
    df = pd.read_csv(cfg.fileCsv)
    file_idx = df[df.DSNO.isin(dsno)]
    
    for index, row in file_idx.iterrows():
        print(f"{row.DSNO:.0f} ", end='')
        
        # 基本パスの設定
        filename = cfg.fits_path + str(row.FILENAME)
        fileFSp = cfg.fits_path + (row.FILENAME).replace(".fits", f".w{fibintwid:.0f}fsp.fits")
        fileWMP = cfg.fits_path + (row.WAVMAP).replace(".wmp.fits", f".w{fibintwid:.0f}wmp.fits")
        fileDatWC = cfg.fits_path + (row.FILENAME).replace(".fits", f".w{fibintwid:.0f}wc.fits")

        # スキップ判定
        if (os.path.exists(fileDatWC) and not overwrite):
            print(cfg.RED + f"Skipped: {row.DSNO:.0f} {fileDatWC}" + cfg.RESET)
            continue
        elif not os.path.exists(filename):
            print(cfg.RED + f"{row.DSNO:.0f} FILENAME ファイルが存在しません: {filename}" + cfg.RESET)
            continue
        elif not os.path.exists(fileFSp):
            print(cfg.RED + f"{row.DSNO:.0f} *.fsp.fits ファイルが存在しません: {fileFSp}" + cfg.RESET)
            continue
        elif not os.path.exists(fileWMP):
            print(f"{row.DSNO:.0f} WAVMAP ファイルが存在しません: {fileWMP}")
            input("Press Enter to continue")
            continue

        # 出力用ファイル名の定義
        fileFSpFlt = cfg.fits_path + (row.FILENAME).replace(".fits", f".w{fibintwid:.0f}ffsp.fits")
        fileDCB = cfg.fits_path + (row.FILENAME).replace(".fits", f".w{fibintwid:.0f}dcb.fits")
        fileIMG = cfg.fits_path + (row.FILENAME).replace(".fits", f".w{fibintwid:.0f}img.fits")
        fileFSpWL = cfg.fits_path + (row.WLFLAT).replace(".fits", f".w{fibintwid:.0f}fsp.fits")

        # 1. Object Data の読み込み
        try:
            with fits.open(fileFSp) as hdu1:
                print("Reading fileFSp", fileFSp)
                spDat = hdu1[0].data
                iFibAct = hdu1['IFIBERS'].data
                iFib = hdu1['FIBERS'].data
                hd1 = hdu1[0].header
                nx, ny = hd1['NAXIS1'], hd1['NAXIS2']
                nFibX, nFibY = hd1['NFIBX'], hd1['NFIBY']
        except Exception as e:
            print(f"Error reading {fileFSp}: {e}")
            continue

        # 2. WLFLAT の読み込み
        if pd.isna(row.WLFLAT) or flgNoWLflat:
            print("No WLFLAT column")
            spFlt = np.ones_like(spDat) # all elements are zero
        else:
            try:
                with fits.open(fileFSpWL) as hdu2:
                    print("Reading WLFLAT", fileFSpWL)
                    spFlt = hdu2[0].data
            except Exception as e:
                print(f"Error reading {fileFSpWL}: {e}")
        #print(f"DEBUG: spFlt size = {spFlt.shape}")

        # 3. SKYFLAT の読み込み判定 (修正ポイント)
        spSky = None
        has_skyflat = False
        fileSkyWC = ""
        if pd.isna(row.SKYFLAT) or str(row.SKYFLAT).strip() == "":
            print("No SKYFLAT column: Skipping sky flat process.")
        else:
            fileSkyWC = cfg.fits_path + (row.SKYFLAT).replace(".fits", f".w{fibintwid:.0f}wc.fits")
            fileFSpSKY = cfg.fits_path + (row.SKYFLAT).replace(".fits", f".w{fibintwid:.0f}fsp.fits")
            try:
                with fits.open(fileFSpSKY) as hdu_sky:
                    print("Reading SKYFLAT", fileFSpSKY)
                    spSky = hdu_sky[0].data
                    has_skyflat = True
            except Exception as e:
                print(f"Error reading SKYFLAT {fileFSpSKY}: {e}")

        # 4. WAVMAP / Wavelength 設定
        wavshift = row.WAVSHIFT if not pd.isna(row.WAVSHIFT) else 0.
        try:
            with fits.open(fileWMP) as hdu3:
                wmp = hdu3[0].data + wavshift
        except Exception as e:
            print(f"Error reading WAVMAP: {e}")
            continue

        # 基準波長軸の作成
        tmpmin, tmpmax = np.max(wmp[iFibAct, 0]), np.min(wmp[iFibAct, nx-1])
        wavmin, wavmax = (tmpmax, tmpmin) if tmpmin > tmpmax else (tmpmin, tmpmax)
        wstep = np.abs((wavmax - wavmin) / nx)
        rwmin, rwstep = float(f"{wavmin:.8g}"), float(f"{wstep:.3g}")
        rwmax = rwmin + nx * rwstep
        rwmid = (rwmin + rwmax) / 2.
        wavs = rwmin + rwstep * np.arange(nx, dtype=float)

        # 5. データ処理 (補間とフラット適用)
        spDatWC = np.zeros((ny, nx), dtype=float)
        spSkyWC = np.zeros((ny, nx), dtype=float)
        spDatFlt = np.zeros((ny, nx), dtype=float)
        spSkyFlt = np.zeros((ny, nx), dtype=float)
        spDatImg = np.zeros((nFibY, nFibX), dtype=float)
        spSkyImg = np.zeros((nFibY, nFibX), dtype=float)
        spDatDcb = np.zeros((nx, nFibY, nFibX), dtype=float)
        FibFF = np.zeros(len(iFib))

        for j in iFibAct:
            skind = 'quadratic'
            ix, iy = j % nFibX, j // nFibX
            
            # Object Flat-fielding & Interpolation
            spDatFlt[j, :] = spDat[j, :] / spFlt[j, :] * np.median(spFlt[j, 512:1536])
            ifunct = interp1d(wmp[j, :], spDatFlt[j, :], kind=skind, fill_value="extrapolate")
            spDatWC[j, :] = ifunct(wavs)
            spDatImg[iy, ix] = np.median(spDatWC[j, 512:1536])
            spDatDcb[:, iy, ix] = spDatWC[j, :]

            # Sky Flat-fielding (存在する場合のみ)
            if has_skyflat:
                spSkyFlt[j, :] = spSky[j, :] / spFlt[j, :] * np.median(spFlt[j, 512:1536])
                ifunct_sky = interp1d(wmp[j, :], spSkyFlt[j, :], kind=skind, fill_value="extrapolate")
                spSkyWC[j, :] = ifunct_sky(wavs)
                spSkyImg[iy, ix] = np.median(spSkyWC[j, 512:1536])
                FibFF[j] = 1. / spSkyImg[iy, ix] if spSkyImg[iy, ix] != 0 else 0

        # Sky Flat Factor の適用
        if has_skyflat:
            FibFF = FibFF / np.median(FibFF[iFibAct])
            for j in iFibAct:
                ix, iy = j % nFibX, j // nFibX
                spDatWC[j, :] *= FibFF[j]
                spSkyWC[j, :] *= FibFF[j]
                spDatImg[iy, ix] = np.median(spDatWC[j, 512:1536])
                spSkyImg[iy, ix] = np.median(spSkyWC[j, 512:1536])
                spDatDcb[:, iy, ix] = spDatWC[j, :]

        # 6. FITS 出力
        hd1['SKYFLAT'] = 'Applied' if has_skyflat else 'None'
        hd1.update({'WAVMIN': rwmin, 'WAVMAX': rwmax, 'WAVSTEP': rwstep, 'WAVMID': rwmid,
                    'CTYPE1': 'WAVE', 'CRVAL1': rwmin, 'CDELT1': rwstep, 'CRPIX1': 1.0,
                    'CTYPE2': 'FIBERID', 'CRVAL2': 0, 'CDELT2': 1.0, 'CRPIX2': 1.0, 'INTERPK': skind})

        # 各種 FITS 保存
        for data, path, save_flg in [
            (spDatWC, fileDatWC, True),
            (spSkyWC, fileSkyWC, has_skyflat),
            (spDatDcb, fileDCB, False), # 元コードで 1==0 のため
            (spDatImg, fileIMG, True)
        ]:
            if save_flg and path:
                hdu_list = [fits.PrimaryHDU(data=data.astype(np.float32), header=hd1),
                            fits.ImageHDU(data=iFib.astype(np.int16), name='FIBERS'),
                            fits.ImageHDU(data=iFibAct.astype(np.int16), name='IFIBERS')]
                fits.HDUList(hdu_list).writeto(path, overwrite=True)
                print(f"{path} saved")

        # 7. プロット処理 (flgPlot=True の場合)
        if flgPlot:
            for j in iFibAct:
                ix, iy = j % nFibX, j // nFibX
                fig = plt.figure(figsize=(9, 10), dpi=96)
                gs = gridspec.GridSpec(6, 2, height_ratios=[1, 1, 1, 1, 1, 1], width_ratios=[14, 1])
                plt.subplots_adjust(wspace=0.0, hspace=0.45, left=0.08, right=0.95, top=0.95, bottom=0.05)

                # (1) Object WC
                ax0 = fig.add_subplot(gs[0, 0])
                vrng = [np.percentile(spDatWC[iFibAct, :], 0.1), np.percentile(spDatWC[iFibAct, :], 99.9)]
                im0 = ax0.imshow(spDatWC, cmap='jet', aspect='auto', origin='lower', extent=[rwmin, rwmax, 0, ny], vmin=vrng[0], vmax=vrng[1])
                ax0.set_title(f"spDatWC (Sky:{hd1['SKYFLAT']})", fontsize=8)
                fig.colorbar(im0, cax=fig.add_subplot(gs[0, 1]))

                # (4) Sky WC (もしあれば)
                if has_skyflat:
                    ax3 = fig.add_subplot(gs[3, 0])
                    im3 = ax3.imshow(spSkyWC, cmap='jet', aspect='auto', origin='lower', vmin=np.percentile(spSkyWC, 1), vmax=np.percentile(spSkyWC, 99))
                    ax3.set_title("spSkyWC", fontsize=8)
                    fig.colorbar(im3, cax=fig.add_subplot(gs[3, 1]))

                # (5) Spectrum Plot
                ax4 = fig.add_subplot(gs[4, 0])
                ax4.plot(wavs, spDatWC[j, :], label="Object")
                if has_skyflat: ax4.plot(wavs, spSkyWC[j, :], label="Sky")
                ax4.legend(fontsize=6); ax4.axhline(0, color='k', lw=0.5)

                # 保存
                filePng = f"{cfg.png_path}{os.path.basename(__file__).replace('.py','/')}{row.DSNO:.0f}/" \
                          f"{os.path.basename(fileDatWC).replace('.fits', f'_ifib{j:03}.png')}"
                os.makedirs(os.path.dirname(filePng), exist_ok=True)
                plt.savefig(filePng, bbox_inches='tight')
                plt.close()

    print("All finished")


# スクリプトの最後にこれを追加する
if __name__ == "__main__":
    df= pd.read_csv(cfg.fileCsv)
    file_idx = df[(df.DATATYPE != 'BADDATA') & (df.DATATYPE != 'DARK') & (df.DATATYPE != 'NONE')
                #& (df.DSNO >=  250502100) & (df.DSNO < 250502990)
                #& (df.DSNO >=  250504000) & (df.DSNO < 250504990)
                #& (df.DSNO >= 250819100) & (df.DSNO <= 250819990) 
                #& (df.DSNO >= 250820000) & (df.DSNO <= 250820900) 
                #& (df.DSNO >= 251111000) & (df.DSNO <= 251112900) 
                #& (df.DSNO >= 251112000) & (df.DSNO <= 251112900) 
                #& (df.DSNO >= 251208000) & (df.DSNO <= 251209990) 
                #& (df.DSNO >=  251209100) & (df.DSNO < 251209990)
                #& (df.DSNO >= 260217000) & (df.DSNO <= 260217990) 
                #& (df.DSNO >= 250824000) & (df.DSNO < 250825000)
                #& (df.DSNO >  250819000) & (df.DSNO < 250820000)
                #& (df.DSNO >  251010900) & (df.DSNO < 251010990)
                #& (df.DSNO >=  251214900) & (df.DSNO < 251214990)
                #& (df.DSNO >=  251208000) & (df.DSNO < 251208990)
                #& (df.DSNO >=  251209000) & (df.DSNO < 251209990)
                #& (df.DSNO >=  260320209) & (df.DSNO < 260320900)
                #& (df.DSNO >= 251111000) & (df.DSNO < 251113000)
                #& (df.DSNO >=  260217000) & (df.DSNO < 260217990)
                #& (df.DSNO >=  260402111) & (df.DSNO < 260402990)
                #& (df.DSNO >=  260406111) & (df.DSNO < 260406990)
                #& (df.DSNO >=  260406121) & (df.DSNO < 260406130)
                #& (df.DSNO >=  260422110) & (df.DSNO < 260422990)
                #& (df.DSNO >=  260423110) & (df.DSNO < 260423990)
                #& (df.DSNO >=  260424110) & (df.DSNO < 260424990)
                #& (df.DSNO >=  260427110) & (df.DSNO < 260427990)
                #& ( (df.DSNO % 1000 < 200) | ((df.DSNO % 1000 > 200) & (df.DSNO % 25 == 0)) )
                #& (df.DSNO >= 260811000) & (df.DSNO <= 260811900) 
                #& (df.DSNO >= 260915161) & (df.DSNO <= 260915900) 
                #& (df.DSNO >= 260916161) & (df.DSNO <= 260916900) 
                & (df.DSNO >=  260917164) & (df.DSNO < 260917900)
                ]    
    dsno = file_idx.DSNO.astype('int64').tolist()
    #dsno = [251112129,251112200,251112201]
    #dsno = [250820200,250820250,250820275,250820300,250820400,250820425,250820450,250820475,250820500,250820525,250820550,250820575]
    #dsno = [260320010]
    #dsno = [251111111]

    print(dsno)
    
    #mkWcalSpec4d(dsno,flgPlot=False,fibintwid=5,overwrite=True,flgNoWLflat=True)
    mkWcalSpec4d(dsno,flgPlot=False,fibintwid=5,overwrite=True,flgNoWLflat=False)
