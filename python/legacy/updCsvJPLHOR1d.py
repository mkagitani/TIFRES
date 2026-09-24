# -*- coding: utf-8 -*-
"""
CSV を読み、各行の FITS に記載の EXPMID（撮像中点時刻）から、
JPL Horizons (astroquery) を用いて天文暦量を取得し、CSV を更新。

改訂点:
- 欠損/Masked/Quantity/文字列の安全処理を追加
- RA/DEC は文字列("hh mm ss", "dd mm ss")にも対応して AltAz 変換
- ephemerides の epochs は UTC JD を使用
- ephemerides は必要な quantities (1,13,14,15,17,19,20,23,24) を明示
- 位相角 STOANG から輝面比 ILMFRAC=(1+cos(STOANG))/2 を計算してCSVへ記録
- NDSKAIFU の計算・更新は行わない
"""

import os
import math
import shutil
from datetime import datetime

import numpy as np
import pandas as pd
from astropy.io import fits
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
import astropy.units as u
from astroquery.jplhorizons import Horizons

import cfg  # cfg.fileCsv, cfg.fits_path

# ===================== 観測地点（Haleakalā / AMOS 既定） =====================
# 元コードは lon=203.742E （西経 156.258°相当）を使用
LON_EAST_DEG = 203.742
LON_FOR_ASTROPY = LON_EAST_DEG if LON_EAST_DEG <= 180 else LON_EAST_DEG - 360.0  # -> -156.258
LAT_DEG = 20.708
ALT_M = 3.0430 # km at Haleakala

SITE = EarthLocation.from_geodetic(
    lon=LON_FOR_ASTROPY * u.deg, lat=LAT_DEG * u.deg, height=ALT_M * u.m
)

AU_KM = 149_597_870.7  # km

# ===================== ターゲットID対応（Horizons ID） =====================
def to_horizons_id(datatype: str) -> str:
    mapping = {
        'MERCURY': '199',
        'VENUS': '299',
        'IO': '501',
        'EUROPA': '502',
        'GANYMEDE': '503',
        'CALLISTO': '504',
        'JI': '501',
        'JII': '502',
        'JIII': '503',
        'JIV': '504',
    }
    t = (datatype or '').upper().strip()
    return mapping.get(t, t or '199')  # 既定は Mercury

# ===================== 角半径計算に使う平均半径（km） =====================
RADIUS_KM = {
    '199': 2439.7,   # Mercury
    '299': 6051.84,  # Venus
    '501': 1821.6,   # Io
    '502': 1560.8,   # Europa
    '503': 2634.1,   # Ganymede
    '504': 2410.3,   # Callisto
}

# ===================== 時角 (Hour Angle) 計算 =====================
def get_hour_angle(ra_raw, obstime_utc: Time):
    """
    RA と観測時刻から時角(deg)を計算する。
    HA = LST - RA
    戻り値: float (degree, -180 to 180)
    """
    if ra_raw is None:
        return None
    try:
        # RA の SkyCoord オブジェクト作成
        ra_val = _safe_num(ra_raw)
        if ra_val is not None:
            sc = SkyCoord(ra=ra_val * u.deg, dec=0 * u.deg, frame='icrs')
        else:
            sc = SkyCoord(ra=str(ra_raw), unit=(u.hourangle, u.deg), frame='icrs')
        
        # 地方恒星時 (LST) の取得
        lst = obstime_utc.sidereal_time('mean', longitude=SITE.lon)
        
        # 時角 HA = LST - RA
        ha = lst - sc.ra
        # -180度〜180度の範囲に丸める
        return ha.wrap_at(180 * u.deg).deg
    except Exception:
        return None
    
# ===================== FITS 時刻ヘッダの取り出し =====================
def _time_from_header(header, key):
    if key not in header:
        return None
    v = header[key]
    # なるべく ISO として解釈、数値は JD とみなす
    try:
        if isinstance(v, (int, float, np.floating)):
            return Time(float(v), format='jd', scale='utc')
        return Time(str(v), format='isot', scale='utc')
    except Exception:
        return None

def get_expmid_time(header):
    """EXPMIDがあればそれを使用。無ければ EXPSTART/EXPSTOP か EXPSTART+EXPTIME で中点推定。"""
    tmid = _time_from_header(header, 'EXPMID')
    if tmid is not None:
        return tmid

    tstart = _time_from_header(header, 'EXPSTART')
    tstop  = _time_from_header(header, 'EXPSTOP')
    exptime = header.get('EXPOSURE', header.get('EXPTIME', None))

    if (tstart is not None) and (tstop is not None):
        mid_dt = tstart.utc.datetime + (tstop.utc.datetime - tstart.utc.datetime)/2.0
        return Time(mid_dt, scale='utc')
    if (tstart is not None) and (exptime is not None):
        try:
            return tstart + (float(exptime) * u.s) / 2.0
        except Exception:
            pass
    return None

# ===================== 安全キャスト（Horizons テーブル用） =====================
def _safe_num(x):
    """Quantity / masked / None / str などを安全に float へ（失敗時 None を返す）"""
    if x is None:
        return None
    try:
        # Masked?
        import numpy as _np
        if _np.ma.isMaskedArray(x):
            if getattr(x, 'mask', False) is True:
                return None
            x = x.data
        # Astropy Quantity?
        if hasattr(x, 'to_value'):
            return float(x.to_value())
        # 普通の数
        return float(x)
    except Exception:
        # 文字列 -> float できるものだけ
        try:
            s = str(x).strip()
            return float(s)
        except Exception:
            return None

# ===================== Horizons 取得 =====================
def query_horizons_ephem(hid: str, jd_utc: float):
    """
    指定 UTC JD で Haleakalā 地点からの視位置を取得。
    戻り値 dict: RA_raw/DEC_raw は数値または "hh mm ss"/"dd mm ss" の文字列。
    """
    obj = Horizons(
        id=hid,
        location={'lon': f'{LON_FOR_ASTROPY}', 'lat': f'{LAT_DEG}', 'elevation': f'{ALT_M}'},
        epochs=jd_utc,   # ephemerides() の epoch は UTC JD
    )
    # 必要な暦量のみを明示して取得
    # 1: RA/DEC, 13: angular diameter,
    # 14: sub-observer lon/lat, 15: sub-solar lon/lat,
    # 17: north-pole angle/distance,
    # 19: heliocentric range/range-rate,
    # 20: observer range/range-rate,
    # 23/24: elongation / phase geometry
    eph = obj.ephemerides(quantities='1,13,14,15,17,19,20,23,24')

    def col(name_list):
        for n in name_list:
            if n in eph.colnames:
                return eph[n][0]
        return None

    # RA/DEC は生のまま返し（数値でも文字列でも可）→ AltAz 側で解釈
    ra_raw  = col(['RA'])    # 多くは度(float)だが、環境により文字列のこともある
    dec_raw = col(['DEC'])

    #print(_safe_num(col(['rdot'])))
    #input("ccgd")

    return {
        'RA_raw':   ra_raw,
        'DEC_raw':  dec_raw,
        'r_AU':     _safe_num(col(['r'])),
        'rdot_kms': _safe_num(col(['r_rate'])),
        'delta_AU': _safe_num(col(['delta'])),
        'deldot_kms': _safe_num(col(['delta_rate'])),
        'elong_deg': _safe_num(col(['elong'])),
        'phase_deg': _safe_num(col(['alpha', 'phase'])),
        'ang_diam_arcsec': _safe_num(col(['ang_diam'])),
        'NP_ang_deg': _safe_num(col(['NPole_ang'])),
        'NP_dist_arcsec': _safe_num(col(['NPole_dist'])),
        'ObsSub_LON_deg': _safe_num(col(['PDObsLon', 'ObsSub-LON', 'Ob-lon', 'Obsrv-lon'])),
        'ObsSub_LAT_deg': _safe_num(col(['PDObsLat', 'ObsSub-LAT', 'Ob-lat', 'Obsrv-lat'])),
        'SunSub_LON_deg': _safe_num(col(['PDSunLon', 'SunSub-LON', 'Sl-lon', 'Solar-lon'])),
        'SunSub_LAT_deg': _safe_num(col(['PDSunLat', 'SunSub-LAT', 'Sl-lat', 'Solar-lat'])),
        'Tru_Anom_deg': _safe_num(col(['true_anom', 'Tru_Anom'])),
        'targetname': str(col(['targetname']) or '')
    }

def query_true_anomaly_deg(hid: str, jd_tdb: float, center: str) -> float | None:
    """elements() から真近点角（度）を得る。無ければ None。"""
    try:
        el = Horizons(id=hid, center=center, epochs=jd_tdb).elements()
        for key in ['TA', 'true_anom', 'TA_deg', 'TrueAnom', 'nu']:
            if key in el.colnames:
                v = el[key][0]
                return _safe_num(v)
        return None
    except Exception:
        return None

# ===================== Alt/Az 計算（RA/DEC が数値 or 文字列いずれもOK） =====================
def ra_dec_to_altaz(ra_raw, dec_raw, obstime_utc: Time):
    """
    ra_raw/dec_raw が float(deg) でも "hh mm ss"/"dd mm ss" でも受け付ける。
    戻り値: (elev_deg, azim_deg) もしくは (None, None)
    """
    if (ra_raw is None) or (dec_raw is None):
        return (None, None)

    try:
        # 数値（deg）の場合
        ra_val = _safe_num(ra_raw)
        dec_val = _safe_num(dec_raw)
        if (ra_val is not None) and (dec_val is not None):
            sc = SkyCoord(ra=ra_val * u.deg, dec=dec_val * u.deg, frame='icrs')
        else:
            # 文字列の場合（RA=hourangle, DEC=deg[dms]）
            sc = SkyCoord(ra=str(ra_raw), dec=str(dec_raw), unit=(u.hourangle, u.deg), frame='icrs')

        altaz = sc.transform_to(AltAz(obstime=obstime_utc, location=SITE))
        return (float(altaz.alt.deg), float(altaz.az.deg))
    except Exception:
        return (None, None)

# ===================== 角半径（arcsec） =====================
def compute_angrad_arcsec(hid: str, delta_AU: float | None, ang_diam_arcsec: float | None):
    if ang_diam_arcsec is not None:
        return ang_diam_arcsec / 2.0
    if (delta_AU is None) or (hid not in RADIUS_KM):
        return None
    R = RADIUS_KM[hid]           # km
    D = delta_AU * AU_KM         # km
    ang_rad = math.atan2(R, D)
    return math.degrees(ang_rad) * 3600.0  # arcsec

# ===================== 輝面比 =====================
def compute_illuminated_fraction(phase_deg):
    """
    位相角 Sun-Target-Observer から、見かけの円盤面積に対する輝面比を求める。

    Parameters
    ----------
    phase_deg : float
        位相角 [deg]。CSVでは STOANG。

    Returns
    -------
    float or None
        輝面比 ``(1 + cos(alpha)) / 2``。範囲は0--1。
    """
    alpha_deg = _safe_num(phase_deg)
    if alpha_deg is None:
        return None

    # Horizonsの位相角は通常0--180 deg。異常値や丸め誤差に備えて制限する。
    alpha_deg = float(np.clip(alpha_deg, 0.0, 180.0))
    illuminated_fraction = 0.5 * (1.0 + math.cos(math.radians(alpha_deg)))
    return float(np.clip(illuminated_fraction, 0.0, 1.0))

# ===================== メイン更新関数 =====================
def updCsvJPLHOR1(dsno_list, target=None):
    df = pd.read_csv(cfg.fileCsv)

    # ILMFRAC列が無い場合は作成する。輝面比なので浮動小数点として保存する。
    if 'ILMFRAC' not in df.columns:
        df['ILMFRAC'] = np.nan

    file_idx = df[df.DSNO.isin(dsno_list)]

    for index, row in file_idx.iterrows():
        hid = to_horizons_id(str(row.DATATYPE))
        filename = os.path.join(cfg.fits_path, str(row.FILENAME))
        print(f"{row.DSNO:.0f}  {row.DATATYPE} -> Horizons ID {hid}")

        try:
            with fits.open(filename) as hdul:
                hdr = hdul[0].header

            # CSV 基本カラムの反映
            if 'EXPOSURE' in hdr:
                df.at[index, 'EXPTIME'] = hdr['EXPOSURE']
            elif 'EXPTIME' in hdr:
                df.at[index, 'EXPTIME'] = hdr['EXPTIME']
            if 'EXPSTART' in hdr:
                df.at[index, 'EXPSTART'] = hdr['EXPSTART']
            if 'EXPSTOP' in hdr:
                df.at[index, 'EXPSTOP'] = hdr['EXPSTOP']
            if 'NFILES' in hdr:
                df.at[index, 'NFILES'] = hdr['NFILES']
            if 'EXPMID' in hdr:
                df.at[index, 'EXPMID'] = hdr['EXPMID']

            # 観測時刻
            tmid = get_expmid_time(hdr)
            if tmid is None:
                print("  WARN: EXPMID を取得できずスキップ")
                continue

            # Horizons: ephem（UTC JD で問い合わせ）
            eph = query_horizons_ephem(hid, jd_utc=float(tmid.utc.jd))

            # Alt/Az（対象 & 太陽）
            elev_tar, azim_tar = ra_dec_to_altaz(eph['RA_raw'], eph['DEC_raw'], tmid)
            sun_eph = query_horizons_ephem('10', jd_utc=float(tmid.utc.jd))  # Sun=10
            elev_sun, azim_sun = ra_dec_to_altaz(sun_eph['RA_raw'], sun_eph['DEC_raw'], tmid)

            # 角半径
            angrad = compute_angrad_arcsec(hid, eph['delta_AU'], eph['ang_diam_arcsec'])

            # 位相角から輝面比を計算
            #   ILMFRAC = (1 + cos(STOANG)) / 2
            illum_frac = compute_illuminated_fraction(eph['phase_deg'])

            # 真近点角（中心天体を分ける）
            if hid == '199':  # Mercury -> 太陽中心
                taa = query_true_anomaly_deg(hid, jd_tdb=float(tmid.tdb.jd), center='500@10')
            elif hid in ('501', '502', '503', '504'):  # 木星衛星 -> 木星中心
                taa = query_true_anomaly_deg(hid, jd_tdb=float(tmid.tdb.jd), center='500@599')
            else:
                taa = query_true_anomaly_deg(hid, jd_tdb=float(tmid.tdb.jd), center='500@10')

            # --- 時角の計算と TELPOS の判定 ---
            ha_val = get_hour_angle(eph['RA_raw'], tmid)
                    
            # ===== CSV 更新 =====
            if ha_val > 0:
                df.at[index, 'TELPOS'] = 'EAST'            
            else:
                df.at[index, 'TELPOS'] = 'WEST'
            if elev_tar is not None:
                df.at[index, 'ELEVTAR'] = elev_tar
            if elev_sun is not None:
                df.at[index, 'ELEVSUN'] = elev_sun
            if angrad is not None:
                df.at[index, 'ANGRAD'] = angrad  # arcsec（半径）
            if eph['elong_deg'] is not None:
                df.at[index, 'SOTANG'] = eph['elong_deg']   # 太陽離角（Sun-Observer-Target）
            if eph['phase_deg'] is not None:
                df.at[index, 'STOANG'] = eph['phase_deg']   # 位相角（Sun-Target-Observer）
            if illum_frac is not None:
                df.at[index, 'ILMFRAC'] = illum_frac
                print(
                    f"  STOANG={eph['phase_deg']:.3f} deg, "
                    f"ILMFRAC={illum_frac:.6f}"
                )
            else:
                print(
                    "  WARN: ILMFRACを計算できません "
                    f"(STOANG={eph['phase_deg']!r})"
                )
            if eph['r_AU'] is not None:
                df.at[index, 'RDISTANC'] = eph['r_AU']      # AU（太陽-対象）
            if eph['delta_AU'] is not None:
                df.at[index, 'DELTADIS'] = eph['delta_AU'] * AU_KM  # km（観測者-対象）            
            if eph['rdot_kms'] is not None:
                df.at[index, 'RDOT'] = eph['rdot_kms']      # km/s
            if eph['deldot_kms'] is not None:
                df.at[index, 'DELDOT'] = eph['deldot_kms']  # km/s
            if eph['NP_ang_deg'] is not None:
                df.at[index, 'NPANG'] = eph['NP_ang_deg']
            if eph['ObsSub_LON_deg'] is not None:
                df.at[index, 'SUBOLON'] = eph['ObsSub_LON_deg']
            if eph['ObsSub_LAT_deg'] is not None:
                df.at[index, 'SUBOLAT'] = eph['ObsSub_LAT_deg']
            if eph['SunSub_LON_deg'] is not None:
                df.at[index, 'SUBSLON'] = eph['SunSub_LON_deg']
            if eph['SunSub_LAT_deg'] is not None:
                df.at[index, 'SUBSLAT'] = eph['SunSub_LAT_deg']
            if eph['Tru_Anom_deg'] is not None:
                 df.at[index, 'TRUEAA'] = eph['Tru_Anom_deg']
            #print(eph)    

        except Exception as e:
            print(f"  ERROR: {e}")

    # ========= バックアップ & 保存 =========
    ctime = datetime.now().strftime('%Y%m%d%H%M%S')
    bk_dir = os.path.join(os.path.dirname(__file__), "bk")
    os.makedirs(bk_dir, exist_ok=True)
    file1 = os.path.join(bk_dir, ctime + os.path.basename(cfg.fileCsv))
    try:
        shutil.copy2(cfg.fileCsv, file1)
        print("backup:", file1)
    except Exception as e:
        print("backup skipped:", e)

    try:
        df.to_csv(cfg.fileCsv, index=False)
        print("Saved:", cfg.fileCsv)
    except Exception:
        print("Close the file:", cfg.fileCsv)
        input("Press Enter to proceed")
        df.to_csv(cfg.fileCsv, index=False)
        print("Saved:", cfg.fileCsv)

# ===================== スクリプトエントリ =====================
if __name__ == "__main__":
    df_all = pd.read_csv(cfg.fileCsv)
    file_idx = df_all[
        ((df_all.DATATYPE == 'IO') | (df_all.DATATYPE == 'EUROPA') | (df_all.DATATYPE == 'JI') |(df_all.DATATYPE == 'JII') |
         (df_all.DATATYPE == 'MERCURY') | (df_all.DATATYPE == 'VENUS') ) &
        # (df_all.DSNO >= 250801000) & (df_all.DSNO < 250820900) &
        # (df_all.DSNO >= 250502000) & (df_all.DSNO < 250504900) &
        #(df_all.DSNO >= 250813000) & (df_all.DSNO <= 250829900) &
        #(df_all.DSNO >= 251112000) & (df_all.DSNO <= 251112900) &
        #(df_all.DSNO >= 251208000) & (df_all.DSNO <= 251209900) &
        #(df_all.DSNO >= 260217000) & (df_all.DSNO <= 260217900) &
        #(df_all.DSNO >= 260400000) & (df_all.DSNO <= 260600900) &
        #(df_all.DSNO >= 251208000) & (df_all.DSNO <= 251209900) &
        #(df_all.DSNO >= 260810000) & (df_all.DSNO <= 260900900) 
        (df_all.DSNO >= 260910000) & (df_all.DSNO <= 261000900) 
        #(df_all.DSNO % 1000 >= 200) 
        #( (df_all.DSNO % 1000 < 200) | 
        #((df_all.DSNO % 1000 >= 200) & (df_all.DSNO % 25 <= 1)) 
    ]
    dsno = file_idx.DSNO.tolist()
    target = file_idx.DATATYPE.tolist()
    #dsno = [250820200,250820250,250820275,250820300,250820400,250820425,250820450,250820475,250820500,250820525,250820550,250820575]
    #dsno = [260811164,260811165,260811166,260811170,260811171]
    
    print(dsno, target)

    updCsvJPLHOR1(dsno_list=dsno, target=target)
