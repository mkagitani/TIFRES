import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy.ndimage import median_filter
from scipy.ndimage import gaussian_filter
from astropy.io import fits
from astropy.time import Time
from astropy.stats import sigma_clip
import pandas as pd
import glob
import os
import sys
import shutil
from datetime import datetime
import cfg

def calc_m2(AARR, i, yFib1, max_back=10):
    """
    AARR[0, i-k, 1] が連続で 0 の場合に、
    最初に 0 でなくなる添字を探して処理します。
    max_back は何ステップ前までチェックするかを指定します。
    """
    # 連続した0の個数を数える
    offset = 1
    while offset <= max_back:
        if AARR[0, i - offset, 1] != 0:
            # ここで 0 でない値が見つかったら終了
            break
        offset += 1

    # offset は「最初に 0 でなくなったときの距離」または
    # max_back+1(=全て0だった) を示す
    # "全て 0 だった" 場合の対策として、テーブル外の
    # 参照エラーに注意してください。
    
    # もし offset が max_back+1 なら、
    # このサンプルでは「すべて0のままだった」ケースとして処理例を用意
    if offset > max_back:
        # 全部 0 だった場合の処理（例: さらに前を参照するなど）
        # ここはお好みのロジックに入れ替えてください
        non_zero_value = 0  # 仮
    else:
        # 見つかった非 0 値を使う
        non_zero_value = AARR[0, i - offset, 1]

    # 連続して 0 だった回数分、yFib1 を掛け算して足す
    # ※問題文中では offset でそのまま倍しているように見えるのでそれを再現
    m2 = non_zero_value + yFib1 * offset
    return m2

def gaussian(x, amplitude, mean, stddev): # ガウス関数の定義
    return amplitude * np.exp(-((x - mean) ** 2) / (2 * stddev ** 2)) 

def gaussian3(x, amplitude, mean, stddev): # ガウス関数の定義
    return amplitude * np.exp(-((x - mean) ** 2) / (2 * stddev ** 2))

def gaussian4(x, amplitude, mean, stddev, base): # ガウス関数の定義
    return amplitude * np.exp(-((x - mean) ** 2) / (2 * stddev ** 2)) + base

def mkFibFit4c(dsno,flgPause=False,finterval=1):
    overwrite=0
    df= pd.read_csv(cfg.fileCsv)
    file_idx = df[df.DSNO.isin(dsno)]
    
    for index, row in file_idx.iterrows():
        fig, axes = plt.subplots(1, 4, figsize=(9,10),dpi=96)
        plt.subplots_adjust(wspace=0.3, hspace=0.3,left=0.05, right=0.95, top=0.95, bottom=0.05)
        idx=0

        print(f"{row.DSNO:.0f}")
        fileDat = cfg.fits_path + row.FILENAME
        fileDark= cfg.fits_path + row.DARKFRAME
        fileFib = cfg.fits_path + (row.FILENAME).replace(".fits",".fib.fits")
        
        if not os.path.exists(fileDat):
            print(df.DSNO,f" ファイルが存在しません: {fileDat}")
            continue
        elif not os.path.exists(fileDark):
            print(df.DSNO,f" ファイルが存在しません: {fileDark}")
            continue
        #elif not os.path.exists(fileFib):
        #    print(df.DSNO,f" ファイルが存在しません: {fileFib}")
        #    continue
        else:    
            if str(row.NFIBXY) == 'nan': nFibX, nFibY = 10, 12
            else:
                tmp=[int(x.strip()) for x in row.NFIBXY.split(',')]
                nFibX, nFibY = tmp[0],tmp[1]
            if str(row.IFIBIACT) == 'nan':  iFibInact = [6,49,69,89,94,109,117]
            else:  iFibInact = [int(x.strip()) for x in row.IFIBIACT.split(',')]
                        
            if str(row.FIBX0) == 'nan': print("no FIBX0 value")
            if str(row.FIBX1) == 'nan': print("no FIBX1 value")
            if str(row.FIBXWID) == 'nan': print("no FIBXWID value")

            iFib = np.arange(nFibX*nFibY)
            iFibAct = np.setdiff1d(iFib,iFibInact)
            yFib0 = df.at[index,'FIBX0']
            yFib1 = df.at[index,'FIBX1']
            ypixFibWid = df.at[index,'FIBXWID']
            print("ypixFibWid:",ypixFibWid)
            
            yfibs0 = np.arange(len(iFib), dtype=float) * yFib1 + yFib0
            yfibs = yfibs0
            
            #print(iFibAct,xpixFibWid,xFib0,xFib1)
            #input("a")
            
            os.makedirs(os.path.dirname(fileFib), exist_ok=True)

            with fits.open(fileDat) as hd1:
                print("reading ",fileDat)
                dat = hd1[0].data
                hd = hd1[0].header
            with fits.open(fileDark) as hd2:
                dk = hd2[0].data
                #header = hdul[0].header
            data = dat - dk
            
            data = median_filter(data,size=(1,5)) # vertical x horizontal
            #data = gaussian_filter(data, sigma=(0, 15))
            
            nx=hd['NAXIS1']
            ny=hd['NAXIS2']
            print(nx,' x ', ny)
            xpix = np.arange(nx,dtype=int)
            #nterm = 3
            AARR = np.zeros((nx,len(iFib),3),dtype=float)

            for j in range(4):
                roix0,roix1,roiy0,roiy1 = 0,nx,int(j*ny/4),int((j+1)*ny/4)
                rng=[np.percentile(data[roiy0:roiy1,roix0:roix1], 2), np.percentile(data[roiy0:roiy1,roix0:roix1], 98)]
                ax=axes[idx]
                
                im = ax.imshow(data[roiy0:roiy1,roix0:roix1], cmap='jet', vmin=rng[0], vmax=rng[1]
                               ,extent=[roix0,roix1,roiy0,roiy1],aspect='auto',origin='lower',interpolation='none')            
                ax.set_title(os.path.basename(fileDat),fontsize=8)
                ax.tick_params(axis='both', labelsize=6) 
                #cbar = fig.colorbar(im, ax=ax, shrink=1)
                #cbar.ax.tick_params(labelsize=6)    
                for i in iFibAct:
                    ax.set(xlim=[roix0,roix1],ylim=[roiy0,roiy1])
                    ax.plot([roix0,roix1],yfibs[i]+[0,0], color='white',linestyle='--', linewidth=1)    
                    if (yfibs[i] > roiy0) & (yfibs[i] < roiy1):
                        ax.text(roix1,yfibs[i],str(i),fontsize=10, verticalalignment='center')
                idx += 1
                
            ### Saving PNG ###
            strDate=(row.FILENAME)[0:8]
            filePng=f"{cfg.png_path}"+(os.path.basename(__file__)).replace('.py','/') \
                +f"{row.DSNO:.0f}/"+(os.path.basename(fileDat)).replace(".fits","_0.png")
            print(f"{row.DSNO:.0f} {filePng}")
            if not os.path.exists(os.path.dirname(filePng)): os.makedirs(os.path.dirname(filePng))
            plt.savefig(filePng,bbox_inches='tight', pad_inches=0.05)
            plt.draw(); plt.pause(0.001)
            if flgPause: input("Press enter to proceed 1")
            ######################
            #plt.close()
            ######################
            #input("aaab")
            ######################
            xpix = np.arange(0,nx,1)
            xpixFStep=finterval
            xpixF = np.arange(0, nx, xpixFStep)
            if xpixF.max() != (nx-1): xpixF=np.append(xpixF,nx-1)
            
            #iFibAct=iFibAct[0,85:]
            #iFibAct=iFibAct[0:20]
            m2=0
            
            flgPlot = False
            flgFitTwice = False

            pnx,pny=4,5
            fig, axes = plt.subplots(pny, pnx, figsize=(9,10),dpi=96); idx=0; iFig2=1
            plt.subplots_adjust(wspace=0.3, hspace=0.3,left=0.05, right=0.95, top=0.95, bottom=0.05)

            ### Fitting Start ##################
            for i in iFibAct:   
                print("iFib/nFib =",i,"/",len(iFib)," ",end='')
                #print("ii, yfibs",ii,yfibs[i])
                for j in xpixF :                    
                #for j in range(xpix.min(),xpix.max(),finterval) :                    
                    if j == 0: m2 = yfibs[i]                                             
                    m2_0=m2
                    ypix0 = (np.arange(ypixFibWid+15,dtype=float)-ypixFibWid/2-7 + m2).astype(int)                            
                    ypix1 = (np.arange(ypixFibWid,dtype=float)-ypixFibWid/2 + 0.5 + m2).astype(int)                            

                    if (j % 256 )==0: print('.', end='')
                    
                    ydat0 = data[ypix0,j]
                    ydat1 = data[ypix1,j]
                    Aini = [np.max(ydat1),np.mean(ypix1),ypixFibWid/5.0]

                    if j == 0 :
                        ax=axes[idx // axes.shape[1], idx % axes.shape[1]]; idx += 1; 
                        ax.plot(ypix1,ydat1, linewidth=2, color='black')                    
                        ax.plot(ypix0,ydat0, linewidth=1, color='black')
                        ax.set_title('iFib='+str(i)+" j="+str(j)+" x="+"{:.2f}".format(AARR[j,i,1]),fontsize=6)
                        #plt.draw(); plt.pause(0.001)
                        #input("Press Enter")            
                        #ax.axvline(xfibs[i],color='green',linestyle='--',linewidth=1)
                    ###################################################3
                    
                    try:
                        param_bounds=([1, np.mean(ypix1)-ypixFibWid/2, 0.1], [1e5, np.mean(ypix1)+ypixFibWid/2, 3])
                        par, cov = curve_fit(gaussian3, ypix1, ydat1, p0=Aini, bounds=param_bounds)                
                        yfit1 = gaussian3(ypix1, *par)
                        
                        if flgFitTwice:
                            ypix1 = (np.arange(ypixFibWid,dtype=float) - ypixFibWid/2 + par[1] + 0.5).astype(int)
                            ydat1 = data[ypix1,j]
                            Aini = [np.max(ydat1),np.mean(ypix1),ypixFibWid/5.0]
                            param_bounds=([1, np.mean(ypix1)-ypixFibWid/2, ypixFibWid/10], [1e5, np.mean(ypix1)+ypixFibWid/2, ypixFibWid/2])
                            par, cov = curve_fit(gaussian3, ypix1, ydat1, p0=Aini, bounds=param_bounds)
                            yfit1 = gaussian3(ypix1, *par)

                        m2=par[1]
                    except RuntimeError as e:
                        print(f"Fitting failed for iFib={i}, j={j}: {e}")
                        input("Press Enter To Proceed 3")
                        continue
                    #print("ypixFibWid",ypixFibWid)
                    AARR[j,i,:] = par
                    if j == 0 :
                        yfibs0=yfibs
                        dlt = -yfibs0[i]+par[1]
                        yfibs = yfibs0 + dlt
                        #print(dlt,yfibs0[i],yfibs[i])

                    if j == 0 & flgPlot:
                        ax.plot(ypix1,yfit1, linewidth=2,color='red')                    
                        ax.plot(ypix1,ydat1,color='blue',marker='o')                    

                        ax.axvline(x=yfibs[i],color='green',linestyle='--')
                        if i>0: ax.axvline(x=yfibs[i-1],color='green',linestyle='--')
                        if i<(len(yfibs)-1): ax.axvline(x=yfibs[i+1],color='green',linestyle='--')

                        ax=axes[idx // axes.shape[1], idx % axes.shape[1]]; idx += 1
                        roix0,roix1,roiy0,roiy1 = 0,nx,int(yfibs[i]-32),int(yfibs[i]+32)
                        rng=[np.percentile(data[roiy0:roiy1,roix0:roix1], 2), np.percentile(data[roiy0:roiy1,roix0:roix1], 98)]                
                        im = ax.imshow(data[roiy0:roiy1,roix0:roix1], cmap='jet', vmin=rng[0], vmax=rng[1]
                               ,extent=[roix0,roix1,roiy0,roiy1],aspect='auto',origin='lower',interpolation='none')            
                        ax.set_title(os.path.basename(fileDat),fontsize=8)
                        ax.tick_params(axis='both', labelsize=6) 
                        #cbar = fig.colorbar(im, ax=ax, shrink=1)
                        #cbar.ax.tick_params(labelsize=6)    
                        for i2 in iFibAct:
                            ax.set(xlim=[roix0,roix1],ylim=[roiy0,roiy1])
                            ax.plot([roix0,roix1],yfibs[i2]+[0,0], color='white',linestyle='--', linewidth=1)    
                        ax.text(roix1,yfibs[i],str(i),fontsize=10, verticalalignment='center')
                            
                        plt.draw(); plt.pause(0.001)
                        #input("Press Enter 2")            
                        #ax.axvline(xfibs[i],color='green',linestyle='--',linewidth=1)
                    ###################################################3
                    if j == nx-1 :                        

                        ax=axes[idx // axes.shape[1], idx % axes.shape[1]]; idx += 1
                        #(0)
                        nterm2=6
                        coef = np.polyfit(xpixF,AARR[xpixF,i,1],nterm2)
                        xfitF = np.polyval(coef,xpixF)
                        residuals = AARR[xpixF, i, 1] - xfitF
                        sigma = np.std(residuals)
                        mask = np.abs(residuals) <= 3.0 * sigma
                        coef = np.polyfit(xpixF[mask], AARR[xpixF, i, 1][mask], nterm2)
                        xfit = np.polyval(coef,xpix)
                        ax.plot(xpixF,AARR[xpixF,i,1]-xfit[xpixF],linewidth=0.5)
                        ax.set(ylim=[-0.1,0.1],xlim=[0,nx])
                        ax.tick_params(axis='both', labelsize=6) 
                        ax.axhline(y=0,color='black',linestyle='--',linewidth=0.5)
                        AARR[xpix,i,1] = xfit

                        #if flgPause: plt.draw(); plt.pause(0.001)

                        #(1)
                        ax=axes[idx // axes.shape[1], idx % axes.shape[1]]; idx += 1
                        #ax.axvline(par[1],color='black',linestyle='--',linewidth=1)
                        roix0,roix1,roiy0,roiy1 = 0,nx,int(np.median(AARR[:,i,1])-ypixFibWid*2),int(np.median(AARR[:,i,1])+ypixFibWid*3)
                        vrng=[np.percentile(data[roiy0:roiy1,roix0:roix1], 2), np.percentile(data[roiy0:roiy1,roix0:roix1], 90)]
                        im = ax.imshow(data[roiy0:roiy1,roix0:roix1], cmap='jet', vmin=vrng[0], vmax=vrng[1],extent=[roix0,roix1,roiy0,roiy1],aspect='auto',origin='lower',interpolation='none')            
                        ax.set_title('iFib='+str(i),fontsize=6)
                        ax.tick_params(axis='both', labelsize=6) 
                        cbar = fig.colorbar(im, ax=ax, shrink=1)
                        cbar.ax.tick_params(labelsize=5)                            
                        ax.set(xlim=[roix0,roix1],ylim=[roiy0,roiy1])
                        ax.plot(xpix,AARR[:,i,1], color='black',linestyle='-', linewidth=0.5)
                        ax.plot(xpix,AARR[:,i,1]-ypixFibWid/2, color='black',linestyle='-', linewidth=0.5)
                        ax.plot(xpix,AARR[:,i,1]+ypixFibWid/2, color='black',linestyle='-', linewidth=0.5)                        
                        ax.plot(xpix,AARR[:,i,1], color='white',linestyle='--', linewidth=0.5)
                        ax.plot(xpix,AARR[:,i,1]-ypixFibWid/2, color='white',linestyle='--', linewidth=0.5)
                        ax.plot(xpix,AARR[:,i,1]+ypixFibWid/2, color='white',linestyle='--', linewidth=0.5)                        
                print(" done")    
                #print(idx,len(axes.flat))
                #if flgPause: input("Press enter to proceed 4")

                if idx == len(axes.flat): 

                    plt.draw(); plt.pause(0.001)
                    if flgPause: input("Press Enter To Continue, 5" )       
                    ### Saving PNG ###
                    filePng=f"{cfg.png_path}"+(os.path.basename(__file__)).replace('.py','/') \
                        +f"{row.DSNO:.0f}/"+(os.path.basename(fileDat)).replace(".fits","_"+str(iFig2)+".png")
                    if not os.path.exists(os.path.dirname(filePng)): os.makedirs(os.path.dirname(filePng))
                    plt.savefig(filePng,bbox_inches='tight', pad_inches=0.05)
                    plt.close()
                        
                    idx=0; iFig2 +=1
                    fig, axes = plt.subplots(pny, pnx, figsize=(9,10),dpi=96)
                    plt.subplots_adjust(wspace=0.3, hspace=0.3,left=0.05, right=0.95, top=0.95, bottom=0.05)


                #plt.draw();  plt.pause(0.001); #input("Press Enter")            
            #input("Press Enter")
                        
            ######################

            for j in range(idx, len(axes.flat)):axes[j // axes.shape[1], j % axes.shape[1]].axis('off')  # 空白の領域を非表示にする    
            plt.draw()
            
            ### Saving PNG ###
            filePng=f"{cfg.png_path}"+(os.path.basename(__file__)).replace('.py','/') \
                +f"{row.DSNO:.0f}/"+(os.path.basename(fileDat)).replace(".fits","_"+str(iFig2)+".png")
            print(filePng)            
            if not os.path.exists(os.path.dirname(filePng)): os.makedirs(os.path.dirname(filePng))
            plt.savefig(filePng,bbox_inches='tight', pad_inches=0.05)            
            plt.close()
            ###############################
            
            ### FITS OUTPUT ###############
            if 1==1:
                #hd = fits.Header()
                #hd.extend(hd1[0].header)
                hd['NFIBX'] = nFibX
                hd['NFIBY'] = nFibY
                hdu_list=[]
                xfib=np.arange(0,nx,1)
                ypix=np.arange(0,ny,1)
                hdu_list.append(fits.PrimaryHDU(data=AARR.astype(float), header=hd))
                hdu_list.append(fits.ImageHDU(data=xfib, name='YFIB'))
                hdu_list.append(fits.ImageHDU(data=iFib, name='IFIB'))
                hdu_list.append(fits.ImageHDU(data=xpix, name='XPIXEL'))
                hdu_list.append(fits.ImageHDU(data=ypix, name='YPIXEL'))
                hdu_list.append(fits.ImageHDU(data=iFib, name='FIBERS'))
                hdu_list.append(fits.ImageHDU(data=iFibAct, name='IFIBERS'))
                hdul = fits.HDUList(hdu_list)
                hdul.writeto(fileFib, overwrite=True)
                print("Saved: ",fileFib)
            ###############################
     
    print("All finsihed")   
    
    #plt.show()

# スクリプトの最後にこれを追加する
if __name__ == "__main__":
    df= pd.read_csv(cfg.fileCsv)
    file_idx = df[((df.DATATYPE == 'WLFLAT')) 
                  #& (df.DSNO > 250707000) & (df.DSNO < 250710000)
                  #& (df.DSNO > 250824000) & (df.DSNO < 250825000)
                  & (df.DSNO >  251101000) & (df.DSNO < 251113000)
                  & (df.DSNO % 1000 == 10)
                  ]    
    dsno = file_idx.DSNO.astype('int64').tolist()
    #dsno = [251009010]
    #dsno = [251112010]
    dsno = [251101010,251102010,251103010,251111010,251112010]
    dsno = [251112010]
    dsno = [250819010]
    dsno = [251010010]
    dsno = [251214910]
    dsno = [251208010,251208060]
    dsno = [251209010,251209060]
    dsno = [251209060]
    dsno = [260320010]
    dsno = [251010010]
    dsno = [251012010]

    dsno = [260406110]
    dsno = [260402110]
    dsno = [260422110,260422160]
    dsno = [260423110]
    dsno = [260424110]
    dsno = [260426110]
    dsno = [260427110]
    dsno = [250504010]
    dsno = [250502010]
    dsno = [250820010]
    dsno = [260217060]
    dsno = [260811010]
    dsno = [260914010]
    dsno = [260916010]

    print(dsno)    
    #input("aa")
    mkFibFit4c(dsno,flgPause=False,finterval=16)
