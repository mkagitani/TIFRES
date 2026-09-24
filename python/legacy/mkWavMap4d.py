### Last update on 15-APR-2025
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
#matplotlib.use("TkAgg")  # TkAggバックエンドを明示的に設定
from scipy.ndimage import median_filter
from scipy.signal import convolve
from scipy.optimize import curve_fit
from scipy.interpolate import interp1d
from scipy.optimize import least_squares
from astropy.stats import sigma_clip
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

plt.rcParams.update({'font.size': 8})

nterm = 4 
def gauss1d(x, A): # ガウス関数の定義
    z=(x-A[1])/A[2]
    if nterm==3: return  A[0] * np.exp(-(z ** 2)/2)
    elif(nterm==4): return  A[0] * np.exp(-(z ** 2)/2) + A[3]
    elif(nterm==5): return  A[0] * np.exp(-(z ** 2)/2) + A[3] + A[4]* (x-A[1])

def residuals(A, x, y):
    return gauss1d(x, A) - y

def gauss1d4(x, A): # ガウス関数の定義
    z=(x-A[1])/A[2]
    return  A[0] * np.exp(-(z ** 2)/2) + A[3]
    
def residuals4(A, x, y):
    return gauss1d4(x, A) - y

def gauss1d5(x, A): # ガウス関数の定義
    z=(x-A[1])/A[2]
    return  A[0] * np.exp(-(z ** 2)/2) + A[3] + A[4]* (x-A[1])

def residuals5(A, x, y):
    return gauss1d5(x, A) - y

def replace_outliers_with_mean(data, mask):# 外れ値を周辺のデータで置き換える関数
    result = data.copy()
    consecutive_outliers = False  # 連続した外れ値を追跡するフラグ

    for i in np.where(mask)[0]:  # 外れ値のインデックスを取得
        if i > 0 and mask[i - 1]:  # 前のデータが外れ値であれば連続とみなす
            consecutive_outliers = True
        else:
            consecutive_outliers = False

        if not consecutive_outliers:  # 連続した外れ値でない場合のみ置き換え
            # 周辺の平均値を計算 (端のデータを扱うために範囲をクリップ)
            lower = max(0, i - 2)
            upper = min(len(data), i + 3)
            # マスクされていないデータの平均を計算
            non_outlier_data = data[lower:upper][~mask[lower:upper]]
            if len(non_outlier_data) > 0:
                result[i] = np.mean(non_outlier_data)  # 周辺の平均で置き換え
    return result

# 畳み込みカーネル (ガウシアンカーネル)
def gaussian_kernel(size, sigma=1):
    x = np.linspace(-size // 2, size // 2, size)
    kernel = np.exp(-x**2 / (2 * sigma**2))
    return kernel / np.sum(kernel)



def fit_smooth_cubic_with_fiber_offsets(pixel_centers, wavelengths, active_fibers,
                                          fiber_numbers, nx,
                                          fiber_coef_degree=2,
                                          max_residual_pm=3.0):
    """Fit independent smooth cubic models for even and odd fiber rows.

    For each parity group p (even/odd),

        u = (x - pixel_offset[j] - x_ref) / x_scale
        v = (fiber_number[j] - fiber_ref[p]) / fiber_scale[p]

        wavelength(j, x) = c0[p]
                         + C1_p(v) * u
                         + C2_p(v) * u**2
                         + C3_p(v) * u**3

    C1, C2 and C3 vary smoothly with fiber number within each parity group.
    Pixel offsets remain independent for every fiber, with zero mean imposed
    separately within the even and odd groups.
    """
    active_fibers = np.asarray(active_fibers, dtype=int)
    wavelengths = np.asarray(wavelengths, dtype=float)
    fiber_numbers = np.asarray(fiber_numbers, dtype=float)
    nrow = pixel_centers.shape[0]
    nline = len(wavelengths)
    n_fcoef = fiber_coef_degree + 1
    x_ref = 0.5 * (nx - 1)
    x_scale = max(0.5 * (nx - 1), 1.0)

    parity_results = {}

    def fit_one_group(group_fibers):
        group_fibers = np.asarray(group_fibers, dtype=int)
        nfib = len(group_fibers)
        if nfib == 0:
            return None

        active_numbers = fiber_numbers[group_fibers]
        fiber_ref = np.nanmedian(active_numbers)
        fiber_scale = np.nanmax(np.abs(active_numbers - fiber_ref))
        if not np.isfinite(fiber_scale) or fiber_scale <= 0:
            fiber_scale = 1.0
        v_active = (active_numbers - fiber_ref) / fiber_scale

        fiber_index = np.repeat(np.arange(nfib), nline)
        x_obs = pixel_centers[group_fibers, :].reshape(-1)
        w_obs = np.tile(wavelengths, nfib)
        valid = np.isfinite(x_obs) & np.isfinite(w_obs)

        n_model_coef = 1 + 3 * n_fcoef
        n_offset_free = max(0, nfib - 1)
        n_parameter = n_model_coef + n_offset_free
        if valid.sum() < n_parameter + 1:
            raise RuntimeError(
                f"Not enough valid line centers for parity fit: "
                f"{valid.sum()} data for {n_parameter} parameters"
            )

        line_reference = np.nanmedian(pixel_centers[group_fibers, :], axis=0)
        offset0 = np.nanmedian(
            pixel_centers[group_fibers, :] - line_reference[None, :], axis=1
        )
        offset0 = np.where(np.isfinite(offset0), offset0, 0.0)
        offset0 -= np.mean(offset0)

        corrected_x = x_obs[valid] - offset0[fiber_index[valid]]
        u0 = (corrected_x - x_ref) / x_scale
        coef_desc = np.polyfit(u0, w_obs[valid], 3)
        common_cubic = coef_desc[::-1]

        smooth_coef0 = np.zeros((3, n_fcoef), dtype=float)
        smooth_coef0[:, 0] = common_cubic[1:4]
        p0 = np.concatenate([
            [common_cubic[0]],
            smooth_coef0.ravel(),
            offset0[:-1] if nfib > 1 else np.empty(0),
        ])

        def unpack(par):
            c0 = par[0]
            smooth_coef = par[1:n_model_coef].reshape(3, n_fcoef)
            if nfib == 1:
                offsets = np.zeros(1, dtype=float)
            else:
                independent = par[n_model_coef:]
                offsets = np.concatenate([independent, [-np.sum(independent)]])
            return c0, smooth_coef, offsets

        def coefficients_at_fiber(smooth_coef, v):
            powers = np.vstack([v**m for m in range(n_fcoef)])
            return smooth_coef @ powers

        def model(par, x, jf):
            c0, smooth_coef, offsets = unpack(par)
            u = (x - offsets[jf] - x_ref) / x_scale
            ck = coefficients_at_fiber(smooth_coef, v_active[jf])
            return c0 + ck[0] * u + ck[1] * u**2 + ck[2] * u**3

        fit_mask = valid.copy()
        for _ in range(4):
            result = least_squares(
                lambda par: model(par, x_obs[fit_mask], fiber_index[fit_mask])
                            - w_obs[fit_mask],
                p0,
                loss='soft_l1',
                f_scale=0.001,
                max_nfev=50000,
                x_scale='jac',
            )
            p0 = result.x
            residual_pm = (w_obs - model(p0, x_obs, fiber_index)) * 1e3
            new_mask = valid & (np.abs(residual_pm) <= max_residual_pm)
            if np.array_equal(new_mask, fit_mask):
                break
            if new_mask.sum() < n_parameter + 1:
                break
            fit_mask = new_mask

        c0, smooth_coef, offsets = unpack(p0)

        def evaluate_local(x, local_index, offset=None):
            if offset is None:
                offset = offsets[local_index]
            u = (np.asarray(x, dtype=float) - offset - x_ref) / x_scale
            ck = coefficients_at_fiber(
                smooth_coef, np.asarray([v_active[local_index]])
            )[:, 0]
            return c0 + ck[0] * u + ck[1] * u**2 + ck[2] * u**3

        coef_values = np.empty((nfib, 4), dtype=float)
        coef_values[:, 0] = c0
        coef_values[:, 1:4] = coefficients_at_fiber(smooth_coef, v_active).T
        residuals = np.full((nfib, nline), np.nan, dtype=float)
        for local_index in range(nfib):
            residuals[local_index, :] = (
                wavelengths - evaluate_local(
                    pixel_centers[group_fibers[local_index], :], local_index
                )
            )

        return {
            'fibers': group_fibers,
            'fiber_ref': float(fiber_ref),
            'fiber_scale': float(fiber_scale),
            'c0': float(c0),
            'smooth_coef': smooth_coef,
            'offsets': offsets,
            'coef_values': coef_values,
            'residuals': residuals,
            'fit_mask': fit_mask.reshape(nfib, nline),
            'evaluate_local': evaluate_local,
        }

    for parity in (0, 1):
        group = active_fibers[active_fibers % 2 == parity]
        parity_results[parity] = fit_one_group(group)

    offsets_all = np.full(nrow, np.nan, dtype=float)
    coef_values_all = np.full((nrow, 4), np.nan, dtype=float)
    residuals_all = np.full_like(pixel_centers, np.nan, dtype=float)
    fit_mask_all = np.zeros_like(pixel_centers, dtype=bool)
    local_lookup = {}

    c0_by_parity = np.full(2, np.nan, dtype=float)
    coef_model_by_parity = np.full((2, 3, n_fcoef), np.nan, dtype=float)
    fiber_ref_by_parity = np.full(2, np.nan, dtype=float)
    fiber_scale_by_parity = np.full(2, np.nan, dtype=float)

    for parity, result in parity_results.items():
        if result is None:
            continue
        fibers = result['fibers']
        c0_by_parity[parity] = result['c0']
        coef_model_by_parity[parity] = result['smooth_coef']
        fiber_ref_by_parity[parity] = result['fiber_ref']
        fiber_scale_by_parity[parity] = result['fiber_scale']
        offsets_all[fibers] = result['offsets']
        coef_values_all[fibers] = result['coef_values']
        residuals_all[fibers] = result['residuals']
        fit_mask_all[fibers] = result['fit_mask']
        for local_index, fiber in enumerate(fibers):
            local_lookup[int(fiber)] = (parity, local_index)

    def evaluate(x, fiber_or_index, offset=None):
        j = int(fiber_or_index)
        if j not in local_lookup:
            raise ValueError(f"Fiber row {j} was not included in the joint fit")
        parity, local_index = local_lookup[j]
        return parity_results[parity]['evaluate_local'](x, local_index, offset)

    return (c0_by_parity, coef_model_by_parity, coef_values_all,
            offsets_all, residuals_all, fit_mask_all, evaluate,
            x_ref, x_scale, fiber_ref_by_parity, fiber_scale_by_parity)

def fib2spec(dat, CxFib, fibwid=7, iFibAct=None, ypix=None, mask=None):
    sz = CxFib.shape
    spec = np.zeros((sz[1], sz[0]), dtype=float)  # spec 配列を初期化

    for j in iFibAct:
        for i in ypix:
            xbin = (CxFib[i,j] + np.arange(fibwid) - (fibwid - 1) / 2).astype(int)
            spec[j,i] = np.sum(dat[i,xbin])            
    
    return spec

def mkWavMap4d(dsno, flgPause=True, fibintwid=5, flgNoWLflat=False,fiberCoefDegree=2):
    df= pd.read_csv(cfg.fileCsv)
    file_idx = df[df.DSNO.isin(dsno)]
    print(dsno)

    kernel =gaussian_kernel(size=151,sigma=51)
    kernel2=gaussian_kernel(size=11,sigma=3)
        
    for index, row in file_idx.iterrows():
    # Create subplots with 4x6 grid
        # loading FITS files
        #fileFSp = cfg.current_dir + (row.FILENAME).replace(".fits",".fsp.fits")
        #fileWMP = cfg.current_dir + (row.FILENAME).replace(".fits",".wmp.fits")
        fileFSp = cfg.fits_path + (row.FILENAME).replace(".fits",f".w{fibintwid:.0f}fsp.fits")
        fileWMP = cfg.fits_path + (row.FILENAME).replace(".fits",f".w{fibintwid:.0f}wmp.fits")        
        print("fileFSP:",fileFSp)
        print("fileWMP:",fileWMP)
        
        #if not os.path.exists(filename):
        #    print(row.DSNO,f"FILENAME ファイルが存在しません: {filename}")
        #    continue
        if not os.path.exists(fileFSp):
            print(cfg.RED+f"{row.DSNO:.0f} *.fsp.fits ファイルが存在しません: {fileFSp}"+cfg.RESET)
            continue
        #elif not os.path.exists(fileWMP):
        #    print(row.DSNO,f"WAVMAP ファイルが存在しません: {fileWMP}")
        #    continue
        
        try:
            with fits.open(fileFSp) as hdu1:
                print("Reading fileFSp",fileFSp)
                #spDat = hdu1[0].data
                spDat = np.asarray(hdu1[0].data, dtype=np.float64)
                hd = hdu1[0].header
                nFibX = hd['NFIBX']
                nFibY = hd['NFIBY']
                nx = hd['NAXIS1']
                ny = hd['NAXIS2']
                iFibAct = hdu1['IFIBERS'].data
                iFib = hdu1['FIBERS'].data
        except Exception as e:print("Error on reading ",fileFSp)
        #iFibAct=[74,75,76]

        if pd.isna(row.WLFLAT): print("No WLFLAT column: "); 
        else:
            #fileFSpWL=cfg.current_dir + (row.WLFLAT).replace(".fits",".fsp.fits")
            fileFSpWL = cfg.fits_path + (row.WLFLAT).replace(".fits",f".w{fibintwid:.0f}fsp.fits")
            if pd.isna(fileFSpWL) or flgNoWLflat:
                print("No WLFLAT: ",fileFSpWL)
                spFlt = np.ones_like(spDat) # all elements are zero
            else:    
                try:
                    with fits.open(fileFSpWL) as hdu2:
                        #print("Reading WLFLAT",fileFSpWL)
                        spFlt = hdu2[0].data            
                except Exception as e:print("Error on reading ",fileFSpWL)

                spDatFlt=np.zeros((ny,nx),dtype=float)
                for j in iFibAct:
                    spDatFlt[j,:] = spDat[j,:] / spFlt[j,:] * np.median(spFlt[j,512:1536])
                spDat=spDatFlt    
                print("Flat fielding was applied to spDat")

        # loading solar spectrum
        pixwav1=row.PIXWAV1; calwav1=row.CALWAV1; wavstep1=row.WAVSTEP1        
        wlinesM = np.array([float(x) for x in row.CALWAVS.split(",")])
        if isinstance(row.PIXWAVS, float) and np.isnan(row.PIXWAVS): pxlinesD0=np.around((wlinesM-calwav1)/wavstep1+pixwav1,decimals=0)
        else: 
            pxlinesD0 = np.array([float(x) for x in row.PIXWAVS.split(",")]) + row.PIXDWAVS
            #sys.exit("ERROR:",file_idx.DSNO)
        #wlinesM = [588.995,589.592]
        print(wlinesM)
        print(", ".join([f"{x:.0f}" for x in pxlinesD0]))
        
        if np.isnan(pixwav1): sys.exit("ERROR:",file_idx.DSNO)
        if np.isnan(wavstep1):sys.exit("ERROR:",file_idx.DSNO)
        if np.isnan(calwav1): sys.exit("ERROR:",file_idx.DSNO)
        print(pixwav1,wavstep1,calwav1)
        xpix=np.arange(nx)
        wpix=(xpix-pixwav1)*wavstep1+calwav1
        wDwav=(pxlinesD0-pixwav1)*wavstep1+calwav1
        #input("Press any key to proceed 0")
        
        if(calwav1 >= 548 and calwav1 <= 568):   fileCal='psg/psgrad548-568.txt'
        elif(calwav1 >= 586 and calwav1 <= 596): fileCal='psg/psgrad586-596.txt'
        elif(calwav1 >= 625 and calwav1 <= 635): fileCal='psg/psgrad625-635.txt'
        elif(calwav1 >= 760 and calwav1 <= 780): fileCal='psg/psgrad760-780.txt'
        else: sys.exit("ERROR:",file_idx.DSNO)
        print("loading Solar spectrum",cfg.current_dir + fileCal)        
        spMdl=np.loadtxt(cfg.current_dir + fileCal,skiprows=14)        
        wavair2vac = 1.000276
        #wavair2vac = 1.000
        for iJ in range(ny):
            spDat[iJ,:]=median_filter(spDat[iJ,:],size=3)
        #input("aabbccdd")
   
        flgPlt=1 
        if flgPlt == 1:
            fig, axes = plt.subplots(4, 1, figsize=(9,10),dpi=96); iFig=0
            plt.subplots_adjust(wspace=0.3, hspace=0.3,left=0.05, right=0.95, top=0.95, bottom=0.05)            
            #plt.get_current_fig_manager().window.wm_geometry("+0-1124")  # ウィンドウ位置を設定 "+X+Y" の形式で位置指定        
            
            #page-1-(1)
            ax = axes[iFig]; iFig += 1 # Calculate grid position
            ax.set(xlim=[np.min(wpix)-0.1,np.max(wpix)+0.1],ylim=(0,1.5))
            #ax.set(xlim=np.array([-1,1])*1.9+589.3,ylim=(0,1.5))
            #ax.plot(spMdl[:,0],spMdl[:,1]/np.median(spMdl[:,1]))
            cv=convolve(spMdl[:,1],kernel,mode='same')
            xm=spMdl[:,0]/wavair2vac
            ax.plot(xm,cv/np.median(cv))
            for i in wlinesM:
                ax.axvline(x=i,color='red',linestyle='--',label=str(i))
                
            plt.draw(); plt.pause(0.01); #input("Press any key to proceed")
            #sys.exit()

        #page-1-(2)
        ax = axes[iFig]; iFig += 1 # Calculate grid position
        #ax.plot(xpix,spDat[iJ,:]/np.median(spDat[iJ,:])*0.6,label='data')
        iJ=0
        ax.plot(xpix,spDat[iJ,:]/np.median(spDat[iJ,:])*0.6,label='data')
        ax.set(ylim=(0,1.0))
        #for i in wDwav:  ax.plot([i,i],[1.03,1.5],color='blue',linestyle='--',label=str(i))
        for i in pxlinesD0:
            ax.axvline(x=i,color='red',linestyle='--',label=str(i))
        #plt.draw(); plt.pause(0.01); #input("Press any key to proceed")

        #fig, axes = plt.subplots(3, 1, figsize=(9,10),dpi=96); iFig=0
        #plt.subplots_adjust(wspace=0.3, hspace=0.3,left=0.05, right=0.95, top=0.95, bottom=0.05)

        #page-1-(3)
        #ax = axes[iFig // 2, iFig % 2]; iFig += 1 # Calculate grid position
        ax = axes[iFig]; iFig += 1 # Calculate grid position
        roix0,roix1,roiy0,roiy1 = 0,2048,0,120
        vrng=[np.percentile(spDat[roiy0:roiy1,roix0:roix1], 2), np.percentile(spDat, 98)]
        im = ax.imshow(spDat[roiy0:roiy1,roix0:roix1], cmap='jet', vmin=vrng[0], vmax=vrng[1],extent=[roix0,roix1,roiy0,roiy1]
                       ,aspect='auto',origin='lower',interpolation='none')            
        ax.set_title(str(row.DSNO)+" "+os.path.basename(fileFSp),fontsize=6)
        ax.tick_params(axis='both', labelsize=6) 
        cbar = fig.colorbar(im, ax=ax, shrink=1)
        cbar.ax.tick_params(labelsize=6)

        #print(pixwav1,wavstep1,calwav1)
        wrng=(np.array([0,nx])-pixwav1)*wavstep1+calwav1
        #print(wrng)
        #plt.show()
        #ax = axes[iFig]; iFig += 1 # Calculate grid position
        
        #ax.plot(spMdl[:,0],convolve(spMdl[:,1],kernel,mode='same'))
        #plt.show()

        #wlinesM=np.array([629.269, 629.391, 629.692 ,629.771, 629.953, 630.020, 630.324, 630.756, 630.831, 631.239, 631.976]) # for GA=6600
        #pxlinesD0=np.array([2402, 2313, 2087, 2028, 1889, 1839, 1606, 1274, 1215, 897, 313])

        #wlinesM=np.array([589.592, 590.568, 590.999, 591.417, 591.626, 592.780]) # for GA=9800
        #pxlinesD0=np.array([2526, 1834, 1523, 1217, 1060, 207])

        #page-1-(4)
        ax = axes[iFig]; iFig += 1 # Calculate grid position
        ax.set(xlim=[np.min(wpix)-0.1,np.max(wpix)+0.1],ylim=(0,1.5))
        iJ=0
        cv=convolve(spMdl[:,1],kernel,mode='same')
        cv=cv/np.median(cv)
        ax.plot(wpix,spDat[iJ,:]/np.median(spDat[iJ,:])*0.6,label='data')
        ax.plot(xm,cv,linewidth=1,label='model')
        ax.legend(fontsize="x-small")
        for i in wlinesM:ax.plot([i,i],[1.03,1.5],color='red',label=str(i))
        for i in wDwav:  ax.plot([i,i],[1.03,1.5],color='blue',linestyle='--',label=str(i))
        
        ### Saving PNG ###
        strDate=((row.FILENAME).replace("fits/",""))[0:8]
        filePng=f"{cfg.png_path}"+(os.path.basename(__file__)).replace('.py','/') \
            +f"{row.DSNO:.0f}/"+(os.path.basename(fileWMP)).replace(".fits","_all-01.png")
        print(filePng)
        
        if not os.path.exists(os.path.dirname(filePng)):os.makedirs(os.path.dirname(filePng))
        plt.savefig(filePng,bbox_inches='tight', pad_inches=0.05)
        plt.draw(); plt.pause(0.01); 

        if flgPause: input("Press any key to proceed 1")
        ######################
        #ax = axes[iFig]; iFig += 1 # Calculate grid position
        #ax.set(xlim=(2400,0),ylim=(0,np.max(spDat[0,:])))
        #ax.plot(pxwav,spDat[0,:])
        #for i in wlinesM:
        #    ax.axvline(x=i,color='red',linestyle='--',label=str(i))
        #ax.axvline(x=calwav1,color='red')    
        
        fig, axes = plt.subplots(7, 4, figsize=(9,10),dpi=96); iFig=0
        plt.subplots_adjust(wspace=0.5, hspace=0.8,left=0.08, right=0.95, top=0.95, bottom=0.05)
        # ウィンドウ位置を設定
        #plt.get_current_fig_manager().window.wm_geometry("+0-1124")  # ウィンドウ位置を設定 "+X+Y" の形式で位置指定        
        
        wavs=np.zeros(len(wlinesM))
        wpix=np.zeros(len(pxlinesD0))
        #print(nx,ny)
        
        wmp=np.zeros((ny,nx))
        dltWMP=np.zeros((ny,len(wlinesM)))
        dltFibY=-12.5 #-44 # pixel
        #dltFibY= 12.5
        #dltFibY= -44
        #dltFibY=+0 #-44 # pixel
        
        ym = cv; xm = spMdl[:,0]/wavair2vac
        for idx, i in enumerate(wlinesM):
            ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]; iFig += 1 # Calculate grid position                  
            xrng=np.array([-0.5,0.5])*0.30 + i          
            #cv =  convolve(spMdl[:,1],kernel,mode='same')
            ixm = (xm >= xrng[0]) & (xm<=xrng[1])

            ax.set(xlim=xrng)
            ax.plot(xm,ym,linewidth=2)
            
            Aini = [-1, i, 0.002, 1]; nterm=len(Aini)
            res = least_squares(residuals4, Aini, args=(xm[ixm], ym[ixm])); par = res.x
            #par, cov = curve_fit(gaussian, xm[ixm], ym[ixm], p0=Aini, maxfev = 300)
            xrng=np.array([-0.5,0.5])*0.07 + par[1]
            ixm = (xm >= xrng[0]) & (xm<=xrng[1])
            res = least_squares(residuals4, Aini, args=(xm[ixm], ym[ixm])); par = res.x

            #par, cov = curve_fit(gaussian, xm[ixm], ym[ixm], p0=Aini, maxfev = 300)            
            yfit = gauss1d(xm[ixm], par)
            ax.plot(xm[ixm],yfit,linestyle="--")
            ax.set_title("{:.3f} => {:.3f}".format(i,par[1]))
            ax.axvline(x=par[1],color='red',linestyle='--') 
            wavs[idx]=par[1]
            #print(par)
            #plt.draw(); plt.pause(0.01);
            
        print(wavs)        
        for k in range(iFig, len(axes.flat)): axes[k // axes.shape[1], k % axes.shape[1]].axis('off')  # 空白の領域を非表示にする    

        
        ### Saving PNG ###
        #strDate=((row.FILENAME).replace("fits/",""))[0:8]
        filePng=f"{cfg.png_path}"+(os.path.basename(__file__)).replace('.py','/') \
            +f"{row.DSNO:.0f}/"+(os.path.basename(fileWMP)).replace(".fits","_all-02.png")
        print(filePng)
        #if not os.path.exists(os.path.dirname(filePng)):os.makedirs(os.path.dirname(filePng))
        plt.savefig(filePng,bbox_inches='tight', pad_inches=0.05)
        plt.draw(); plt.pause(0.01); 
        if flgPause: input("Press any key to proceed 2")
    
        #############################
        ### Start of Data fitting ###

        #plt.show()
        #if j % 2 == 0   : y0even = wmp[j,0]; y0odd = y0even + dltFibY
        #else            : y0odd  = wmp[j,0]; y0even = y0odd - dltFibY
        #y0even=0. ; y0odd=0.
        y0even = pxlinesD0[0]; y0odd = y0even + dltFibY
        #print(ny)
        nBad=np.zeros(ny,dtype=int)
        nBad2=np.zeros(ny,dtype=int)
        sdvarr=np.zeros(ny,dtype=float)

        # Measure all line centers first.  The wavelength solution itself is
        # determined only after all active fibers have been measured.
        pixel_centers = np.full((ny, len(wlinesM)), np.nan, dtype=float)

        for j in iFibAct:
            if j % 2 == 0:
                pxlinesD = pxlinesD0 - pxlinesD0[0] + y0even
            else:
                pxlinesD = pxlinesD0 - pxlinesD0[0] + y0odd

            for idx, predicted_x in enumerate(pxlinesD):
                y = spDat[j, :]
                xd = xpix
                xrng = np.array([-0.5, 0.5]) * 0.12 / wavstep1 + predicted_x
                ixd = (xd >= np.min(xrng)) & (xd <= np.max(xrng))
                yd = y / np.max(y[ixd])

                Aini = [-1, np.mean(xd[ixd]), 5, 1]
                bounds = ([-1.5, np.min(xd[ixd]), 1.5, 0],
                          [0, np.max(xd[ixd]), 20, 1.5])
                res = least_squares(residuals4, Aini, args=(xd[ixd], yd[ixd]),
                                    bounds=bounds, loss='huber')
                par = res.x

                xrng_fine = np.array([-0.5, 0.5]) * 0.05 / wavstep1 + par[1]
                ixd_fine = (xd >= np.min(xrng_fine)) & (xd <= np.max(xrng_fine))
                Aini = [-1, par[1], 5, 1]
                bounds = ([-1.5, np.min(xd[ixd_fine]), 1.5, 0.1],
                          [-0.1, np.max(xd[ixd_fine]), 10, 1.5])
                res = least_squares(residuals4, Aini,
                                    args=(xd[ixd_fine], yd[ixd_fine]),
                                    bounds=bounds, loss='huber')
                pixel_centers[j, idx] = res.x[1]

            # Propagate only the predicted starting position for the next fiber.
            if j % 2 == 0:
                y0even = pixel_centers[j, 0]
                y0odd = y0even + dltFibY
            else:
                y0odd = pixel_centers[j, 0]
                y0even = y0odd - dltFibY

        # Smooth cubic coefficients versus fiber number + independent pixel offset.
        max_residual = 3.0   # pm, clipping threshold used by the joint fit
        max_residual2 = 10.0 # pm, diagnostic threshold only
        (common_c0, fiber_coef_model, fiber_coef_values, pixel_offset,
         dltWMP, fit_mask, eval_smooth, x_ref, x_scale,
         fiber_ref, fiber_scale) = fit_smooth_cubic_with_fiber_offsets(
            pixel_centers, wavs, iFibAct, iFib, nx,
            fiber_coef_degree=fiberCoefDegree,
            max_residual_pm=max_residual,
        )

        for j in iFibAct:
            wmp[j, :] = eval_smooth(xpix, j)
            resid_pm = dltWMP[j, :] * 1e3
            nBad[j] = np.sum(np.abs(resid_pm) > max_residual)
            nBad2[j] = np.sum(np.abs(resid_pm) > max_residual2)
            sdvarr[j] = np.nanstd(resid_pm)

        print(f"Smooth coefficient degree versus fiber number: {fiberCoefDegree}")
        print("Separate even/odd c0 values [even, odd]:", common_c0)
        print("Even/odd fiber-polynomial coefficients for c1, c2, c3:")
        print(fiber_coef_model)
        print("Fiber pixel offsets are constrained to zero mean separately for even and odd fibers.")

        # Recreate and save the individual-fiber diagnostic PNGs.
        for j in iFibAct:
            iFig = 0
            for idx, center_x in enumerate(pixel_centers[j, :]):
                ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]
                iFig += 1
                ax.clear()
                ax.axis('on')

                xd = xpix
                y = spDat[j, :]
                xrng = np.array([-0.5, 0.5]) * 0.12 / wavstep1 + center_x
                ixd = (xd >= np.min(xrng)) & (xd <= np.max(xrng))
                yd = y / np.max(y[ixd])

                xrng_fine = np.array([-0.5, 0.5]) * 0.05 / wavstep1 + center_x
                ixd_fine = (xd >= np.min(xrng_fine)) & (xd <= np.max(xrng_fine))
                Aini = [-1, center_x, 5, 1]
                bounds = ([-1.5, np.min(xd[ixd_fine]), 1.5, 0.1],
                          [-0.1, np.max(xd[ixd_fine]), 10, 1.5])
                res = least_squares(residuals4, Aini,
                                    args=(xd[ixd_fine], yd[ixd_fine]),
                                    bounds=bounds, loss='huber')
                yfit = gauss1d4(xd[ixd_fine], res.x)

                ax.plot(xd, yd, linewidth=1)
                ax.plot(xd[ixd_fine], yd[ixd_fine], linewidth=3, label='data')
                ax.plot(xd[ixd_fine], yfit, '--', linewidth=2, label='line fit')
                ax.axvline(center_x, color='red', linestyle='--', label='center')
                ax.set_xlim(xrng)
                ax.set_title(f"{center_x:.1f}/{wavs[idx]:.3f}")
                if idx == 0:
                    ax.legend(fontsize='x-small')

            ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]
            iFig += 1
            ax.clear()
            ax.axis('on')
            ax.set(xlim=[0, nx], ylim=np.array([-1, 1]) * max_residual,
                   ylabel="delta w [pm]",
                   title=(f"j{j} offset={pixel_offset[j]:+.3f}px "
                          f"nBad={nBad[j]}, nBad2={nBad2[j]}\n"
                          f"std={sdvarr[j]:.2f}pm"))
            ax.plot(pixel_centers[j, :], dltWMP[j, :] * 1e3, 'o-')
            ax.axhline(0, color='black', linewidth=0.6)

            for k in range(iFig, len(axes.flat)):
                axes[k // axes.shape[1], k % axes.shape[1]].axis('off')

            plt.draw()
            plt.pause(0.01)
            filePng = f"{cfg.png_path}" + os.path.basename(__file__).replace('.py', '/') \
                + f"/{row.DSNO:.0f}/" + os.path.basename(fileWMP).replace(".fits", "_iFib") \
                + f"{j:03}.png"
            if not os.path.exists(os.path.dirname(filePng)):
                os.makedirs(os.path.dirname(filePng))
            plt.savefig(filePng, bbox_inches='tight', pad_inches=0.05)
            print(f"j={j:03}, offset={pixel_offset[j]:+.3f} px, "
                  f"nBad={nBad[j]}, nBad2={nBad2[j]}, std={sdvarr[j]:.2f} pm")
            if flgPause:
                input("Press any key to proceed 5")

        if nBad.sum() != 0: 
            for i, val in enumerate(nBad):
                if val != 0: print(f"j={i}: {val} bad column(s)")
            
        # Summary diagnostics.  Plot c1, c2 and c3 separately because their
        # absolute scales differ greatly; a shared y-axis hides the fiber trend.
        fig, axes = plt.subplots(5, 2, figsize=(9,10), dpi=96); iFig = 0
        plt.subplots_adjust(wspace=0.32, hspace=0.72,
                            left=0.07, right=0.95, top=0.97, bottom=0.05)

        #plt.get_current_fig_manager().window.wm_geometry("+0-1124")  # ウィンドウ位置を設定 "+X+Y" の形式で位置指定        
        ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]; iFig += 1 # Calculate grid position                  
        vrng=np.array([-0.5,0.5])*3.9 + np.median(wmp)
        im = ax.imshow(wmp, cmap='jet', vmin=vrng[0], vmax=vrng[1],origin='lower',aspect="auto",interpolation='none')
        ax.set_title(f"{row.DSNO:.0f} {os.path.basename(fileWMP)}",fontsize=8)
        ax.tick_params(axis='both', labelsize=6) 
        cbar = fig.colorbar(im, ax=ax, shrink=1)
        cbar.ax.tick_params(labelsize=6)
        
        ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]; iFig += 1 # Calculate grid position                  
        vrng=[-1,1]
        im = ax.imshow(dltWMP*1E3, cmap='jet', vmin=vrng[0], vmax=vrng[1],origin='lower',aspect="auto",interpolation='none')
        ax.set_title(f"dltWMP (pm), std={np.nanstd(dltWMP[:,:])*1e3:.2f}pm")
        ax.tick_params(axis='both', labelsize=6) 
        cbar = fig.colorbar(im, ax=ax, shrink=1)
        cbar.ax.tick_params(labelsize=6)

        ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]; iFig += 1 # Calculate grid position                  
        ax.plot(iFib[iFibAct],sdvarr[iFibAct])
        ax.set_title("stddev (pm)")

        ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]; iFig += 1 # Calculate grid position                  
        ax.set_title("nBad, nBad2")
        ax.plot(iFib[iFibAct], nBad[iFibAct],label='nBad1')
        ax.plot(iFib[iFibAct],nBad2[iFibAct],label='nBad2',linestyle='--')
        ax.legend()

        ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]; iFig += 1
        even_mask = (iFibAct % 2) == 0
        odd_mask = ~even_mask
        ax.plot(iFib[iFibAct[even_mask]], pixel_offset[iFibAct[even_mask]], 'o-', label='even')
        ax.plot(iFib[iFibAct[odd_mask]], pixel_offset[iFibAct[odd_mask]], 'o-', label='odd')
        ax.axhline(0, color='black', linewidth=0.6)
        ax.legend(fontsize='x-small')
        ax.set_title("fiber pixel offset")
        ax.set_ylabel("offset [pixel]")
        ax.set_xlabel("fiber number")

        def set_coefficient_ylim(axis, values, fractional_margin=0.12):
            """Set a coefficient-specific y range with a small visible margin."""
            values = np.asarray(values, dtype=float)
            values = values[np.isfinite(values)]
            if values.size == 0:
                return
            ymin = np.min(values)
            ymax = np.max(values)
            span = ymax - ymin
            if span <= 0:
                # Preserve visibility even when numerical variation is tiny.
                scale = max(abs(ymin), 1.0)
                margin = scale * 1.0e-6
            else:
                margin = span * fractional_margin
            axis.set_ylim(ymin - margin, ymax + margin)

        # Plot each wavelength-polynomial coefficient in its own panel.
        # This lets matplotlib use an appropriate numerical scale for every
        # coefficient instead of displaying c1, c2 and c3 on one common axis.
        for coef_index, coef_label in zip(range(1, 4), ['c1', 'c2', 'c3']):
            ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]; iFig += 1
            plotted_values = []
            for parity, linestyle, parity_label in [(0, '-', 'even'), (1, '--', 'odd')]:
                group = iFibAct[iFibAct % 2 == parity]
                values = fiber_coef_values[group, coef_index]
                plotted_values.append(values)
                ax.plot(iFib[group], values, marker='o', linestyle=linestyle,
                        ms=3, label=parity_label)
            set_coefficient_ylim(ax, np.concatenate(plotted_values))
            ax.set_title(f"smooth cubic coefficient {coef_label}")
            ax.set_xlabel("fiber number")
            ax.set_ylabel(coef_label)
            ax.grid(alpha=0.25)
            ax.legend(fontsize='x-small')

        for k in range(iFig, len(axes.flat)):
            axes[k // axes.shape[1], k % axes.shape[1]].axis('off')

        plt.draw(); plt.pause(0.01)
        #input("Enter")
        ### FITS OUTPUT ###############
        #hd = fits.Header()
        #hd.extend(hd1[0].header)
        hd['WMPMODEL'] = ('EO-SMOOTH3+OFS', 'even/odd smooth cubic plus offsets')
        hd['WMPXREF'] = (x_ref, 'pixel origin used for normalized cubic')
        hd['WMPXSCL'] = (x_scale, 'pixel scale used for normalized cubic')
        hd['WMPFRE'] = (float(fiber_ref[0]), 'even fiber-number origin')
        hd['WMPFRO'] = (float(fiber_ref[1]), 'odd fiber-number origin')
        hd['WMPFSE'] = (float(fiber_scale[0]), 'even fiber-number scale')
        hd['WMPFSO'] = (float(fiber_scale[1]), 'odd fiber-number scale')
        hd['WMPFDEG'] = (int(fiberCoefDegree), 'degree versus fiber number')
        hd['WMPC0E'] = (float(common_c0[0]), 'even-fiber wavelength c0')
        hd['WMPC0O'] = (float(common_c0[1]), 'odd-fiber wavelength c0')
        hdu_list=[]
        hdu_list.append(fits.PrimaryHDU(data=wmp, header=hd))
        hdu_list.append(fits.ImageHDU(data=iFib, name='FIBERS'))
        hdu_list.append(fits.ImageHDU(data=iFibAct, name='IFIBERS'))
        hdu_list.append(fits.ImageHDU(data=pixel_offset, name='PIXOFS'))
        hdu_list.append(fits.ImageHDU(data=fiber_coef_model, name='COEFMOD'))
        hdu_list.append(fits.ImageHDU(data=fiber_coef_values, name='WAVCOEF'))
        hdu_list.append(fits.ImageHDU(data=pixel_centers, name='LINEPIX'))
        hdu_list.append(fits.ImageHDU(data=dltWMP, name='LINERES'))
        hdul = fits.HDUList(hdu_list)
        hdul.writeto(fileWMP, overwrite=True)
        print(fileWMP," saved")
        ###############################
        
        #plt.show()        
        ### Saving PNG ###
        strDate=((row.FILENAME).replace("fits/",""))[0:8]
        filePng=f"{cfg.png_path}"+(os.path.basename(__file__)).replace('.py','/') \
                +"/"+f"{row.DSNO:.0f}"+"_"+(os.path.basename(fileWMP)).replace(".fits",".png")
        if not os.path.exists(os.path.dirname(filePng)):os.makedirs(os.path.dirname(filePng))
        plt.savefig(filePng,bbox_inches='tight', pad_inches=0.05)
        plt.pause(0.1)       
        ######################                 

    # ウィンドウ位置を設定
    #plt.get_current_fig_manager().window.wm_geometry("+0-1124")  # ウィンドウ位置を設定 "+X+Y" の形式で位置指定        
    plt.show() # stops at this line
    print("All finished")

# スクリプトの最後にこれを追加する
if __name__ == "__main__":
    df= pd.read_csv(cfg.fileCsv)
    file_idx = df[(df.DATATYPE == 'SKY') 
                #& (df.DSNO >= 250630000) & (df.DSNO <= 250710000)
                #& (df.DSNO >= 250707000) & (df.DSNO <= 250710000)
                #& (df.DSNO >= 250824000) & (df.DSNO <= 250825000)
                & (df.DSNO >= 251101000) & (df.DSNO <= 251113000)
                & (df.DSNO % 1000 == 110) 
                  ]    
    dsno = file_idx.DSNO.tolist()
    dsno = [251101110,251102110,251103110,25111110,251112110]
    dsno = [251102110,251103110,25111110,251112110]
    dsno = [251111110]    
    dsno = [251010110]
    dsno = [251214920]
    dsno = [251208110,251208160]
    dsno = [251209110,251209160]
    dsno = [251010110]
    dsno = [251012110]
    dsno = [260402110]
    dsno = [260422110]
    dsno = [260422160]
    dsno = [260423110]
    dsno = [260424110]
    dsno = [260426110]
    dsno = [260427110]
    dsno = [251208160,251209160]
    dsno = [250819100]
    dsno = [251112110]    
    #dsno = [250504110]
    #dsno = [250502110]
    #dsno = [250820110]
    #dsno = [260217160,260217110]    
    #dsno = [260217160]
    #dsno = file_idx.DSNO.astype('int64').tolist()
    dsno = [260811111]
    dsno = [260914111]
    dsno = [260916111]
    print(dsno)
    mkWavMap4d(dsno, flgPause=False, fibintwid=5,
                 flgNoWLflat=True, fiberCoefDegree=2)
    
    