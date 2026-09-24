import numpy as np
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from astropy.io import fits
from astropy.time import Time
from astropy.stats import sigma_clip
from scipy.ndimage import median_filter, binary_dilation, generate_binary_structure
from scipy.ndimage import gaussian_filter, laplace
import pandas as pd
import glob
import os
import re
import sys
import shutil
import time
from datetime import datetime
import cfg
#from pathlib import Path

def _fits_writeto_retry(
        path,
        data,
        header,
        attempts=10,
        base_delay=0.5,
        max_delay=5.0):
    """
    FITSを一時ファイルに書き込み、その後os.replace()で最終名へ置換する。

    Windowsで出力先ファイルがDS9、FITSビューア、Explorer、
    同期ソフトなどに掴まれている場合は、名前変更のみを再試行する。

    一時FITSは最初の1回だけ書き込み、再試行ごとには書き直さない。
    """
    path = os.path.abspath(path)
    out_dir = os.path.dirname(path)

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    tmp = f"{path}.tmp.{os.getpid()}.{time.time_ns()}"

    # 一時FITSは1回だけ作成する
    try:
        fits.PrimaryHDU(
            data=np.asarray(data),
            header=header
        ).writeto(tmp, overwrite=True)
    except Exception:
        # 書き込み途中の不完全ファイルだけ削除
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        raise

    last_err = None

    for i in range(attempts):
        try:
            os.replace(tmp, path)

            print(f"[INFO] FITS saved: {path}")
            return

        except PermissionError as e:
            last_err = e

            if i >= attempts - 1:
                break

            delay = min(
                max_delay,
                base_delay * (1.5 ** i)
            )

            print(
                f"[WARN] Cannot replace FITS file "
                f"({i + 1}/{attempts}):\n"
                f"       target = {path}\n"
                f"       The target may be open in DS9, a FITS viewer, "
                f"Explorer preview, or another Python process.\n"
                f"       Retrying in {delay:.1f} s...",
                flush=True
            )

            time.sleep(delay)

        except Exception as e:
            last_err = e
            break

    # 置換できなかった場合、一時FITSは有効な可能性があるため保存する
    raise PermissionError(
        f"Failed to replace the output FITS file after "
        f"{attempts} attempts.\n"
        f"Target file: {path}\n"
        f"Temporary FITS retained at:\n{tmp}\n"
        f"Close DS9/FITS viewers and other programs using the target file, "
        f"then rename the temporary file manually if necessary."
    ) from last_err

def _fiber_zone_mask(img, thr_nsig=2.0, grow_rows=2):
    """
    画像の y プロファイル（各行のメディアン）からファイバー帯域（明るい行）を自動抽出。
    thr_nsig: 行プロファイルのロバスト閾値 [median + thr_nsig*MAD]
    grow_rows: 帯域を y 方向に膨張するピクセル数（FWHM~3pxなので 2 程度）
    """
    ny, nx = img.shape
    prof_y = np.median(img, axis=1)  # 各行の代表値
    med = np.median(prof_y)
    mad = np.median(np.abs(prof_y - med)) * 1.4826 + 1e-6
    fib_rows = prof_y > (med + thr_nsig * mad)  # 明るい行＝ファイバー帯域候補

    # y方向だけ膨張（±grow_rows 行）
    if grow_rows > 0:
        fib_rows = fib_rows.astype(bool)
        for _ in range(grow_rows):
            fib_rows[:-1] |= fib_rows[1:]
            fib_rows[1:]  |= fib_rows[:-1]

    # 2D マスクへ（全 x 列に複製）
    return np.repeat(fib_rows[:, None], nx, axis=1)

def cr_despike_single_fiber(img,
                            box_x=9,                 # x方向メディアン窓（奇数、7～11推奨）
                            nsig_resid=6.0,          # 残差閾値（x方向基準）
                            lap_sigma=0.8,           # LoG用の事前Gaussian σ（0.6～1.0）
                            lap_nsig=5.0,            # Laplacianのロバスト閾値
                            fiber_thr_nsig=2.0,      # ファイバー帯域検出の閾値（行プロファイル）
                            fiber_grow=2,            # ファイバー帯域のy膨張
                            grow=1,                  # マスク膨張（近接も置換）
                            max_iter=1):             # 反復回数（通常1で十分）
    """
    x方向1Dメディアンを基準に残差を取り、加えて Laplacian で“鋭さ”を判定。
    ファイバー帯域内は (残差 & 鋭さ) の AND 条件、帯域外は (残差 OR 鋭さ) の OR 条件で検出。
    置換値は x方向1Dメディアン（分散方向の近傍）を採用。
    """
    work = img.astype(np.float32).copy()
    ny, nx = work.shape
    total_mask = np.zeros_like(work, dtype=bool)

    for _ in range(max_iter):
        # x方向のみの局所メディアン（yは触らない）
        medx = median_filter(work, size=(1, box_x), mode='mirror')
        resid = work - medx
        sig_r = 1.4826 * np.median(np.abs(resid - np.median(resid))) + 1e-6

        # 鋭さ（高周波成分）の検出：軽く平滑→ラプラシアン
        smooth = gaussian_filter(work, sigma=(lap_sigma, lap_sigma))
        L = laplace(smooth)
        Lpos = np.maximum(L, 0.0)  # 正の鋭いピークに敏感
        sig_L = 1.4826 * np.median(np.abs(L - np.median(L))) + 1e-6

        # ファイバー帯域マスクを作成
        fib_zone = _fiber_zone_mask(work, thr_nsig=fiber_thr_nsig, grow_rows=fiber_grow)

        # 帯域内：厳しく（AND）／ 帯域外：やや緩く（OR）
        mask_in  = fib_zone  & (resid > nsig_resid * sig_r) & (Lpos > lap_nsig * sig_L)
        mask_out = (~fib_zone) & ( (resid > nsig_resid * sig_r) | (Lpos > lap_nsig * sig_L) )

        mask = mask_in | mask_out

        if grow > 0:
            st = generate_binary_structure(2, 1)    # 3x3相当
            for _ in range(grow):
                mask = binary_dilation(mask, structure=st)

        work = np.where(mask, medx, work)
        total_mask |= mask

    return work, total_mask

def cr_despike_single(img, box=5, nsig=7.0, grow=1, max_iter=2):
    """
    単一画像の宇宙線スパイクをローカル・メディアン＋MADで検出・置換
    box: メディアンフィルタ窓
    nsig: 検出しきい値 (sigma単位; 大きいほど保守的)
    grow: 検出マスクの膨張ピクセル数（周辺も巻き込んで置換）
    max_iter: 反復回数（残りスパイクを徐々に除去）
    """
    work = img.astype(np.float32).copy()
    total_mask = np.zeros_like(work, dtype=bool)

    for _ in range(max_iter):
        med = median_filter(work, size=box, mode='mirror')
        resid = work - med
        # グローバルにロバストσ推定
        sigma = 1.4826 * np.median(np.abs(resid - np.median(resid)))
        sigma = max(sigma, 1e-6)

        mask = resid > nsig * sigma  # 宇宙線は基本「正のスパイク」を想定
        if grow > 0:
            st = generate_binary_structure(2, 1)
            for _ in range(grow):
                mask = binary_dilation(mask, structure=st)

        work = np.where(mask, med, work)
        total_mask |= mask

    return work, total_mask

def combine_two_images_robust(a, b, diff_nsig=8.0):
    """
    2画像のロバスト合成。差画像のロバストσで外れ差分を検出し、
    その画素は小さい方の値（正のスパイク想定）を採用し、それ以外は平均。
    """
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    d = a - b
    # 差画像のロバストσ
    sigma_d = 1.4826 * np.median(np.abs(d - np.median(d)))
    sigma_d = max(sigma_d, 1e-6)

    out = 0.5 * (a + b)
    mask = np.abs(d) > diff_nsig * sigma_d
    # d>0 なら a が大きい（スパイク）→ b 採用、d<0 なら b が大きい → a 採用
    out[mask] = np.where(d[mask] > 0, b[mask], a[mask])
    return out, mask

def file_search(file_pattern):
    # パスとファイル名の分離
    directory = os.path.dirname(file_pattern)  # ディレクトリ部分
    pattern = os.path.basename(file_pattern)   # ファイルパターン部分
    
    # 正規表現に変換（{} の部分を () に変換し、| で区切る）
    pattern = re.sub(r'{(.*?)}', lambda m: '(' + '|'.join(m.group(1).split(',')) + ')', pattern)
    
    # ワイルドカード * と ? を正規表現に変換
    regex_pattern = re.sub(r'\*', r'.*', re.sub(r'\?', r'.', pattern))
    regex = re.compile(regex_pattern)

    # ディレクトリ内のファイルをリストアップ
    matching_files = []
    for file in os.listdir(directory):
        if regex.match(file):
            # フルパスを生成
            full_path = os.path.join(directory, file)
            matching_files.append(full_path)

    return matching_files

def fits_fspframe7(files, savefile=None, type='clippedmean', n_sigma=2.0, 
                  silent=False, show=False, save_path=None,
                  # 追加: 宇宙線処理パラメータ
                  cr_box=5, cr_nsig=7.0, cr_grow=1, cr_max_iter=2, cr_diff_nsig=8.0,
                  # 追加: ダーク・正規化
                  darkfile=None, normalize=True):

    if not silent:
        print(files)

    if savefile is None:
        savefile = files[0].replace('1.fits', 'sp.fits')

    if save_path:
        savefile = os.path.join(save_path, os.path.basename(savefile))

    # --- ダークフレーム読込（存在すれば） ---
    dark_final = None
    if darkfile is not None:
        try:
            if os.path.exists(darkfile):
                with fits.open(darkfile, memmap=False) as dh:
                    ddata = dh[0].data
                    if ddata is not None and ddata.ndim == 3:
                        ddata = np.squeeze(ddata)                        
                    dflip = dh[0].header.get('FLIPX', 1)
                    # ダークも最終表示向きに合わせる（FLIPX==0なら左右反転）
                    if dflip == 0:
                        ddata = np.flip(ddata, axis=1)
                    dark_final = ddata.astype(np.float32)
            else:
                if not silent:
                    print(f"[WARN] darkfile not found: {darkfile}")
        except Exception as e:
            if not silent:
                print(f"[WARN] failed to read darkfile: {darkfile}\n{e}")
            dark_final = None

    # Read header only for dimensions
    try:
        with fits.open(files[0]) as hdul:
            header0 = hdul[0].header
            nx = header0['NAXIS1']
            ny = header0['NAXIS2']
    except Exception as e:
        print(cfg.RED+f"No file: {files[0]}"+cfg.RESET)
        print(e)
        return

    jdmid = np.zeros(len(files))
    jdsta = np.zeros(len(files))
    jdsto = np.zeros(len(files))
    expt = np.zeros(len(files))
    ctemp = np.zeros(len(files))

    dcb = []
    frame_meds = []  # 各フレームの（ダーク減算後）全体メジアン

    for k in range(len(files)):
        try:
            with fits.open(files[k], memmap=False) as hdul:
                data = hdul[0].data
                header = hdul[0].header
                if data.ndim == 3:
                    data = np.squeeze(data)  # 3D → 2D

                # 安全に FLIPX 取得（無ければ 1=flipしない）
                #flipx = header.get('FLIPX', 1)
                #if flipx == 0:
                #    data = np.flip(data, axis=1)
                data = data.astype(np.float32)

                # ダークを最終向きに整形済み（dark_final）として減算
                if dark_final is not None:
                    if dark_final.shape == data.shape:
                        data = data - dark_final
                    else:
                        if not silent:
                            print(f"[WARN] dark shape {dark_final.shape} != data shape {data.shape} (skip subtract)")

                # 後のスケール合わせ用にメジアンを記録
                frame_meds.append(np.median(data))

                dcb.append(data)
                if 'EXPOSURE' in header:
                    expt[k] = header['EXPOSURE']
                elif 'EXPTIME' in header:
                    expt[k] = header['EXPTIME']
                else:
                    expt[k] = 0.0

                t_mid = Time(header.get('DATE', header.get('DATE-OBS')), format='isot', scale='utc').jd
                jdsta[k] = t_mid - expt[k] / 86400.0
                jdmid[k] = t_mid - expt[k] / 86400.0 / 2.0
                jdsto[k] = t_mid
                ctemp[k] = float(header.get('TEMP', np.nan))

            if k == 0:
                header0 = header
        except Exception as e:
            print(e)

    dcb = np.array(dcb)  # shape = (N, ny, nx)
    N = len(dcb)

    # --- 明るさ正規化（フレーム間の一様スケール） ---
    if normalize and N > 0:
        meds = np.array(frame_meds, dtype=np.float64)
        # 目標値 = 「フレーム全体メジアンたち」のメジアン
        if np.all(~np.isfinite(meds)) or np.sum(np.isfinite(meds)) == 0:
            target_med = None
        else:
            target_med = np.median(meds[np.isfinite(meds)])

        # 追加: フレーム強度ばらつき指標 FMSTD = std( frame_meds / target_med )
        fmstd = np.nan
        if (target_med is not None) and np.isfinite(target_med) and target_med != 0:
            mask = np.isfinite(meds)
            if np.any(mask):
                fmstd = float(np.std(meds[mask] / float(target_med)))  # 母標準偏差（ddof=0）

        try:
            header0['FMSTD'] = (fmstd, 'Std of (frame_median/target_med)')
        except Exception:
            pass

        scales = []
        if (target_med is not None) and np.isfinite(target_med):
            eps = 1e-12
            for i in range(N):
                m = meds[i]
                if np.isfinite(m) and (abs(m) > eps):
                    P = float(target_med / m)
                else:
                    P = 1.0
                dcb[i] *= P
                scales.append(P)

            # HISTORYに記録（上書きせず追記）
            try:
                dark_name = os.path.basename(darkfile) if darkfile else 'None'
                header0.add_history(f"NORM: dark={dark_name}, target_med={target_med:.6g}, "
                                    f"scale[min,max]=[{min(scales):.6g},{max(scales):.6g}]")
            except Exception:
                pass

    # === 規格化後の単純平均（CR除去なし）を保存 ===
    #  N=1ならその1枚、N>=2なら普通の mean。clipped mean の確認用。
    norm_mean = np.mean(dcb, axis=0).astype(np.float32)

    base, ext = os.path.splitext(savefile)
    savefile_m = base + '.m.fits'  # 例: xxx/sp.fits -> xxx/sp.m.fits

    headerM = header0.copy()
    try: headerM['FMSTD'] = header0['FMSTD']
    except Exception: pass
    # 代表レンジ（任意）
    vm = [np.percentile(norm_mean, 0.3), np.percentile(norm_mean, 99.7)]
    headerM['DATAMIN'] = (float(vm[0]), '0.3%')
    headerM['DATAMAX'] = (float(vm[1]), '99.7%')
    # 代表メタ（super frame と合わせておく）
    headerM['EXPOSURE']  = float(np.nanmean(expt)) if N > 0 else 0.0
    headerM['JD']        = float(np.nanmin(jdsta)) if N > 0 else np.nan
    headerM['TELESCOP']  = ('T60','Haleakala Tohoku 60-cm telescope')
    headerM['DATE-OBS']  = Time(np.nanmean(jdmid), format='jd').isot if N > 0 else ''
    headerM['EXPSTART']  = Time(np.nanmin(jdsta), format='jd').isot if N > 0 else ''
    headerM['EXPSTOP']   = Time(np.nanmax(jdsto), format='jd').isot if N > 0 else ''
    headerM['EXPMID']    = Time((np.nanmin(jdsta)+np.nanmax(jdsto))/2, format='jd').isot if N > 0 else ''
    if np.isfinite(np.nanmean(ctemp)):
        headerM['CCD-TEMP'] = f"{np.nanmean(ctemp):.2f}"
    headerM['NFILES']    = N
    try:
        headerM.add_history('NORM-MEAN: simple average after dark-subtraction and per-frame scalar normalization (no CR rejection)')
    except Exception:
        pass

    #fits.PrimaryHDU(norm_mean, header=headerM).writeto(savefile_m, overwrite=True)
    _fits_writeto_retry(savefile_m, np.flip(norm_mean,axis=1), headerM)

    if not silent:
        print(f"[INFO] normalized simple mean saved: {savefile_m}")

    # --- 合成（super frame） ---
    if N >= 3:
        if type == 'median':
            sdk = np.median(dcb, axis=0)
            try: header0.add_history('STACK: median (N>=3)')
            except Exception: pass
        elif type == 'mean':
            sdk = np.mean(dcb, axis=0)
            try: header0.add_history('STACK: mean (N>=3)')
            except Exception: pass
        elif type == 'clippedmean':
            print("taking clipped mean ...", end='')
            clipped = sigma_clip(dcb, sigma=n_sigma, axis=0, maxiters=3)
            # マスク平均→欠損は中央値で埋めて安定化
            mmean = np.ma.mean(clipped, axis=0)
            sdk = mmean.filled(np.nan)
            med = np.nanmedian(dcb, axis=0)
            sdk = np.where(np.isnan(sdk), med, sdk)
            print(" done")
            try: header0.add_history(f'STACK: sigma_clip mean (N>=3), sigma={n_sigma}')
            except Exception: pass
        else:
            sdk = np.mean(dcb, axis=0)
            try: header0.add_history('STACK: mean (fallback, N>=3)')
            except Exception: pass

    elif N == 2:
        # 各フレームを軽くデスパイクしてからロバスト合成
        nsig_resid0 = 4.0
        fiber_thr_nsig0 = 2.5
        lap_nsig0 = 4.0
        a1, m1 = cr_despike_single_fiber(dcb[0], box_x=9, nsig_resid=nsig_resid0,
                                         lap_sigma=0.8, lap_nsig=lap_nsig0,
                                         fiber_thr_nsig=fiber_thr_nsig0, fiber_grow=2,
                                         grow=1, max_iter=1)
        b1, m2 = cr_despike_single_fiber(dcb[1], box_x=9, nsig_resid=nsig_resid0,
                                         lap_sigma=0.8, lap_nsig=lap_nsig0,
                                         fiber_thr_nsig=fiber_thr_nsig0, fiber_grow=2,
                                         grow=1, max_iter=1)
        sdk, m12 = combine_two_images_robust(a1, b1, diff_nsig=8.0)
        try:
            header0.add_history(
                f'CRREJ(2img,fiber-aware): box_x=9 nsig_resid={nsig_resid0:.1f} lap=0.8/{lap_nsig0:.1f} '
                f'fiberThr={fiber_thr_nsig0:.1f} grow={1}; '
                f'Ncr1={int(m1.sum())}, Ncr2={int(m2.sum())}, Nrob={int(m12.sum())}'
            )
        except Exception:
            pass

    elif N == 1:
        # 単一フレームのデスパイク
        nsig_resid0 = 4.0
        fiber_thr_nsig0 = 2.5
        lap_nsig0 = 4.0
        sdk, m1 = cr_despike_single_fiber(dcb[0], box_x=9, nsig_resid=nsig_resid0,
                                          lap_sigma=0.8, lap_nsig=lap_nsig0,
                                          fiber_thr_nsig=fiber_thr_nsig0, fiber_grow=2,
                                          grow=1, max_iter=1)
        try:
            header0.add_history(
                f'CRREJ(1img,fiber-aware): box_x=9 nsig_resid={nsig_resid0:.1f} lap=0.8/{lap_nsig0:.1f} '
                f'fiberThr={fiber_thr_nsig0:.1f} grow={1}; Ncr={int(m1.sum())}'
            )
        except Exception:
            pass
    else:
        print("No input files.")
        return

    # 出力レンジとメタ
    vrng = [np.percentile(sdk, 0.3), np.percentile(sdk, 99.7)]

    header0['EXPOSURE']  = float(np.nanmean(expt)) if N > 0 else 0.0
    header0['JD']        = float(np.nanmin(jdsta)) if N > 0 else np.nan
    header0['TELESCOP']  = ('T60','Haleakala Tohoku 60-cm telescope')
    header0['DATE-OBS']  = Time(np.nanmean(jdmid), format='jd').isot if N > 0 else ''
    header0['EXPSTART']  = Time(np.nanmin(jdsta), format='jd').isot if N > 0 else ''
    header0['EXPSTOP']   = Time(np.nanmax(jdsto), format='jd').isot if N > 0 else ''
    header0['EXPMID']    = Time((np.nanmin(jdsta)+np.nanmax(jdsto))/2, format='jd').isot if N > 0 else ''
    if np.isfinite(np.nanmean(ctemp)):
        header0['CCD-TEMP'] = f"{np.nanmean(ctemp):.2f}"
    header0['NFILES']    = N
    header0['DATAMIN']   = (float(vrng[0]), '0.3%')
    header0['DATAMAX']   = (float(vrng[1]), '99.7%')

    # Save to fits file (super frame)
    sdk = np.array(sdk, dtype=np.float32)
    #fits.PrimaryHDU(sdk, header=header0).writeto(savefile, overwrite=True)
    _fits_writeto_retry(savefile, np.flip(sdk,axis=1), header0)
    
    if not silent:
        print(f"[INFO] super frame saved: {savefile}")

    # ====== ここから追加：呼び出し側に情報を返す ======
    # 正規化をしなかった場合に備えて安全に初期化しておく
    try:
        meds_ret = meds
    except NameError:
        meds_ret = None
    try:
        target_med_ret = target_med
    except NameError:
        target_med_ret = None
    try:
        fmstd_ret = fmstd
    except NameError:
        fmstd_ret = np.nan
    try:
        scales_ret = scales
    except NameError:
        scales_ret = None

    info = {
        # ダーク減算後・正規化前の各フレームのメジアン
        'frame_meds': np.array(frame_meds, dtype=np.float64) if len(frame_meds) > 0 else None,
        # 正規化処理で使った値（あれば）
        'meds': np.array(meds_ret, dtype=np.float64) if meds_ret is not None else None,
        'target_med': target_med_ret,
        'fmstd': fmstd_ret,
        'scales': np.array(scales_ret, dtype=np.float64) if isinstance(scales_ret, list) else None,
        # その他メタ
        'nframes': N,
        'files': files,
    }
    return info    
    
def _as2d_axes(axes, ny, nx):
    """plt.subplots が返す axes を必ず (ny, nx) の2次元配列に整形"""
    return np.array(axes, dtype=object).reshape(ny, nx)

def mkSpFrames4f(dsno,overwrite=True,flgPause=True,nxFig=2,nyFig=5):
    df= pd.read_csv(cfg.fileCsv)
    file_idx = df[df.DSNO.isin(dsno)]
    #print(file_idx)
    
    for index, row in file_idx.iterrows():
        info_stack = None  # この DSNO の stack 情報を入れておく
        fig, axes = plt.subplots(nyFig, nxFig, figsize=(9,10),dpi=96); iFig=0; iFig2=1; axes = _as2d_axes(axes, nyFig, nxFig)
        plt.subplots_adjust(wspace=0.3, hspace=0.3,left=0.05, right=0.95, top=0.95, bottom=0.05)
        
        savefile = cfg.fits_path + row.FILENAME
        #files = glob.glob(cfg.original_path+row.ORIGIN);  files = sorted(files, key=os.path.getmtime)     
        files = file_search(cfg.original_path+row.ORIGIN); files = sorted(files, key=os.path.getmtime)   
        #print(files); input("aab")
        os.makedirs(os.path.dirname(savefile), exist_ok=True)
        print(f"{row.DSNO:.0f}",f'{len(files)} {savefile}')
        
        if not files:  
            print(cfg.RED+f"No file: {row.DSNO:.0f} {cfg.original_path+row.ORIGIN}"+cfg.RESET)
            df.at[index, 'DATATYPE'] = 'NONE'
            continue
        elif os.path.exists(savefile) and not overwrite:
            print(cfg.RED+f"Skipped: {row.DSNO:.0f} {savefile}"+cfg.RESET)
            continue        
        else :
            sum_img_for_mean = None
            n_for_mean = 0
            for k2 in range(len(files)):
                with fits.open(files[k2]) as hdul:
                    data = hdul[0].data                             
                    if data.ndim==3: data=np.squeeze(data)# データが 3D の場合、2D に変換
          
                  # 個別ファイルを開く for k2 in range(len(files)) の中、hdulを開いた直後あたりに追加
                    header_k = hdul[0].header
                    data_for_mean = data
                    if header_k.get('FLIPX', 1) == 0:
                        data_for_mean = np.flip(data_for_mean, axis=1)  # スーパーフレームと同じ向きに合わせる

                    if sum_img_for_mean is None:
                        sum_img_for_mean = data_for_mean.astype(np.float64)
                    else:
                        sum_img_for_mean += data_for_mean
                    n_for_mean += 1

                    vrng=[np.percentile(data, 2), np.percentile(data, 98)]

                    if iFig >= len(axes.flat): 
                        # Saving PNG
                        strDate=((row.FILENAME).replace("fits/",""))[0:8]
                        filePng=f"{cfg.png_path}"+(os.path.basename(__file__)).replace('.py','/') \
                                +f"{row.DSNO:.0f}"[:6]+f"/{row.DSNO:.0f}_"+(os.path.basename(savefile)).replace(".fits","_")+str(iFig2)+".png"
                        if not os.path.exists(os.path.dirname(filePng)):os.makedirs(os.path.dirname(filePng))
                        #plt.draw(); plt.pause(0.001)
                        plt.savefig(filePng,bbox_inches=None, pad_inches=0.05)
                        plt.close()
                        print(filePng)
                        iFig2 += 1;                          
                        fig, axes = plt.subplots(nyFig, nxFig, figsize=(9,10),dpi=96); iFig=0; axes = _as2d_axes(axes, nyFig, nxFig)
                        plt.subplots_adjust(wspace=0.3, hspace=0.3,left=0.05, right=0.95, top=0.95, bottom=0.05)
                    
                    # Determine the correct subplot (4x4 grid)
                    ax = axes[iFig // nxFig, iFig % nxFig]; iFig += 1
                    im = ax.imshow(data, cmap='jet', vmin=vrng[0], vmax=vrng[1],origin='lower',interpolation='none')
                    ax.set_title(os.path.basename(os.path.dirname(savefile))+"/"+os.path.basename(files[k2]),fontsize=8)
                    ax.tick_params(axis='both', labelsize=6) 
                    cbar = fig.colorbar(im, ax=ax)

            if not os.path.exists(savefile) or overwrite: 
                # 追加：DARKFRAME 列があれば、cfg.current_dir + row.DARKFRAME を渡す
                darkfile = None
                if ('DARKFRAME' in df.columns) and isinstance(row.DARKFRAME, str) and len(row.DARKFRAME) > 0:
                    darkfile = os.path.join(cfg.current_dir, row.DARKFRAME)

                info_stack = fits_fspframe7(files,savefile=savefile,n_sigma=2.0,
                    silent=True,type='clippedmean',darkfile=darkfile,normalize=True)

        # スーパーフレームを開く箇所の変数名 sdk
        with fits.open(savefile, memmap=False) as hdul:
            sdk = np.array(hdul[0].data, copy=True)

            if sdk.ndim == 3:
                sdk = np.squeeze(sdk).copy()

            header = hdul[0].header.copy()
            
        try:
            df.at[index,'CCDTEMP']=round(float(header['TEMP']),2)
            df.at[index,'EXPTIME']=header['EXPOSURE']
            df.at[index,'EXPSTART']=header['EXPSTART']
            df.at[index,'EXPSTOP']=header['EXPSTOP']
            df.at[index,'NFILES']=header['NFILES']
            df.at[index,'EXPMID']=header['EXPMID']
            df.at[index,'FMSTD'] = header.get('FMSTD', np.nan)
        except Exception as e: 
            print(e)

        # ページが満杯なら保存→新規ページ
        if iFig >= len(axes.flat): 
            strDate=((row.FILENAME).replace("fits/",""))[0:8]
            filePng=f"{cfg.png_path}"+(os.path.basename(__file__)).replace('.py','/') \
                    +f"{row.DSNO:.0f}"[:6]+f"/{row.DSNO:.0f}_"+(os.path.basename(savefile)).replace(".fits","_")+str(iFig2)+".png"
            if not os.path.exists(os.path.dirname(filePng)): os.makedirs(os.path.dirname(filePng))
            #plt.draw(); plt.pause(0.001)
            plt.savefig(filePng, bbox_inches=None, pad_inches=0.05)
            print(filePng)      
            plt.close()
            iFig2 += 1        
            fig, axes = plt.subplots(nyFig, nxFig, figsize=(9,10), dpi=96); iFig=0; axes = _as2d_axes(axes, nyFig, nxFig)
            plt.subplots_adjust(wspace=0.3, hspace=0.3, left=0.05, right=0.95, top=0.95, bottom=0.05)
        
        # スーパーフレーム表示
        rng=[np.percentile(sdk, 2), np.percentile(sdk, 98)]
        ax = axes[iFig // nxFig, iFig % nxFig]; iFig += 1
        im = ax.imshow(sdk, cmap='jet', vmin=rng[0], vmax=rng[1], origin='lower', interpolation='none')
        ax.set_title(os.path.basename(os.path.dirname(savefile))+"/"+os.path.basename(savefile), fontsize=8)
        ax.tick_params(axis='both', labelsize=6) 
        cbar = fig.colorbar(im, ax=ax)

        # === 新規：規格化平均(.m.fits)を読み込み、差分 (NormalizedMean - SuperFrame) を表示 ===
        base, ext = os.path.splitext(savefile)
        savefile_m = base + '.m.fits'
        mean_norm = None
        try:
            if os.path.exists(savefile_m):
                with fits.open(savefile_m, memmap=False) as hdum:
                    if hdum[0].data is None:
                        mean_norm = None
                    else:
                        mean_norm = np.array(
                            hdum[0].data,
                            dtype=np.float32,
                            copy=True
                        )

                        if mean_norm.ndim == 3:
                            mean_norm = np.squeeze(mean_norm).copy()            
                        else:
                            print(f"[WARN] normalized-mean file not found: {savefile_m}")
        except Exception as e:
            print(f"[WARN] failed to open normalized-mean file: {savefile_m} : {e}")
            mean_norm = None

        if mean_norm is not None:
            # 差分 = 規格化平均 - スーパーフレーム（ご指定の順序）
            diff = (mean_norm.astype(np.float32) - sdk.astype(np.float32))

            # 表示スケール：ロバストσ ±5σ（失敗時は |diff| の99.5%）
            diff_med = np.median(diff)
            diff_sig = 1.4826 * np.median(np.abs(diff - diff_med))
            if np.isfinite(diff_sig) and diff_sig > 0:
                vlim = 5.0 * diff_sig
                vmin, vmax = -vlim, +vlim
                ttl_extra = "±5σ"
            else:
                vmax = np.percentile(np.abs(diff), 99.5)
                vmin = -vmax
                ttl_extra = "±99.5%"

            # パネルが埋まっていたらページセーブ→新規ページ
            if iFig >= len(axes.flat):
                strDate=((row.FILENAME).replace("fits/",""))[0:8]
                filePng=f"{cfg.png_path}"+(os.path.basename(__file__)).replace('.py','/') \
                        +f"{row.DSNO:.0f}"[:6]+f"/{row.DSNO:.0f}_"+(os.path.basename(savefile)).replace(".fits","_")+str(iFig2)+".png"
                if not os.path.exists(os.path.dirname(filePng)): os.makedirs(os.path.dirname(filePng))
                #plt.draw(); plt.pause(0.001)
                plt.savefig(filePng, bbox_inches=None, pad_inches=0.05)
                print(filePng)
                plt.close()
                iFig2 += 1
                fig, axes = plt.subplots(nyFig, nxFig, figsize=(9,10), dpi=96); iFig=0; axes = _as2d_axes(axes, nyFig, nxFig)
                plt.subplots_adjust(wspace=0.3, hspace=0.3, left=0.05, right=0.95, top=0.95, bottom=0.05)

            # 差分を追加描画（発散カラーマップ）
            ax = axes[iFig // nxFig, iFig % nxFig]; iFig += 1
            im = ax.imshow(diff, cmap='bwr', vmin=vmin, vmax=vmax, origin='lower', interpolation='none')
            ax.set_title(f"NMean - SFrame ({ttl_extra}), FMSTD = {header.get('FMSTD', np.nan):.3f}", fontsize=8)
            ax.tick_params(axis='both', labelsize=6)
            cbar = fig.colorbar(im, ax=ax)

            if row.DATATYPE == 'BAD':
                h, w = diff.shape[:2]#（画像ピクセルの対角線）                
                ax.plot([0, w-1], [0, h-1],color='red', linewidth=3, solid_capstyle='butt', zorder=10)
                
        # === 新規：各フレームのメジアン値（frame_meds）の推移をプロット ===
        if isinstance(info_stack, dict):
            meds = info_stack.get('frame_meds', None)
            if meds is not None:
                meds = np.asarray(meds, dtype=float)
                nframes = meds.size
                x = np.arange(nframes) + 1  # 1,2,3,...

                # パネルが埋まっていたらページセーブ→新規ページ
                if iFig >= len(axes.flat):
                    strDate=((row.FILENAME).replace("fits/",""))[0:8]
                    filePng=f"{cfg.png_path}"+(os.path.basename(__file__)).replace('.py','/') \
                            +f"{row.DSNO:.0f}"[:6]+f"/{row.DSNO:.0f}_"+(os.path.basename(savefile)).replace(".fits","_")+str(iFig2)+".png"
                    if not os.path.exists(os.path.dirname(filePng)):
                        os.makedirs(os.path.dirname(filePng))
                    plt.savefig(filePng, bbox_inches=None, pad_inches=0.05)
                    print(filePng)
                    plt.close()
                    iFig2 += 1
                    fig, axes = plt.subplots(nyFig, nxFig, figsize=(9,10), dpi=96); iFig=0; axes = _as2d_axes(axes, nyFig, nxFig)
                    plt.subplots_adjust(wspace=0.3, hspace=0.3, left=0.05, right=0.95, top=0.95, bottom=0.05)

                ax = axes[iFig // nxFig, iFig % nxFig]; iFig += 1
                ax.plot(x, meds, marker='o')
                ax.set_xlabel('Frame #', fontsize=6)
                ax.set_ylabel('Median (after dark)', fontsize=6)
                ax.set_title('Frame median (pre-normalization)', fontsize=8)
                ax.grid(True, alpha=0.3)
                ax.tick_params(axis='both', labelsize=6)

        # 空白の領域を非表示にする
        for j in range(iFig, len(axes.flat)):
            axes[j // nxFig, j % nxFig].axis('off')
        
        # Saving PNG（ページの最後）
        strDate=((row.FILENAME).replace("fits/",""))[0:8]
        filePng=f"{cfg.png_path}"+(os.path.basename(__file__)).replace('.py','/') \
            +f"{row.DSNO:.0f}"[:6]+f"/{row.DSNO:.0f}_"+(os.path.basename(savefile)).replace(".fits","_")+str(iFig2)+".png"
        print(filePng)

        if not os.path.exists(os.path.dirname(filePng)): os.makedirs(os.path.dirname(filePng))
        plt.savefig(filePng, bbox_inches=None, pad_inches=0.05)
        #plt.draw(); plt.pause(0.001)
        plt.close()
        
    # バックアップとCSV保存    
    #########################################################33            
    ctime = datetime.now().strftime('%Y%m%d%H%M%S')
    file1=os.path.dirname(__file__)+ "\\bk\\" +ctime+os.path.basename(cfg.fileCsv)
    shutil.copy2(cfg.fileCsv,file1)
    print("backup: ",file1)    
    try:
        df.to_csv(cfg.fileCsv,index=False)
        print("Saved:", cfg.fileCsv)    
    except Exception as e:
        #print("Error on writing ",cfg.fileCsv)
        print("Close the file:",cfg.fileCsv)
        input("Press Enter to proceed")
        try:
            df.to_csv(cfg.fileCsv,index=False)
            print("Saved:", cfg.fileCsv)    
        except Exception as e: print(e)    

#################################################################################
### START POINT ###
if __name__ == "__main__":
    df= pd.read_csv(cfg.fileCsv)
    file_idx = df[ ((df.DATATYPE != 'BADDATA') & (df.DATATYPE != 'DARK'))                  
                  #&  (df.DSNO >  251101000) & (df.DSNO < 251130000)
                  #& (df.DSNO >= 250502100) & (df.DSNO < 250502900)
                  #& (df.DSNO >= 250504000) & (df.DSNO < 250504900)
                  #& (df.DSNO >= 250630000) & (df.DSNO < 250720000)
                  #& (df.DSNO >= 250707000) & (df.DSNO < 250710000)
                  #& (df.DSNO % 1000 > 10)  & (df.DSNO % 1000 <40)
                  #& (df.DSNO >= 250813000) & (df.DSNO < 250818000)
                  #& (df.DSNO >= 250818000) & (df.DSNO < 250819000)
                  # & (df.DSNO >= 250819000) & (df.DSNO < 250820000) #K
                  #& (df.DSNO >= 250820000) & (df.DSNO < 250821000)
                  #& (df.DSNO > 250812000) & (df.DSNO < 250830000)
                  #& (df.DSNO >= 250900000) & (df.DSNO <= 250900900)
                  #& (df.DSNO >  250819000) & (df.DSNO < 250820000)
                  #& (df.DSNO >  251010900) & (df.DSNO < 251010990)
                  #& (df.DSNO >=  251010010) & (df.DSNO < 251010990)
                  #& (df.DSNO >=  251012010) & (df.DSNO < 251012990)
                  #& (df.DSNO >=  251209100) & (df.DSNO < 251209990)
                  #& (df.DSNO >=  260217200) & (df.DSNO < 260217990)
                  #& (df.DSNO >=  260402110) & (df.DSNO < 260402990)
                  #& (df.DSNO >=  260406111) & (df.DSNO < 260406990)
                  #& (df.DSNO >=  260422110) & (df.DSNO < 260422990)
                  #& (df.DSNO >=  260423110) & (df.DSNO < 260423990)
                  #& (df.DSNO >=  260424110) & (df.DSNO < 260424990)
                  #& (df.DSNO >=  260427110) & (df.DSNO < 260427990)
                  #& (df.DSNO >=  251214910) & (df.DSNO < 251214990)
                  #& (df.DSNO >  251101000) #& (df.DSNO < 251113000)
                  #& (df.DSNO >  251112000) & (df.DSNO < 251112990)
                  #& (df.DSNO >=  251209000) & (df.DSNO < 251209200)
                  #& (df.DSNO >=  251210000) & (df.DSNO < 251210900)
                  #& (df.DSNO >=  251211000) & (df.DSNO < 251211900)
                  #& (df.DSNO >=  251210000) & (df.DSNO < 251221900)
                  #& (df.DSNO >=  260217250) & (df.DSNO < 260217900)
                  #& (df.DSNO >=  260320209) & (df.DSNO < 260320900)
                  #& (df.DSNO >=  260320209) & (df.DSNO < 260320900)
                  #& (df.DSNO >=  260811000) & (df.DSNO < 260811900)
                  #& (df.DSNO >=  260915161) & (df.DSNO < 260915900)
                  #& (df.DSNO >=  260916000) & (df.DSNO < 260916900)
                  & (df.DSNO >=  260917163) & (df.DSNO < 260917900)
                  #& ( (df.DSNO % 1000 < 200) | (df.DSNO % 1000 > 200) & (df.DSNO % 25 == 0) )
                  #& ((df.DSNO % 1000 > 200) & (df.DSNO % 25 == 0) )
                  #& ((df.DSNO % 1000 < 200) )
                  ]    
    dsno = file_idx.DSNO.astype('int64').tolist()
    #dsno = [251112129,251112200,251112201]
    #dsno = [250504136]

    print(*map(int,dsno))
    mkSpFrames4f(dsno,overwrite=True,flgPause=False,nxFig=3,nyFig=7)
    