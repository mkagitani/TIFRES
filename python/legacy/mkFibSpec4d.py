import numpy as np
import matplotlib.pyplot as plt
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

def fib4spec(dat, CxFib, fibwid=5, iFibAct=None, xpix=None, mask=None,type=None):
    #print('fibwid',fibwid)
    sz = CxFib.shape
    spec = np.zeros((sz[1], sz[0]), dtype=float)  # spec 配列を初期化

    for j in iFibAct:
        for i in xpix:
            ybin = (CxFib[i,j] + 0.5 + np.arange(fibwid) - (fibwid - 1) / 2).astype(int)
            if type == None: 
                spec[j,i] = np.sum(dat[ybin,i])                
            elif type == "median"   : 
                spec[j,i] = np.median(dat[ybin,i])
            elif type == "mean"   : 
                spec[j,i] = np.mean(dat[ybin,i])
            elif type == "min": 
                spec[j,i] = np.min(dat[ybin,i])
            elif type == "max": 
                spec[j,i] = np.max(dat[ybin,i])
    return spec

import numpy as np

def fib4specV(dat, CxFib, iFibAct, fibwid=7, xpix=None, type='sum'):
    """
    dat   : (ny, nx)      原画像（y:縦, x:横）
    CxFib : (nx, nFibAll) 各 x 列における全ファイバ（含むdead）の中心y
    iFibAct : 1D index    アクティブなファイバ列のインデックス
    fibwid  : int         y方向の積分幅
    xpix    : 1D index    計算する x のインデックス（None なら全x）
    type    : str         'sum' | 'median' | 'mean' | 'min' | 'max'

    return : spec (nFibAll, nx_sel)  非アクティブ列は 0
    """
    ny, nx = dat.shape
    nx_c, nFibAll = CxFib.shape
    if nx_c != nx:
        raise ValueError(f"dat.shape[1]({nx}) と CxFib.shape[0]({nx_c}) が一致していません。")

    # x 範囲
    if xpix is None:
        xpix = np.arange(nx, dtype=np.int32)
    else:
        xpix = np.asarray(xpix, dtype=np.int32)

    # アクティブ列のみ抽出: (nx_sel, nFibAct)
    iFibAct = np.asarray(iFibAct, dtype=np.int32)
    if iFibAct.size == 0:
        return np.zeros((nFibAll, xpix.size), dtype=np.float32)

    C_act = CxFib[np.ix_(xpix, iFibAct)]        # (nx_sel, nFibAct)

    # 積分窓の相対オフセット（中心化）
    offs = (0.5 + np.arange(fibwid) - (fibwid - 1)/2.0).astype(np.float32)  # (fibwid,)

    # y インデックス（丸め→端クリップ）: (nx_sel, nFibAct, fibwid)
    y_idx = np.rint(C_act[..., None] + offs[None, None, :]).astype(np.int32)
    y_idx = np.clip(y_idx, 0, ny - 1)

    # x インデックスをブロードキャスト
    x_idx = np.broadcast_to(xpix[:, None, None], y_idx.shape).astype(np.int32)

    # 画素抽出: (nx_sel, nFibAct, fibwid)
    vals = dat[y_idx, x_idx]

    # 集約 → (nx_sel, nFibAct)
    if type == 'sum':
        spec_act_T = vals.sum(axis=2)
    elif type == 'median':
        spec_act_T = np.median(vals, axis=2)
    elif type == 'mean':
        spec_act_T = vals.mean(axis=2)
    elif type == 'min':
        spec_act_T = vals.min(axis=2)
    elif type == 'max':
        spec_act_T = vals.max(axis=2)
    else:
        raise ValueError("type must be 'sum', 'median', 'mean', or 'max'")

    # (nFibAct, nx_sel) にして full 配列へ埋め戻し
    spec_act = spec_act_T.T.astype(np.float32, copy=False)   # (nFibAct, nx_sel)
    spec_full = np.zeros((nFibAll, xpix.size), dtype=np.float32)
    spec_full[iFibAct, :] = spec_act
    return spec_full


def mkFibSpec4d(dsno,flgPause=False,flgShowAll=False,fibintwid=5,overwrite=True):
    df= pd.read_csv(cfg.fileCsv)
    file_idx = df[df.DSNO.isin(dsno)]
    
    for index, row in file_idx.iterrows():
        print(f"{row.DSNO:.0f} ",end='')        
        fileDat = cfg.fits_path + row.FILENAME
        fileDark= cfg.fits_path + row.DARKFRAME
        fileFSp = cfg.fits_path + (row.FILENAME).replace(".fits",f".w{fibintwid:.0f}fsp.fits")
        fileFib = cfg.fits_path + (row.WLFLAT).replace(".fits",".fib.fits")
        
        if (os.path.exists(fileFSp) and not overwrite):
            print(cfg.RED+f"Skipped: {row.DSNO:.0f} {fileFSp}"+cfg.RESET)
            continue
        elif not os.path.exists(fileDat):
            print(cfg.RED+f"{row.DSNO:.0f} ",f" fileDat, ファイルが存在しません: {fileDat}"+cfg.RESET)
            continue
        elif not os.path.exists(fileDark):
            print(cfg.RED+f"{row.DSNO:.0f} ",f" fileDark, ファイルが存在しません: {fileDark}"+cfg.RESET)
            continue
        elif not os.path.exists(fileFib):
            print(cfg.RED+f"{row.DSNO:.0f} ",f" fileFib, ファイルが存在しません: {fileFib}"+cfg.RESET)
            continue
        else:
            xpixFibWid=fibintwid    
            #xpixFibWid = df.at[index,'FIBINTWID']                         
            print("FIBINTWID:",xpixFibWid)
            with fits.open(fileDat) as hdu1:
                dat = hdu1[0].data
                hd1 = hdu1[0].header
                nx=hd1['NAXIS1']
                ny=hd1['NAXIS2']
            with fits.open(fileDark) as hdu2:
                dk = hdu2[0].data
                #header = hdul[0].header
            data = dat - dk

            with fits.open(fileFib) as hdu3:
                AARR = hdu3[0].data
                hd3 = hdu3[0].header
                yFib = hdu3['YFIB'].data
                iFibAct = hdu3['IFIBERS'].data
                iFib = hdu3['FIBERS'].data
                nFibX=hd3['NFIBX']
                nFibY=hd3['NFIBY']
        
            iFibPkW = np.concatenate(( [[-1],iFib,[np.max(iFib)+1]]))
            iFibVlW = iFibPkW + 0.5
            fxPkW = np.zeros((nx,len(iFibPkW))) # flux at peak
            fxVlW = np.zeros((nx,len(iFibVlW))) # flux at valley            
            
            #print(iFibPkW)
            #print(iFibVlW)
            #input("ggok")

            ### Slower code ###
            for j in range(nx):
                ifunct= interp1d(iFibAct,AARR[j,iFibAct,1], kind='linear', fill_value="extrapolate")
                fxPkW[j,:]  = ifunct(iFibPkW)
                fxVlW[j,:]  = ifunct(iFibVlW)
            ###################
            ### Faster code ###
            f_all = interp1d(iFibAct,AARR[:, iFibAct, 1],      # 形: (nx, len(iFibAct))
                kind='linear',axis=1,fill_value="extrapolate",assume_sorted=True)
            
            iFibPkW = np.r_[-1, iFib, np.max(iFib) + 1]      # サンプリング点（番兵を両端に追加）
            iFibVlW = iFibPkW + 0.5
            fxPkW = f_all(iFibPkW)        # 形: (nx, len(iFib)+2)
            fxVlW = f_all(iFibVlW)        # 形: (nx, len(iFib)+2)
            ########################            
            fxPk = fxPkW[:,1:len(iFib)+1] # 中央（実ファイバー分）だけ取り出し

            xpix = np.arange(nx,dtype=int)
            ypix = np.arange(ny,dtype=int)            
            spDat = fib4specV(data, fxPk, fibwid=xpixFibWid, iFibAct=iFibAct, xpix=xpix)
            
            #type='mean' 
            #type='median' 
            type='min'
            spDk1 = fib4specV(data, fxVlW[:,0:len(iFib)]  , fibwid=5, iFibAct=iFibAct, xpix=xpix,type=type)
            spDk2 = fib4specV(data, fxVlW[:,1:len(iFib)+1], fibwid=5, iFibAct=iFibAct, xpix=xpix,type=type)
            spDk = (spDk1+spDk2)/2.0 * xpixFibWid
            spDat2 = spDat - spDk 
            spImg=np.zeros((nFibY,nFibX),dtype=float)

            for k in iFibAct:
                ix = k % nFibX  # 剰余演算
                iy = k // nFibX  # 商の整数部
                spImg[iy, ix] = np.median(spDat[k,:])  # spDat の iFib[i] 列の中央値を計算

            roix0,roix1,roiy0,roiy1 = 1500,1900,0,len(iFib)
            #input("a")
            #print(len(iFib))
            #roix0r,roix1r,roiy0r,roiy1r = roix0,roix1,min(ypix),max(ypix)
            if flgShowAll: arr=iFibAct
            else: arr=[55]
            for j in arr:
                #j=55
                fig = plt.figure(figsize=(9,10),dpi=96)
                gs  = gridspec.GridSpec(5,2,height_ratios=[1,1,1,1,1],width_ratios=[14,1])
                #fig, axes = plt.subplots(3, 2, figsize=(9,10),dpi=96,gridspec_kw={'width_ratios': [14,1]}); iFig=0
                plt.subplots_adjust(wspace=0.0, hspace=0.3,left=0.08, right=0.95, top=0.95, bottom=0.05)            
                
                #ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]; iFig += 1 # Calculate grid position
                #ax=axes[iFig]; iFig += 1
                ax = fig.add_subplot(gs[0, 0])
                vrng=[0, np.percentile(data[:,roix0:roix1+1], 99)]
                im = ax.imshow(data[:,roix0:roix1+1], cmap='jet', vmin=vrng[0], vmax=vrng[1],origin='lower',interpolation='none',aspect="auto"
                               ,extent=[roix0-0.5,roix1+0.5,np.min(ypix),np.max(ypix)])
                ax.set_title("data: "+os.path.basename(fileDat),fontsize=8)
                ax.tick_params(axis='both', labelsize=6) 
                #ax.axhline(y=j,color='black',linewidth=1); ax.axhline(y=j,color='white',linestyle='--',linewidth=1)
                ax = fig.add_subplot(gs[0, 1]); ax.axis('off')
                cbar = fig.colorbar(im, ax=ax, shrink=1)
                cbar.ax.tick_params(labelsize=6)
                
    #            ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]; iFig += 1 # Calculate grid position
                ax = fig.add_subplot(gs[1, 0])
                vrng=[0, np.percentile(spDat[roiy0:roiy1+1,roix0:roix1+1], 99)]
                im = ax.imshow(spDat[roiy0:roiy1+1,roix0:roix1+1], cmap='jet', vmin=vrng[0], vmax=vrng[1],origin='lower',interpolation='none',aspect="auto"
                               ,extent=[roix0-0.5,roix1+0.5,roiy0-0.5,roiy1+0.5])
                ax.set_title("spDat: "+os.path.basename(fileFib),fontsize=8)
                ax.tick_params(axis='both', labelsize=6) 
                ax.axhline(y=j,color='black',linewidth=1); ax.axhline(y=j,color='white',linestyle='--',linewidth=1)
                ax = fig.add_subplot(gs[1, 1]); ax.axis('off')
                cbar = fig.colorbar(im, ax=ax, shrink=1)
                cbar.ax.tick_params(labelsize=6)

                ax = fig.add_subplot(gs[2, 0])
                vrng=[0, np.percentile(spDk[roiy0:roiy1+1,roix0:roix1+1], 99)]
                im = ax.imshow(spDk[roiy0:roiy1+1,roix0:roix1+1], cmap='jet', vmin=vrng[0], vmax=vrng[1],origin='lower',interpolation='none',aspect="auto"
                               ,extent=[roix0-0.5,roix1+0.5,roiy0-0.5,roiy1+0.5])
                ax.set_title("spDk: "+os.path.basename(fileFib),fontsize=8)
                ax.tick_params(axis='both', labelsize=6) 
                ax.axhline(y=j,color='black',linewidth=1); ax.axhline(y=j,color='white',linestyle='--',linewidth=1)
                ax = fig.add_subplot(gs[2, 1]); ax.axis('off')
                cbar = fig.colorbar(im, ax=ax, shrink=1)
                cbar.ax.tick_params(labelsize=6)

    #            ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]; iFig += 1 # Calculate grid position
                ax = fig.add_subplot(gs[3, 0])
                vrng=[0, np.percentile(spDat2[roiy0:roiy1+1,roix0:roix1+1], 99)]
                im = ax.imshow(spDat2[roiy0:roiy1+1,roix0:roix1+1], cmap='jet', vmin=vrng[0], vmax=vrng[1],origin='lower',interpolation='none',aspect="auto"
                               ,extent=[roix0-0.5,roix1+0.5,roiy0-0.5,roiy1+0.5])
                ax.set_title("spDat2: "+os.path.basename(fileFib),fontsize=8)
                ax.tick_params(axis='both', labelsize=6) 
                ax.axhline(y=j,color='black',linewidth=1); ax.axhline(y=j,color='white',linestyle='--',linewidth=1)
                ax = fig.add_subplot(gs[3, 1]); ax.axis('off')
                cbar = fig.colorbar(im, ax=ax, shrink=1)
                cbar.ax.tick_params(labelsize=6)

                ax = fig.add_subplot(gs[4, 1]); ax.axis('off')                
                ax = fig.add_subplot(gs[4, 0])
                ax.set_title(f"iFibAct={j},   Mean:{np.mean(spDat2[j,roix0:roix1]):.2f},   Std:{np.std(spDat2[j,roix0:roix1]):.2f},   "
                            +f"S/N:{np.mean(spDat2[j,roix0:roix1])/np.std(spDat2[j,roix0:roix1]):.2f}",fontsize=10)
                ax.set(xlim=[roix0,roix1+1],ylim=np.max(spDat[j:roix0:roix1+1])*np.array([-0.05,+1.05]), xlabel='pixel',ylabel='Count')                
                ax.plot(xpix,spDat[j,:],label="spDat")                
                ax.plot(xpix,spDat2[j,:],label="spDat2")
                ax.plot(xpix,spDat2[j,:]*100.0,label="spDat2x100")
                ax.plot(xpix,spDk[j,:],label="spDk")
                ax.tick_params(axis='both', labelsize=6) 
                ax.axhline(y=0,color='black',linestyle='--',linewidth=0.5)
                ax.legend(loc="upper right")

                #flgPause=True
                #if flgPause: plt.draw(); plt.pause(0.01); input("aaa")
                #input("ccg")
                ### Saving PNG ###
                strDate=((row.FILENAME).replace("fits/",""))[0:8]
                filePng=f"{cfg.png_path}"+(os.path.basename(__file__)).replace('.py','/'+strDate+'/') \
                    +f"{row.DSNO:.0f}"+"_"+(os.path.basename(fileDat)).replace(".fits","_ifib")+f"{j:03}"+'.png'
                if not os.path.exists(os.path.dirname(filePng)): os.makedirs(os.path.dirname(filePng))
                plt.savefig(filePng,bbox_inches='tight', pad_inches=0.05)                
                if cfg.pythonide == 'spyder': plt.show()
                ######################
                
                if flgPause: 
                    plt.draw(); 
                    input("Press Enter to Continue 5")
                plt.close()

            #for j in range(iFig, len(axes.flat)):  axes[j // axes.shape[1], j % axes.shape[1]].axis('off')  # 空白の領域を非表示にする    

            #plt.draw(); plt.pause(0.001)
            
            ### FITS OUTPUT ###############
            #hd = fits.Header()
            hd1['NFIBX'] = nFibX
            hd1['NFIBY'] = nFibY
            hd1['FIBINTWI'] = fibintwid
            #hd.extend(hd1[0].header)
            hdu_list=[]
            hdu_list.append(fits.PrimaryHDU(data=spDat2.astype(np.float32), header=hd1))
            hdu_list.append(fits.ImageHDU(data=spDat.astype(np.float32), header=hd1, name='spDat'))
            hdu_list.append(fits.ImageHDU(data=spDk.astype(np.float32), header=hd1, name='spDk'))
            hdu_list.append(fits.ImageHDU(data=iFib.astype(np.int16), name='FIBERS'))
            hdu_list.append(fits.ImageHDU(data=iFibAct.astype(np.int16), name='IFIBERS'))            
            hdu4 = fits.HDUList(hdu_list)
            hdu4.writeto(fileFSp, overwrite=True)
            print(f"{row.DSNO:.0f}"+": "+fileFSp," saved")
            ###############################        
    print("All finished")    
    
# スクリプトの最後にこれを追加する
if __name__ == "__main__":
    df= pd.read_csv(cfg.fileCsv)
    file_idx = df[(df.DATATYPE != 'BADDATA') & (df.DATATYPE != 'DARK') & (df.DATATYPE != 'NONE') 
                #& (df.DSNO >=  250502000) & (df.DSNO < 250502990)
                #& (df.DSNO >=  250504000) & (df.DSNO < 250504990)
                #& (df.DSNO >= 250630000) & (df.DSNO <= 250720000)
                #& (df.DSNO >= 250707000) & (df.DSNO < 250710000)
                #& (df.DSNO >= 250820000) & (df.DSNO < 250821000)
                #& (df.DSNO >= 251101000) & (df.DSNO < 251113000)
                #& (df.DSNO >  250819000) & (df.DSNO < 250820000)
                #& (df.DSNO >  251010900) & (df.DSNO < 251010990)
                #& (df.DSNO >=  251214900) & (df.DSNO < 251214990)
                #& ((df.DSNO % 1000 < 200) | ( (df.DSNO % 1000 > 200) & (df.DSNO % 25 == 0) ))
                #& ( (df.DSNO % 1000 < 200) | (df.DSNO % 25 == 0))
                #& ( (df.DSNO % 1000 < 200) | (df.DSNO % 1000 > 200) & (df.DSNO % 25 == 0) )
                #and (df.DATATYPE == 'MERCURY')
                #& (df.DSNO >=  251209000) & (df.DSNO < 251209200)
                #& (df.DSNO >=  260320209) & (df.DSNO < 260320900)
                #& (df.DSNO >=  251010010) & (df.DSNO < 251010990)
                #& (df.DSNO >=  251012010) & (df.DSNO < 251012990)
                #& (df.DSNO >=  251112010) & (df.DSNO < 251112990)
                #& (df.DSNO >=  251209100) & (df.DSNO < 251209990)
                #& (df.DSNO >=  260217300) & (df.DSNO < 260217990)
                #& (df.DSNO >=  260406110) & (df.DSNO < 260406990)
                #& (df.DSNO >=  260422110) & (df.DSNO < 260422990)
                #& (df.DSNO >=  260423110) & (df.DSNO < 260423990)
                #& (df.DSNO >=  260424110) & (df.DSNO < 260424990)
                #& (df.DSNO >=  260427110) & (df.DSNO < 260427990)
                #& (df.DSNO >=  260811010) & (df.DSNO < 260811990)
                #& (df.DSNO >=  260915161) & (df.DSNO < 260915990)
                #& (df.DSNO >=  260916000) & (df.DSNO < 260916990)
                & (df.DSNO >=  260917164) & (df.DSNO < 260917900)
                ]    
    dsno = file_idx.DSNO.astype('int64').tolist()
    #dsno = [251112129,251112200,251112201]
    #dsno = [251112110]
    #dsno = [251010110]
    #dsno = [260320010]
    #dsno = [251012110]
    #dsno = [251111111]
    #dsno = [250820200,250820250,250820275,250820300,250820400,250820425,250820450,250820475,250820500,250820525,250820550,250820575]

    print(dsno)
    mkFibSpec4d(dsno,overwrite=True,flgPause=False,fibintwid=5)#,flgShowAll=True)