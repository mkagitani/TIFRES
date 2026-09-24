"""mkMercEmSpm4e

Changes from mkMercEmSpm4d.py:
- Added Venus/east-positive longitude support for the disk geometry overlay.
  When DATATYPE is VENUS, SUBOLON and SUBSLON are sign-reversed only when
  passed to pltLonLatMerc03, which internally expects west-positive input.
  All other processing is unchanged.


Changes from mkMercEmSpm4c.py:
- Added optional per-exposure manual absolute wavelength shift from CSV ``WAVSHIFT``.
  Blank/missing values mean 0 nm (no manual shift); positive values move the
  calibrated observed wavelength axis to longer wavelengths.
- The manual shift is applied directly to the wavelength grid read from
  ``WAVMIN``/``WAVSTEP`` before any range selection, Fraunhofer fitting,
  emission integration, or plotting. Output ``WAVMIN``/``WAVMAX`` are shifted
  consistently.
- The legacy output FITS ``WAVSHIFT`` keyword continues to store the residual
  wavelength correction fitted by the Fraunhofer+Gaussian model. The new
  ``CSVWSHFT`` keyword stores the manual CSV shift, and ``TOTWSHFT`` stores
  manual + fitted residual shift.


Changes from mkMercEmSpm4b.py:
- Sky subtraction is now optional on a per-exposure basis from the CSV.
- When both ``SKYA`` and ``SKYB`` are present, the existing time-interpolated
  SkyA/SkyB subtraction is used unchanged.
- When SkyA/SkyB are unavailable but ``SKYBG`` is present, ``SKYBG`` is used
  directly as the sky spectrum.
- When ``SKYBG``, ``SKYA``, and ``SKYB`` are all blank/NaN, sky subtraction is
  disabled completely.  ``SKYFLAT`` fiber-response correction is still applied.
- Sky-off products remain internally well defined: ISKYWC is zero, SKYMED/
  SKYAMED/SKYBMED are NaN, and FITS headers record ``SKYSUB`` and ``SKYMODE``.
- A partially specified SkyA/SkyB pair without SKYBG is treated as sky-off with
  a warning rather than aborting the DSNO.

Changes from mkMercEmSpm4a.py:
- For every displayed individual fiber, the third-row emission-spectrum title
  now reports the integrated active-line counts and 1-sigma error using the
  same fit-region residual-noise and emission-window calculation as the
  disk-fiber mean/sum spectrum, together with ``iFibAct``.


Changes from mkMercEm4Ma3t.py:
- Output ``*.sswc.fits`` and ``*.img.fits`` basenames are prefixed with
  ``DSNO_`` so products from different exposures cannot share a filename.
- The former ``line`` output-selection option has been removed.  The combined
  image FITS containing CONTINUUM, D2, D1, D2SM, and D1SM is always written.
- The former individual ``*.imCont.fits``, ``*.imD2.fits``, and
  ``*.imD1.fits`` output code is retained as comments for possible future use,
  but those files are not written.

Changes from mkMercEm4Ma3r.py:
- D2 and D1 column-density results are validated independently.  If the
  corresponding ``CTS2CDD2``/``CTS2CDD1`` factor or derived result is not
  finite, its column-density FITS keywords are omitted and its CSV result
  cells are left blank (NaN); the FITS files and subsequent DSNOs are still
  processed.
- CSV reads use ``low_memory=False`` to suppress mixed-type chunk warnings.

Changes from mkMercEm4Ma3q.py:
- The disk-mean integrated D2/D1 counts and their 1-sigma errors are converted
  to column densities with the per-exposure ``CTS2CDD2``/``CTS2CDD1`` factors.
- ``NDSKCDD2``, ``NDSKCDD1``, ``NDCDD2ER``, and ``NDCDD1ER`` are saved in
  both the output FITS headers and the raw-observation CSV table.
- When ``flgDiskTotal=True``, summed counts and errors are divided by the
  number of disk fibers before conversion, so these four quantities always
  describe the disk-mean spectrum.

Changes from mkMercEm4Ma3p.py:
- Longitude/latitude and terminator overlays now use ``pltLonLatMerc03``,
  whose east/north projection and ``NPA-PA`` image rotation match the RHapke
  model in ``fitRHapke4VCe``.  For ``TELPOS == 'EAST'``, the fitted center is
  still mapped back to the unflipped IFU frame and the relative overlay is
  rotated by 180 degrees through ``overlay_npa``.

Changes from mkMercEm4Ma3n.py:
- For ``TELPOS == 'EAST'``, the Mercury disk overlay alone is rotated by
  180 degrees to undo the ``np.flip`` coordinate convention used when
  ``fitRHapke4VCe`` fitted and saved ``DSKXIFUF``/``DSKYIFUF``.  The plotted
  IFU maps themselves are not flipped: the saved disk center is mapped back
  with ``(NFIBX - 1 - x, NFIBY - 1 - y)``, and ``NPANG`` is advanced by
  180 degrees for the longitude/latitude overlay.
- The blue Mercury curve now follows ``flgTelluricAbs`` explicitly: it is
  the T^1-divided spectrum and is labeled ``Mercury / Telluric`` when the
  correction is enabled; otherwise it is the uncorrected spectrum and is
  labeled ``Mercury``.  The same rule is used for disk-average and
  individual-fiber plots.

Changes from mkMercEm4Ma3m.py:
- ``flgTelluricAbs`` controls the analysis transmission exponent: T(lambda)^1
  is divided from the observations when True, while T(lambda)^0=1 leaves the
  spectra uncorrected when False.
- The analysis correction is independent of the display curves.  T^10 is
  plotted as an orange dotted line; a separately normalized T^1 curve is also
  calculated, but its orange dash-dot plotting commands are commented out.

Changes from mkMercEm4Ma3l.py:
- The Gaussian-convolved, unpowered telluric transmission is retained as a
  display-only array.  Its 10th power is normalized to the observed continuum
  and overplotted in orange, matching ``spMdlTrnPlot`` in mkMercEm4VgtM.py.
- The 10th-power display does not alter the telluric correction, solar fit,
  emission spectrum, or integrated line measurements.

Changes from mkMercEm4Ma3k.py:
- The disk-fiber outline is drawn by the top-level
  ``add_selected_fiber_outline(ax, fibers, n_fib_x, n_fib_y, ...)`` helper.
- Boundary segments are joined into continuous paths before applying a red
  dashed linestyle, so the dash pattern does not restart on every pixel edge.

Changes from mkMercEm4Ma3j.py:
- In the three disk-average maps, the fibers used for nDiskArea are outlined
  by the external boundary of their union.  Shared edges between neighboring
  selected fibers are no longer drawn as individual red rectangles.

Changes from mkMercEm4Ma3i.py:
- The fitted instrumental Gaussian FWHM is shown after ``nDiskArea`` in the
  second-row title and as a normalized profile in the otherwise unused panel
  to the right of the third-row emission spectrum.
- The standard deviation of the disk residual in the gray fitting regions
  (excluding the red emission windows) is used as the noise per spectral bin.
  The integrated-emission error is ``noise * sqrt(Nbin)``.  Disk D1/D2
  integrated counts, errors, bin counts, and the active-line summary are
  written to the output FITS headers.

Changes from mkMercEm4Ma3f.py:
- The solar/Fraunhofer fitting band is no longer the whole CSV WRNG1.
  WRNG1 is used only to select D2 or D1.  The selected line center is
  calculated from RDOT + DELDOT, and the fitting band is centered there
  with full width ``fraunhoferFitWidthNm`` (default 0.12 nm), matching
  mkMercEm4VgtI.py.  The planetary emission windows are excluded.

Earlier changes from mkMercEm4Ma3e.py:
- The wavelength offset and Gaussian instrumental FWHM are fitted once from
  the mean (or optional sum) of the brightest nDiskArea active fibers.
- The fitted wavelength offset and Gaussian FWHM are then fixed for every
  individual fiber; only a non-negative multiplicative solar-model scale is
  fitted per fiber.

Earlier changes from mkMercEm4Ma3d.py:
- The fitted wavelength offset is now applied to the observed wavelength axis,
  rather than shifting the solar model.
- At every least-squares evaluation, telluric transmission is re-evaluated on
  the trial corrected observed wavelength grid, and observed/telluric is
  recalculated before comparison with the solar model.
- A single Gaussian instrumental FWHM is fitted simultaneously with the
  observed wavelength-axis offset and solar amplitude. The same trial
  Gaussian is applied to both the high-resolution solar spectrum and the
  high-resolution telluric-transmission spectrum; no fixed Lorentz component
  is used.
- After fitting, observed and telluric-corrected spectra are resampled onto the
  common corrected wavelength grid before emission integration and display.

Earlier changes:
- Removed nFibShow.
- Added nDiskArea and nFibDisp, following mkMercEm4VgtH.py.
- Generates an average (or optional summed) spectrum from the brightest
  nDiskArea active fibers and saves *_afibN###.png.
- Saves individual plots for the brightest nFibDisp active fibers.
- By default, nDiskArea is read per exposure from CSV NDSKAIFU.
  Missing, non-finite, or non-positive values fall back to 14.
  When nFibDisp is omitted, it is set equal to the resolved nDiskArea.
  Explicit function arguments can override either count.
"""
import numpy as np
from matplotlib.ticker import MultipleLocator
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.gridspec as gridspec
from scipy.interpolate import interp1d
from scipy.signal import convolve
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import least_squares
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
from pltLonLatMerc03 import pltLonLatTerm

# Resonance-line rest wavelengths.  They are kept in the same wavelength
# convention as ``wavs`` and the existing wrng3/wrng4 definitions.
C_KM_S = 2.998e5
OI_D2_REST_NM = 557.7339
OI_D1_REST_NM = 557.7339
NA_D2_REST_NM = 588.995
NA_D1_REST_NM = 589.592
K_D2_REST_NM = 766.490
K_D1_REST_NM = 769.897
TELLURIC_DISPLAY_POWER = 1.0#10.0

# ========= ユーティリティ =========
def csv_value_present(value):
    """Return True when a CSV field contains a usable non-empty value."""
    if pd.isna(value):
        return False
    text = str(value).strip()
    return text.lower() not in ('', 'nan', 'none', 'null')


def move_figure_to(x=0, y=0, fig=None):
    """図ウインドウを画面座標 (x, y) に移動。主要バックエンド対応。"""
    fig = fig or plt.gcf()
    backend = plt.get_backend().lower()
    mng = fig.canvas.manager
    try:
        if 'qt' in backend:             # QtAgg / qtagg / Qt5Agg
            mng.window.move(int(x), int(y))
        elif 'tkagg' in backend:        # TkAgg
            mng.window.wm_geometry(f"+{int(x)}+{int(y)}")
        elif 'wx' in backend:           # WXAgg
            mng.window.SetPosition((int(x), int(y)))
        elif 'gtk' in backend:          # GTK
            mng.window.move(int(x), int(y))
        else:
            print(f"[info] このバックエンド({backend})では位置指定に未対応の可能性があります。")
    except Exception as e:
        print(f"[warn] ウインドウ移動に失敗: {e}")


def resolve_fiber_count(row, override=None, default=14, column='NDSKAIFU'):
    """Resolve a positive integer fiber count for one CSV row.

    When ``override`` is None, use ``row[column]``. Missing, non-finite, or
    non-positive values fall back to ``default``. A supplied override is
    validated in the same way, preserving backward-compatible manual control.
    """
    source = override
    source_name = 'argument'
    if source is None:
        source = getattr(row, column, np.nan)
        source_name = column

    try:
        value = float(source)
    except (TypeError, ValueError):
        value = np.nan

    if not np.isfinite(value) or value <= 0.0:
        value = float(default)
        source_name = f'default({int(default)})'

    # NDSKAIFU is a count. Use ordinary half-up rounding for any float value.
    count = max(1, int(np.floor(value + 0.5)))
    return count, source_name


def summarize_disk_emission(wavelength, residual, fit_mask,
                            emission_ranges_nm, labels=('D2', 'D1')):
    """Measure disk emission and its fit-residual noise.

    The noise is the sample standard deviation of ``residual`` in the gray
    least-squares region.  Because ``fit_mask`` already excludes the red
    emission intervals, emission cannot inflate this noise estimate.  The
    1-sigma error of a sum over N independent spectral bins is
    ``noise_per_bin * sqrt(N)``.
    """
    wavelength = np.asarray(wavelength, dtype=float)
    residual = np.asarray(residual, dtype=float)
    fit_mask = np.asarray(fit_mask, dtype=bool)

    noise_mask = fit_mask & np.isfinite(wavelength) & np.isfinite(residual)
    n_fit = int(np.count_nonzero(noise_mask))
    noise_per_bin = (
        float(np.std(residual[noise_mask], ddof=1)) if n_fit >= 2 else np.nan
    )

    measurements = {}
    for label, interval in zip(labels, emission_ranges_nm):
        lo, hi = sorted(map(float, interval))
        emission_mask = (
            np.isfinite(wavelength) & np.isfinite(residual)
            & (wavelength >= lo) & (wavelength <= hi)
        )
        n_bin = int(np.count_nonzero(emission_mask))
        integrated_counts = (
            float(np.sum(residual[emission_mask])) if n_bin > 0 else np.nan
        )
        integrated_error = (
            float(noise_per_bin * np.sqrt(n_bin))
            if n_bin > 0 and np.isfinite(noise_per_bin) else np.nan
        )
        measurements[str(label)] = {
            'counts': integrated_counts,
            'error': integrated_error,
            'n_bin': n_bin,
            'range_nm': (lo, hi),
        }

    return noise_per_bin, n_fit, measurements


def summarize_disk_column_density(measurements, cts2cd_d2, cts2cd_d1,
                                  n_disk_fibers,
                                  disk_spectrum_is_sum=False):
    """Convert disk integrated counts and errors to mean column densities.

    ``CTS2CDD2`` and ``CTS2CDD1`` are column density per integrated count.
    Measurements made from a summed disk spectrum are first divided by the
    number of contributing fibers; measurements from a mean spectrum already
    have the required normalization.
    """
    factors = {'D2': cts2cd_d2, 'D1': cts2cd_d1}
    divisor = float(n_disk_fibers) if disk_spectrum_is_sum else 1.0
    if not np.isfinite(divisor) or divisor <= 0.0:
        divisor = np.nan

    result = {}
    for line_name in ('D2', 'D1'):
        try:
            factor = float(factors[line_name])
        except (TypeError, ValueError):
            factor = np.nan
        if not np.isfinite(factor):
            factor = np.nan

        measurement = measurements[line_name]
        mean_counts = float(measurement['counts']) / divisor
        mean_error = float(measurement['error']) / divisor
        column_density = (
            mean_counts * factor
            if np.isfinite(mean_counts) and np.isfinite(factor) else np.nan
        )
        column_density_error = (
            abs(mean_error * factor)
            if np.isfinite(mean_error) and np.isfinite(factor) else np.nan
        )
        result[line_name] = {
            'mean_counts': mean_counts,
            'mean_error': mean_error,
            'factor': factor,
            'column_density': column_density,
            'column_density_error': column_density_error,
            'valid': bool(
                np.isfinite(factor)
                and np.isfinite(column_density)
                and np.isfinite(column_density_error)
            ),
        }

    return result


def add_gaussian_fwhm_panel(fig, subplot_spec, fwhm_nm):
    """Plot a compact vertical Gaussian profile without covering the data."""
    ax = fig.add_subplot(subplot_spec)
    fwhm_nm = float(fwhm_nm)
    if not np.isfinite(fwhm_nm) or fwhm_nm <= 0.0:
        ax.axis('off')
        return ax

    delta_nm = np.linspace(-1.5 * fwhm_nm, 1.5 * fwhm_nm, 401)
    profile = np.exp(-4.0 * np.log(2.0) * (delta_nm / fwhm_nm) ** 2)
    half_fwhm = 0.5 * fwhm_nm

    ax.plot(profile, delta_nm, color='tab:purple', lw=1.2)
    ax.plot([0.5, 0.5], [-half_fwhm, half_fwhm], color='black', lw=1.0)
    ax.plot([0.45, 0.55], [-half_fwhm, -half_fwhm], color='black', lw=0.8)
    ax.plot([0.45, 0.55], [half_fwhm, half_fwhm], color='black', lw=0.8)
    ax.set(
        xlim=(0.0, 1.05), ylim=(-1.5 * fwhm_nm, 1.5 * fwhm_nm),
        xlabel='Norm.', ylabel=r'$\Delta\lambda$ (nm)'
    )
    ax.set_title(f'Gaussian\nFWHM={fwhm_nm:.5f} nm', fontsize=6)
    ax.tick_params(axis='both', labelsize=6, pad=1)
    ax.grid(alpha=0.2)
    return ax


def add_selected_fiber_outline(
        ax, fibers, n_fib_x, n_fib_y,
        color='red', linewidth=1.3):
    """Draw the selected-fiber union boundary as continuous dashed paths.

    Shared edges between adjacent selected fibers are omitted. The remaining
    directed boundary edges are then joined into closed paths so that the
    dashed pattern continues around corners instead of restarting on every
    one-pixel edge.
    """
    selected_cells = set()
    n_fib_x = int(n_fib_x)
    n_fib_y = int(n_fib_y)

    for fiber in np.asarray(fibers, dtype=int).ravel():
        if 0 <= fiber < n_fib_x * n_fib_y:
            selected_cells.add((fiber % n_fib_x, fiber // n_fib_x))

    if not selected_cells:
        return []

    # Directed edges are oriented counterclockwise around each selected cell.
    # An edge is retained only when the neighboring cell across it is not
    # selected; shared internal edges therefore disappear.
    segments = []
    for x, y in selected_cells:
        left, right = x - 0.5, x + 0.5
        bottom, top = y - 0.5, y + 0.5

        if (x, y - 1) not in selected_cells:
            segments.append(((left, bottom), (right, bottom)))
        if (x + 1, y) not in selected_cells:
            segments.append(((right, bottom), (right, top)))
        if (x, y + 1) not in selected_cells:
            segments.append(((right, top), (left, top)))
        if (x - 1, y) not in selected_cells:
            segments.append(((left, top), (left, bottom)))

    # Join edge segments into one closed path for each connected boundary.
    # Separate selected islands (and holes, if present) form separate paths.
    remaining = set(segments)
    outline_lines = []

    while remaining:
        start, end = remaining.pop()
        points = [start, end]

        while end != start:
            next_segment = next(
                (candidate for candidate in remaining
                 if candidate[0] == end),
                None
            )
            if next_segment is None:
                # Defensive fallback for an unexpected open boundary.
                break

            remaining.remove(next_segment)
            end = next_segment[1]
            points.append(end)

        x_outline, y_outline = zip(*points)
        line, = ax.plot(
            x_outline, y_outline,
            color=color,
            linewidth=linewidth,
            linestyle=(0, (6, 3)),  # dashed: 6 pt line, 3 pt gap
            dash_capstyle='butt',
            dash_joinstyle='miter',
            zorder=6
        )
        outline_lines.append(line)

    return outline_lines


# Gaussian Kernel
def gaussian_kernel(size, sigma=1):
    x = np.linspace(-size // 2, size // 2, size)
    kernel = np.exp(-x**2 / (2 * sigma**2))
    return kernel / np.sum(kernel)


def _physical_fit_mask(wavelength, fit_range_nm, emission_ranges_nm):
    """Physical fitting-band mask excluding emission integration ranges."""
    wavelength = np.asarray(wavelength, dtype=float)
    fit_lo, fit_hi = map(float, fit_range_nm)
    mask = (wavelength >= fit_lo) & (wavelength <= fit_hi)
    for lo, hi in emission_ranges_nm:
        mask &= ~((wavelength >= float(lo)) & (wavelength <= float(hi)))
    return mask


def fit_observed_wavelength_solar_model(
        nominal_wavelength, observed_counts,
        fit_range_nm, emission_ranges_nm,
        telluric_wavelength, telluric_transmission,
        solar_wavelength, solar_highres_spectrum,
        solar_sample_step_nm, telluric_sample_step_nm=None,
        wave_shift_half_range_nm=0.020,
        gaussian_fwhm_init_nm=0.0020,
        gaussian_fwhm_min_nm=0.0002,
        gaussian_fwhm_max_nm=0.0300,
        telluric_power=1.0):
    """Fit observed wavelength offset, solar amplitude, and Gaussian FWHM.

    Trial model construction at every least-squares evaluation
    ----------------------------------------------------------
    1. ``lambda_actual = lambda_header + delta_lambda_obs``
    2. Re-evaluate telluric transmission at ``lambda_actual``.
    3. Convolve both the telluric model and solar model with the same trial
       Gaussian instrumental FWHM.
    4. Recalculate ``observed / telluric`` and restore its median count scale.
    5. Compare ``scale * solar(lambda_actual)`` with the corrected observation
       over the Doppler-centered fitting band, excluding the D2/D1 emission windows.

    Positive ``delta_lambda_obs`` means that the true observed wavelength is
    longer than the wavelength stored in the FITS wavelength solution.
    """
    nominal_wavelength = np.asarray(nominal_wavelength, dtype=float)
    observed_counts = np.asarray(observed_counts, dtype=float)
    telluric_wavelength = np.asarray(telluric_wavelength, dtype=float)
    telluric_transmission = np.asarray(telluric_transmission, dtype=float)
    solar_wavelength = np.asarray(solar_wavelength, dtype=float)
    solar_highres_spectrum = np.asarray(solar_highres_spectrum, dtype=float)

    if nominal_wavelength.shape != observed_counts.shape:
        raise ValueError('nominal_wavelength and observed_counts must have the same shape')

    wave_shift_half_range_nm = float(wave_shift_half_range_nm)
    gaussian_fwhm_init_nm = float(gaussian_fwhm_init_nm)
    gaussian_fwhm_min_nm = float(gaussian_fwhm_min_nm)
    gaussian_fwhm_max_nm = float(gaussian_fwhm_max_nm)
    solar_sample_step_nm = float(solar_sample_step_nm)
    telluric_power = float(telluric_power)
    if telluric_sample_step_nm is None:
        telluric_sample_step_nm = float(np.nanmedian(np.diff(telluric_wavelength)))
    telluric_sample_step_nm = float(telluric_sample_step_nm)

    if not np.isfinite(wave_shift_half_range_nm) or wave_shift_half_range_nm <= 0.0:
        raise ValueError('obsWaveShiftHalfRangeNm must be finite and positive')
    if not (0.0 <= gaussian_fwhm_min_nm < gaussian_fwhm_max_nm):
        raise ValueError('solar Gaussian FWHM bounds are invalid')
    gaussian_fwhm_init_nm = float(np.clip(
        gaussian_fwhm_init_nm, gaussian_fwhm_min_nm, gaussian_fwhm_max_nm
    ))
    if not np.isfinite(solar_sample_step_nm) or solar_sample_step_nm <= 0.0:
        raise ValueError('solar_sample_step_nm must be finite and positive')
    if not np.isfinite(telluric_sample_step_nm) or telluric_sample_step_nm <= 0.0:
        raise ValueError('telluric_sample_step_nm must be finite and positive')

    fit_lo, fit_hi = map(float, fit_range_nm)
    # Fixed residual vector length. The current physical mask is recalculated
    # inside the optimizer, while this candidate mask covers every sample that
    # can enter the fitting band over the allowed wavelength-offset range.
    candidate_mask = (
        (nominal_wavelength >= fit_lo - wave_shift_half_range_nm)
        & (nominal_wavelength <= fit_hi + wave_shift_half_range_nm)
        & np.isfinite(observed_counts)
    )
    candidate_index = np.flatnonzero(candidate_mask)
    if candidate_index.size < 5:
        raise ValueError(f'Too few candidate samples for solar fit: {candidate_index.size}')

    # Crop the high-resolution solar and telluric spectra with enough margin
    # for the largest allowed Gaussian instrumental convolution.
    sigma_max_nm = gaussian_fwhm_max_nm / 2.354820045
    margin_nm = max(6.0 * sigma_max_nm, 0.010)
    solar_crop_mask = (
        (solar_wavelength >= fit_lo - wave_shift_half_range_nm - margin_nm)
        & (solar_wavelength <= fit_hi + wave_shift_half_range_nm + margin_nm)
    )
    if np.count_nonzero(solar_crop_mask) < 10:
        raise ValueError('Solar model does not cover the requested fitting interval')
    solar_wave_crop = solar_wavelength[solar_crop_mask]
    solar_highres_crop = solar_highres_spectrum[solar_crop_mask]

    telluric_crop_mask = (
        (telluric_wavelength >= fit_lo - wave_shift_half_range_nm - margin_nm)
        & (telluric_wavelength <= fit_hi + wave_shift_half_range_nm + margin_nm)
    )
    if np.count_nonzero(telluric_crop_mask) < 10:
        raise ValueError('Telluric model does not cover the requested fitting interval')
    telluric_wave_crop = telluric_wavelength[telluric_crop_mask]
    telluric_highres_crop = telluric_transmission[telluric_crop_mask]

    def broaden_model(values, fwhm_nm, sample_step_nm):
        sigma_pix = max(float(fwhm_nm), 0.0) / 2.354820045 / float(sample_step_nm)
        if sigma_pix <= 1.0e-8:
            return values
        return gaussian_filter1d(
            values,
            sigma=sigma_pix,
            mode='nearest',
            truncate=6.0,
        )

    def evaluate_trial(wave_shift_nm, gaussian_fwhm_nm):
        actual_wavelength = nominal_wavelength + float(wave_shift_nm)

        telluric_broadened = broaden_model(
            telluric_highres_crop, gaussian_fwhm_nm, telluric_sample_step_nm
        )
        trn_native = np.interp(
            actual_wavelength,
            telluric_wave_crop,
            telluric_broadened,
            left=1.0,
            right=1.0,
        )
        trn_native = np.clip(trn_native, 1.0e-6, np.inf) ** telluric_power

        with np.errstate(divide='ignore', invalid='ignore'):
            corrected_native = observed_counts / trn_native

        current_fit_mask = _physical_fit_mask(
            actual_wavelength, fit_range_nm, emission_ranges_nm
        )
        current_fit_mask &= (
            candidate_mask
            & np.isfinite(corrected_native)
            & np.isfinite(observed_counts)
        )
        if np.count_nonzero(current_fit_mask) < 5:
            raise ValueError('Too few valid samples in the trial physical fitting region')

        # Preserve the original count scale after telluric division, as in the
        # preceding Ma3 code, but recalculate it for every wavelength trial.
        corr_median = np.nanmedian(corrected_native[current_fit_mask])
        obs_median = np.nanmedian(observed_counts[current_fit_mask])
        if np.isfinite(corr_median) and abs(corr_median) > 1.0e-30:
            corrected_native = corrected_native * (obs_median / corr_median)

        solar_broadened = broaden_model(
            solar_highres_crop, gaussian_fwhm_nm, solar_sample_step_nm
        )
        solar_native = np.interp(
            actual_wavelength,
            solar_wave_crop,
            solar_broadened,
            left=float(solar_broadened[0]),
            right=float(solar_broadened[-1]),
        )
        return (actual_wavelength, trn_native, corrected_native,
                solar_native, current_fit_mask, solar_broadened)

    # Initial scale and robust residual scale.
    (_, _, corrected0, solar0, fit_mask0, _) = evaluate_trial(
        0.0, gaussian_fwhm_init_nm
    )
    denom0 = float(np.dot(solar0[fit_mask0], solar0[fit_mask0]))
    scale0 = (float(np.dot(solar0[fit_mask0], corrected0[fit_mask0])) / denom0
              if denom0 > 1.0e-30 else 1.0)
    scale0 = max(scale0, 0.0)
    fit_values0 = corrected0[fit_mask0]
    data_scale = max(
        float(np.nanstd(fit_values0)),
        0.05 * float(np.nanmax(fit_values0) - np.nanmin(fit_values0)),
        1.0e-6,
    )

    def residual(p):
        scale, wave_shift_nm, gaussian_fwhm_nm = map(float, p)
        try:
            (_, _, corrected_native, solar_native,
             current_fit_mask, _) = evaluate_trial(
                wave_shift_nm, gaussian_fwhm_nm
            )
        except Exception:
            return np.full(candidate_index.size, 1.0e6, dtype=float)

        residual_all = np.zeros(candidate_index.size, dtype=float)
        use = current_fit_mask[candidate_index]
        idx = candidate_index[use]
        residual_all[use] = (
            scale * solar_native[idx] - corrected_native[idx]
        ) / data_scale
        return residual_all

    result = least_squares(
        residual,
        x0=np.array([scale0, 0.0, gaussian_fwhm_init_nm], dtype=float),
        bounds=(
            np.array([0.0, -wave_shift_half_range_nm,
                      gaussian_fwhm_min_nm], dtype=float),
            np.array([np.inf, +wave_shift_half_range_nm,
                      gaussian_fwhm_max_nm], dtype=float),
        ),
        loss='linear',
        x_scale=np.array([
            max(scale0, 1.0),
            wave_shift_half_range_nm,
            max(gaussian_fwhm_init_nm, gaussian_fwhm_min_nm, 1.0e-4),
        ], dtype=float),
        max_nfev=800,
    )

    scale = float(result.x[0])
    wave_shift_nm = float(result.x[1])
    gaussian_fwhm_nm = float(result.x[2])
    (actual_wavelength, trn_native, corrected_native, _,
     native_fit_mask, solar_broadened) = evaluate_trial(
        wave_shift_nm, gaussian_fwhm_nm
    )

    # Correct the observed wavelength solution and interpolate every observed
    # product onto the common physical wavelength grid. This allows averaging
    # fibers and integrating D1/D2 with the corrected wavelength calibration.
    raw_corrected_grid = np.interp(
        nominal_wavelength, actual_wavelength, observed_counts,
        left=np.nan, right=np.nan,
    )
    telluric_corrected_grid = np.interp(
        nominal_wavelength, actual_wavelength, corrected_native,
        left=np.nan, right=np.nan,
    )
    # Generate the final fitted solar model across the entire observed
    # wavelength span.  The optimizer itself used the smaller fitting crop,
    # but the displayed/output model must remain valid outside the fit band as well.
    output_solar_mask = (
        (solar_wavelength >= np.nanmin(nominal_wavelength) - margin_nm)
        & (solar_wavelength <= np.nanmax(nominal_wavelength) + margin_nm)
    )
    solar_wave_output = solar_wavelength[output_solar_mask]
    solar_highres_output = solar_highres_spectrum[output_solar_mask]
    sigma_pix_output = gaussian_fwhm_nm / 2.354820045 / solar_sample_step_nm
    if sigma_pix_output <= 1.0e-8:
        solar_broadened_output = solar_highres_output
    else:
        solar_broadened_output = gaussian_filter1d(
            solar_highres_output,
            sigma=sigma_pix_output,
            mode='nearest',
            truncate=6.0,
        )
    solar_fit_grid = scale * np.interp(
        nominal_wavelength,
        solar_wave_output,
        solar_broadened_output,
        left=float(solar_broadened_output[0]),
        right=float(solar_broadened_output[-1]),
    )
    telluric_output_mask = (
        (telluric_wavelength >= np.nanmin(nominal_wavelength) - margin_nm)
        & (telluric_wavelength <= np.nanmax(nominal_wavelength) + margin_nm)
    )
    telluric_wave_output = telluric_wavelength[telluric_output_mask]
    telluric_highres_output = telluric_transmission[telluric_output_mask]
    sigma_pix_telluric = (
        gaussian_fwhm_nm / 2.354820045 / telluric_sample_step_nm
    )
    if sigma_pix_telluric <= 1.0e-8:
        telluric_broadened_output = telluric_highres_output
    else:
        telluric_broadened_output = gaussian_filter1d(
            telluric_highres_output,
            sigma=sigma_pix_telluric,
            mode='nearest',
            truncate=6.0,
        )
    telluric_plot_grid = np.interp(
        nominal_wavelength,
        telluric_wave_output,
        telluric_broadened_output,
        left=1.0,
        right=1.0,
    )
    telluric_plot_grid = np.clip(telluric_plot_grid, 1.0e-6, np.inf)
    telluric_grid = telluric_plot_grid ** telluric_power
    fit_mask_grid = _physical_fit_mask(
        nominal_wavelength, fit_range_nm, emission_ranges_nm
    )

    return dict(
        scale=scale,
        wave_shift_nm=wave_shift_nm,
        gaussian_fwhm_nm=gaussian_fwhm_nm,
        raw_corrected_grid=raw_corrected_grid,
        telluric_corrected_grid=telluric_corrected_grid,
        solar_fit_grid=solar_fit_grid,
        telluric_grid=telluric_grid,
        telluric_plot_grid=telluric_plot_grid,
        fit_mask_grid=fit_mask_grid,
        native_fit_mask=native_fit_mask,
        result=result,
    )



def prepare_fixed_wavelength_solar_model(
        nominal_wavelength,
        fit_range_nm, emission_ranges_nm,
        telluric_wavelength, telluric_transmission,
        solar_wavelength, solar_highres_spectrum,
        solar_sample_step_nm, telluric_sample_step_nm,
        wave_shift_nm, gaussian_fwhm_nm,
        telluric_power=0.0):
    """Prepare one common wavelength/telluric/solar model shape.

    The wavelength correction and Gaussian FWHM are fixed.  The returned
    ``solar_native`` and ``solar_grid`` are unscaled; each fiber subsequently
    fits only one non-negative multiplicative scale.
    """
    nominal_wavelength = np.asarray(nominal_wavelength, dtype=float)
    telluric_wavelength = np.asarray(telluric_wavelength, dtype=float)
    telluric_transmission = np.asarray(telluric_transmission, dtype=float)
    solar_wavelength = np.asarray(solar_wavelength, dtype=float)
    solar_highres_spectrum = np.asarray(solar_highres_spectrum, dtype=float)

    solar_sample_step_nm = float(solar_sample_step_nm)
    telluric_sample_step_nm = float(telluric_sample_step_nm)
    wave_shift_nm = float(wave_shift_nm)
    gaussian_fwhm_nm = float(gaussian_fwhm_nm)
    telluric_power = float(telluric_power)

    if solar_sample_step_nm <= 0.0 or telluric_sample_step_nm <= 0.0:
        raise ValueError('Model wavelength steps must be positive')
    if gaussian_fwhm_nm < 0.0:
        raise ValueError('Gaussian FWHM must be non-negative')

    actual_wavelength = nominal_wavelength + wave_shift_nm
    sigma_nm = gaussian_fwhm_nm / 2.354820045
    margin_nm = max(6.0 * sigma_nm, 0.010)
    wave_lo = min(np.nanmin(actual_wavelength), np.nanmin(nominal_wavelength)) - margin_nm
    wave_hi = max(np.nanmax(actual_wavelength), np.nanmax(nominal_wavelength)) + margin_nm

    def broaden(values, sample_step_nm):
        sigma_pix = sigma_nm / float(sample_step_nm)
        if sigma_pix <= 1.0e-8:
            return np.asarray(values, dtype=float)
        return gaussian_filter1d(
            np.asarray(values, dtype=float),
            sigma=sigma_pix,
            mode='nearest',
            truncate=6.0,
        )

    solar_mask = (solar_wavelength >= wave_lo) & (solar_wavelength <= wave_hi)
    if np.count_nonzero(solar_mask) < 10:
        raise ValueError('Solar model does not cover the observed wavelength range')
    solar_wave_crop = solar_wavelength[solar_mask]
    solar_broad = broaden(solar_highres_spectrum[solar_mask], solar_sample_step_nm)

    telluric_mask = (
        (telluric_wavelength >= wave_lo) & (telluric_wavelength <= wave_hi)
    )
    if np.count_nonzero(telluric_mask) < 10:
        raise ValueError('Telluric model does not cover the observed wavelength range')
    telluric_wave_crop = telluric_wavelength[telluric_mask]
    telluric_broad = broaden(
        telluric_transmission[telluric_mask], telluric_sample_step_nm
    )

    solar_native = np.interp(
        actual_wavelength,
        solar_wave_crop,
        solar_broad,
        left=float(solar_broad[0]),
        right=float(solar_broad[-1]),
    )
    solar_grid = np.interp(
        nominal_wavelength,
        solar_wave_crop,
        solar_broad,
        left=float(solar_broad[0]),
        right=float(solar_broad[-1]),
    )

    telluric_native_unpowered = np.interp(
        actual_wavelength,
        telluric_wave_crop,
        telluric_broad,
        left=1.0,
        right=1.0,
    )
    telluric_native_unpowered = np.clip(
        telluric_native_unpowered, 1.0e-6, np.inf
    )
    telluric_native = telluric_native_unpowered ** telluric_power

    telluric_plot_grid = np.interp(
        nominal_wavelength,
        telluric_wave_crop,
        telluric_broad,
        left=1.0,
        right=1.0,
    )
    telluric_plot_grid = np.clip(telluric_plot_grid, 1.0e-6, np.inf)
    telluric_grid = telluric_plot_grid ** telluric_power

    fit_mask_native = _physical_fit_mask(
        actual_wavelength, fit_range_nm, emission_ranges_nm
    )
    fit_mask_grid = _physical_fit_mask(
        nominal_wavelength, fit_range_nm, emission_ranges_nm
    )

    return dict(
        actual_wavelength=actual_wavelength,
        solar_native=solar_native,
        solar_grid=solar_grid,
        telluric_native=telluric_native,
        telluric_grid=telluric_grid,
        telluric_plot_grid=telluric_plot_grid,
        fit_mask_native=fit_mask_native,
        fit_mask_grid=fit_mask_grid,
        wave_shift_nm=wave_shift_nm,
        gaussian_fwhm_nm=gaussian_fwhm_nm,
    )


def fit_solar_scale_with_fixed_shape(
        nominal_wavelength, observed_counts, fixed_model):
    """Fit only a non-negative solar-model scale for one fiber."""
    nominal_wavelength = np.asarray(nominal_wavelength, dtype=float)
    observed_counts = np.asarray(observed_counts, dtype=float)
    actual_wavelength = np.asarray(
        fixed_model['actual_wavelength'], dtype=float
    )
    telluric_native = np.asarray(
        fixed_model['telluric_native'], dtype=float
    )
    solar_native = np.asarray(fixed_model['solar_native'], dtype=float)
    fit_mask_native = np.asarray(
        fixed_model['fit_mask_native'], dtype=bool
    )

    if observed_counts.shape != nominal_wavelength.shape:
        raise ValueError('Observed spectrum and wavelength grid shape mismatch')

    with np.errstate(divide='ignore', invalid='ignore'):
        corrected_native = observed_counts / telluric_native

    valid_native = (
        fit_mask_native
        & np.isfinite(observed_counts)
        & np.isfinite(corrected_native)
        & np.isfinite(solar_native)
    )
    if np.count_nonzero(valid_native) < 5:
        raise ValueError('Too few valid samples for fixed-shape scale fit')

    # Keep the count level comparable before/after telluric division, following
    # the existing Ma3 processing.  This is deterministic; the only fitted
    # parameter below is the multiplicative solar-model scale.
    corr_median = np.nanmedian(corrected_native[valid_native])
    obs_median = np.nanmedian(observed_counts[valid_native])
    if np.isfinite(corr_median) and abs(corr_median) > 1.0e-30:
        corrected_native = corrected_native * (obs_median / corr_median)

    yy = corrected_native[valid_native]
    aa = solar_native[valid_native]
    denom = float(np.dot(aa, aa))
    if not np.isfinite(denom) or denom <= 1.0e-30:
        raise ValueError('Solar template has zero norm in the fitting region')
    scale = max(float(np.dot(aa, yy) / denom), 0.0)

    raw_corrected_grid = np.interp(
        nominal_wavelength,
        actual_wavelength,
        observed_counts,
        left=np.nan,
        right=np.nan,
    )
    telluric_corrected_grid = np.interp(
        nominal_wavelength,
        actual_wavelength,
        corrected_native,
        left=np.nan,
        right=np.nan,
    )
    solar_fit_grid = scale * np.asarray(fixed_model['solar_grid'], dtype=float)

    return dict(
        scale=scale,
        wave_shift_nm=float(fixed_model['wave_shift_nm']),
        gaussian_fwhm_nm=float(fixed_model['gaussian_fwhm_nm']),
        raw_corrected_grid=raw_corrected_grid,
        telluric_corrected_grid=telluric_corrected_grid,
        solar_fit_grid=solar_fit_grid,
        telluric_grid=np.asarray(fixed_model['telluric_grid'], dtype=float),
        telluric_plot_grid=np.asarray(
            fixed_model['telluric_plot_grid'], dtype=float
        ),
        fit_mask_grid=np.asarray(fixed_model['fit_mask_grid'], dtype=bool),
    )


def mkMercEmSpm4d(dsno, flgPause=True, nDiskArea=None, nFibDisp=None,
                  fibintwid=5, flgLonLat=False, flgDiskTotal=False,
                  flgTelluricAbs=True, fraunhoferFitWidthNm=0.16,
                  obsWaveShiftHalfRangeNm=0.020,
                  solarGaussianFwhmInitNm=0.015,
                  solarGaussianFwhmMinNm =0.010,
                  solarGaussianFwhmMaxNm =0.020):
    """Process requested DSNOs and write the combined image FITS product."""
    df= pd.read_csv(cfg.fileCsv, low_memory=False)
    file_idx = df[df.DSNO.isin(dsno)]

    # Analysis/correction exponent only. Display powers are constructed
    # independently from the unpowered Gaussian-convolved transmission.
    telluric_correction_applied = bool(flgTelluricAbs)
    telluric_analysis_power = 1.0 if telluric_correction_applied else 0.0
    print(
        'Telluric absorption correction: '
        f"{'ON (divide by T^1)' if telluric_correction_applied else 'OFF (divide by T^0=1)'}"
    )

    kernel=gaussian_kernel(size=91,sigma=21)
    #kernel2=gaussian_kernel(size=31,sigma=2.5)
    
    for index, row in file_idx.iterrows():
        row_dsno = int(row.DSNO)
        row_filename = str(row.FILENAME)
        output_filename = os.path.join(
            os.path.dirname(row_filename),
            f"{row_dsno}_{os.path.basename(row_filename)}",
        )

        # ------------------------------------------------------------
        # Optional manual absolute wavelength correction from CSV WAVSHIFT.
        # Blank/missing means no correction.  Sign convention:
        #   WAVSHIFT > 0  -> move the calibrated observed wavelength axis
        #                    toward longer wavelengths.
        # This is a pre-correction to the wavelength solution; the later
        # Fraunhofer+Gaussian fit can still determine a small residual shift.
        # ------------------------------------------------------------
        csv_wavshift_raw = getattr(row, 'WAVSHIFT', np.nan)
        if csv_value_present(csv_wavshift_raw):
            try:
                csv_wavshift_nm = float(csv_wavshift_raw)
            except (TypeError, ValueError):
                raise ValueError(
                    f"DSNO {row_dsno}: CSV WAVSHIFT must be a number in nm "
                    f"or blank; got {csv_wavshift_raw!r}"
                )
            if not np.isfinite(csv_wavshift_nm):
                raise ValueError(
                    f"DSNO {row_dsno}: CSV WAVSHIFT must be finite; "
                    f"got {csv_wavshift_raw!r}"
                )
        else:
            csv_wavshift_nm = 0.0

        if csv_wavshift_nm == 0.0:
            print(
                cfg.BLUE + f"[{row.DSNO:.0f}] " + cfg.RESET,
                end=''
            )
            print("Manual wavelength shift: OFF (CSV WAVSHIFT blank/0)")
        else:
            print(
                cfg.BLUE + f"[{row.DSNO:.0f}] " + cfg.RESET,
                end=''
            )
            print(
                f"Manual wavelength shift: {csv_wavshift_nm:+.6f} nm "
                "(positive = longer wavelength)"
            )

        print(cfg.BLUE+f"[{row.DSNO:.0f}] "+cfg.RESET,end='')
        #print(f"{row.DSNO:.0f} ",end='')        
        filename  = cfg.fits_path + str(row.FILENAME)
        fileWMP = cfg.fits_path + (row.WAVMAP).replace(".wmp.fits",f".w{fibintwid:.0f}wmp.fits")
        fileWC      = cfg.fits_path + (row.FILENAME).replace(".fits",f".w{fibintwid:.0f}wc.fits")

        # ------------------------------------------------------------
        # Sky-subtraction mode from CSV.
        # Priority preserves the historical behavior when a complete A/B pair
        # is supplied: SKYA+SKYB interpolation > SKYBG direct > OFF.
        # ------------------------------------------------------------
        has_sky_a = csv_value_present(getattr(row, 'SKYA', np.nan))
        has_sky_b = csv_value_present(getattr(row, 'SKYB', np.nan))
        has_sky_bg = csv_value_present(getattr(row, 'SKYBG', np.nan))

        fileSkyA = None
        fileSkyB = None
        fileSkyBg = None
        if has_sky_a:
            fileSkyA = cfg.fits_path + str(row.SKYA).replace(
                ".fits", f".w{fibintwid:.0f}wc.fits"
            )
        if has_sky_b:
            fileSkyB = cfg.fits_path + str(row.SKYB).replace(
                ".fits", f".w{fibintwid:.0f}wc.fits"
            )
        if has_sky_bg:
            fileSkyBg = cfg.fits_path + str(row.SKYBG).replace(
                ".fits", f".w{fibintwid:.0f}wc.fits"
            )

        if has_sky_a and has_sky_b:
            sky_mode = 'ABINTERP'
        elif has_sky_bg:
            sky_mode = 'SKYBG'
        else:
            sky_mode = 'OFF'

        if sky_mode == 'OFF':
            if has_sky_a != has_sky_b:
                print(
                    f"[warn] DSNO {row.DSNO:.0f}: only one of SKYA/SKYB is "
                    "specified and SKYBG is blank; Sky subtraction: OFF"
                )
            else:
                print("Sky subtraction: OFF (SKYBG, SKYA, SKYB are blank)")
        elif sky_mode == 'ABINTERP':
            print("Sky subtraction: ON (time-interpolated SKYA + SKYB)")
        else:
            print("Sky subtraction: ON (SKYBG direct)")

        if not os.path.exists(fileWC):
            print(cfg.RED+f"No file: {row.DSNO:.0f} {fileWC}"+cfg.RESET)
            continue
        elif not os.path.exists(fileWMP):
            print(f"{row.DSNO:.0f}, No file WMP: {fileWMP}")
            print("Skipped")
            continue
        elif sky_mode == 'ABINTERP' and not os.path.exists(fileSkyA):
            print(f"{row.DSNO:.0f}  No file SkyA: {fileSkyA}")
            print("Skipped")
            continue
        elif sky_mode == 'ABINTERP' and not os.path.exists(fileSkyB):
            print(f"{row.DSNO:.0f}  No file SkyB: {fileSkyB}")
            print("Skipped")
            continue
        elif sky_mode == 'SKYBG' and not os.path.exists(fileSkyBg):
            print(f"{row.DSNO:.0f}  No file SkyBg: {fileSkyBg}")
            print("Skipped")
            continue
        else:
            fileFSp     = cfg.fits_path + (row.FILENAME).replace(".fits",f".w{fibintwid:.0f}fsp.fits")
            fileFSpFlt  = cfg.fits_path + (row.FILENAME).replace(".fits",f".w{fibintwid:.0f}ffsp.fits")
            fileWC      = cfg.fits_path + (row.FILENAME).replace(".fits",f".w{fibintwid:.0f}wc.fits")
            fileSkySubWC= cfg.fits_path + output_filename.replace(".fits",f".w{fibintwid:.0f}sswc.fits")
            fileDCB     = cfg.fits_path + (row.FILENAME).replace(".fits",f".w{fibintwid:.0f}dcb.fits")
            fileIMG     = cfg.fits_path + output_filename.replace(".fits",f".w{fibintwid:.0f}img.fits")
            # Individual image products are intentionally disabled.
            # fileImCont = cfg.fits_path + output_filename.replace(
            #     ".fits", f".w{fibintwid:.0f}.imCont.fits"
            # )
            # fileImD2 = cfg.fits_path + output_filename.replace(
            #     ".fits", f".w{fibintwid:.0f}.imD2.fits"
            # )
            # fileImD1 = cfg.fits_path + output_filename.replace(
            #     ".fits", f".w{fibintwid:.0f}.imD1.fits"
            # )
            
            # Initialize all sky-related objects so OFF mode is safe throughout
            # the later plotting, FITS-writing, and CSV-update sections.
            spSkyAWC = None
            spSkyBWC = None
            spSkyBgWC = None
            jdSkyA = np.nan
            jdSkyB = np.nan
            medSkyA = np.nan
            medSkyB = np.nan
            medSkyBg = np.nan
            medSkyObj = np.nan

            if sky_mode == 'ABINTERP':
                try:
                    with fits.open(fileSkyA) as hdrSkyA:
                        print("Reading ", fileSkyA)
                        spSkyAWC = hdrSkyA[0].data
                        expmid = hdrSkyA[0].header.get('EXPMID')
                        jdSkyA = Time(expmid, format='isot', scale='utc').jd
                    with fits.open(fileSkyB) as hdrSkyB:
                        print("Reading ", fileSkyB)
                        spSkyBWC = hdrSkyB[0].data
                        expmid = hdrSkyB[0].header.get('EXPMID')
                        jdSkyB = Time(expmid, format='isot', scale='utc').jd
                except Exception as e:
                    print(f"Error on reading SKYA/SKYB for DSNO {row.DSNO:.0f}: {e}")
                    print("Skipped")
                    continue
            elif sky_mode == 'SKYBG':
                try:
                    with fits.open(fileSkyBg) as hdrSkyBg:
                        print("Reading ", fileSkyBg)
                        spSkyBgWC = hdrSkyBg[0].data
                except Exception as e:
                    print(f"Error on reading SKYBG for DSNO {row.DSNO:.0f}: {e}")
                    print("Skipped")
                    continue
                
            fileSkyFlt  = cfg.fits_path + (row.SKYFLAT).replace(".fits",f".w{fibintwid:.0f}wc.fits")
            if str(row.ELEVTAR) == 'nan': za=0.
            else: za=90.-row.ELEVTAR
            if str(row.RDOT) == 'nan': rdot=0.
            else: rdot = row.RDOT
            if str(row.DELDOT) == 'nan': ddot=0.
            else: ddot = row.DELDOT
            if str(row.SUBOLON) == 'nan': sOlon=0.
            else: sOlon = row.SUBOLON
            if str(row.SUBOLAT) == 'nan': sOlat=0.
            else: sOlat = row.SUBOLAT
            if str(row.SUBSLON) == 'nan': sSlon=0.
            else: sSlon = row.SUBSLON
            if str(row.SUBSLAT) == 'nan': sSlat=0.
            else: sSlat = row.SUBSLAT
            if str(row.NPANG) == 'nan': npa=0.
            else: npa = row.NPANG
            if str(row.PANIFU) == 'nan': panorth=0.
            else: panorth = row.PANIFU
            telpos_for_overlay = str(getattr(row, 'TELPOS', '')).strip().upper()
            if str(row.DSKXIFUF) == 'nan': cpx=5.
            else: cpx = row.DSKXIFUF
            if str(row.DSKYIFUF) == 'nan': cpy=6.
            else: cpy = row.DSKYIFUF
            if str(row.ANGRAD) == 'nan': angRad=0.
            else: angRad = row.ANGRAD
            if str(row.PSIFU) == 'nan': psIFU=0.
            else: psIFU = row.PSIFU
            R_app_pix = angRad/psIFU
            print("za,rdot,ddot,solon,solat,sslon,sslat",za,rdot,ddot,sOlon,sOlat,sSlon,sSlat)

            try:
                with fits.open(fileWC) as hd3:
                    print("Reading ",fileWC)
                    spDatWC = hd3[0].data
                    #input("aa1")
                    iFibAct = hd3['IFIBERS'].data
                    iFib = hd3['FIBERS'].data
                    hd = hd3[0].header
                    nx = hd['NAXIS1']
                    ny = hd['NAXIS2']
                    nFibX=hd['NFIBX']
                    nFibY=hd['NFIBY']
                    rwmin = hd['WAVMIN']
                    rwmax = hd['WAVMAX']
                    rwstep = hd['WAVSTEP']
                    #input("aa2")

                    # Apply the optional CSV WAVSHIFT to the *absolute* observed
                    # wavelength calibration.  Pixel spacing is unchanged.
                    wavs_unshifted = (
                        rwmin + rwstep * np.arange(nx, dtype=float)
                    )
                    wavs = wavs_unshifted + csv_wavshift_nm

                    # The output products inherit ``hd`` from fileWC.  Keep the
                    # wavelength limits consistent with the wavelength axis used
                    # by all subsequent analysis and plots.
                    hd['WAVMIN'] = (
                        float(rwmin + csv_wavshift_nm),
                        'Wavelength minimum after CSV WAVSHIFT [nm]'
                    )
                    hd['WAVMAX'] = (
                        float(rwmax + csv_wavshift_nm),
                        'Wavelength maximum after CSV WAVSHIFT [nm]'
                    )

                    jdObj  = (Time(hd['EXPMID'], format='isot', scale='utc')).jd
                    #print(wpix)
            except Exception as e:print("Error on reading ",fileWC)

            # fitRHapke4VCe rotates the IFU images by 180 deg with np.flip()
            # before fitting when TELPOS is EAST, then stores that fitted
            # center directly in DSKXIFUF/DSKYIFUF.  Keep the maps below in
            # their original orientation and rotate only the disk overlay
            # back into that coordinate system.
            #print("cpx,cpy",cpx,cpy)
            overlay_cpx = cpx
            overlay_cpy = cpy
            overlay_npa = npa
            if telpos_for_overlay == 'EAST':
                overlay_cpx = (nFibX - 1) - cpx
                overlay_cpy = (nFibY - 1) - cpy
                overlay_npa = (npa + 180.0) % 360.0
                print(
                    f"TELPOS=EAST: disk overlay rotated by 180 deg; "
                    f"center ({cpx:.3f}, {cpy:.3f}) -> "
                    f"({overlay_cpx:.3f}, {overlay_cpy:.3f}), "
                    f"NPANG {npa:.3f} -> {overlay_npa:.3f} deg"
                )
            
            try:
                with fits.open(fileSkyFlt) as hdr0:
                    print("Reading ",fileSkyFlt)
                    spSkyFltWC = hdr0[0].data
            except Exception as e:print("Error on reading ",fileSkyFlt)

            #try:
            #    with fits.open(fileDCB) as hd4:
            #        print("Reading ",fileDCB)
            #        spDcb = hd4[0].data
            #except Exception as e:print("Error on reading ",fileDCB)
        
        calwav1 = np.mean(wavs)
        print(calwav1)
        print(
            f"Wavelength calibration: original mean="
            f"{np.mean(wavs_unshifted):.6f} nm, "
            f"CSV WAVSHIFT={csv_wavshift_nm:+.6f} nm, "
            f"used mean={calwav1:.6f} nm"
        )
        
        if(calwav1 >= 548 and calwav1 <= 568):   
            fileCal='psg/psgrad548-568.txt'
            fileTrn='psg/psg_trn548-568.txt'
        elif(calwav1 >= 586 and calwav1 <= 598):   
            fileCal='psg/psgrad586-598.txt'
            fileTrn='psg/psg_trn586-598.txt'
        elif(calwav1 >= 625 and calwav1 <= 635): 
            fileCal='psg/psgrad625-635.txt'
            fileTrn='psg/psg_trn625-635.txt'
        elif(calwav1 >= 760 and calwav1 <= 780): 
            fileCal = (f"psg/psg_radZa{za:.0f}_760-780.txt")
            fileTrn = (f"psg/psg_trnZa{za:.0f}_760-780.txt")
            fileCal = (f"psg/psg_radZa45_760-780.txt")
            fileTrn = (f"psg/psg_trnZa45_760-780.txt")
            #input('gkkkl')
            #fileCal='psg/psgrad760-780.txt'
            #fileTrn='psg/psg_trn760-780.txt'
        else: sys.exit("ERROR:",file_idx.DSNO)
        
        dltDRwav=(rdot+ddot)/2.998E5*np.mean(calwav1)
        wavair2vac = 1.000276;  
        print("loading Transmittance spectrum",cfg.current_dir + fileTrn)        
        spTrn=np.loadtxt(cfg.current_dir+ fileTrn,skiprows=14)                            
        xmTrn=spTrn[:,0]/wavair2vac

        print("loading Solar spectrum",cfg.current_dir + fileCal)        
        spMdl=np.loadtxt(cfg.current_dir+ fileCal,skiprows=1)        
        xm=spMdl[:,0]/wavair2vac
        
        psg_wstep = 0.0002  # nm, high-resolution solar model sampling
        psg_fwhm_G = float(solarGaussianFwhmInitNm)

        # Gaussian-only instrumental profile for legacy diagnostic curves and
        # the conservative fallback. During the actual fit, the Gaussian FWHM
        # is varied and applied dynamically to both solar and telluric models.
        psg_sigma = (psg_fwhm_G / 2.354820045) / psg_wstep
        half_width = max(1, int(np.ceil(6.0 * psg_sigma)))
        psg_size = 2 * half_width + 1
        kerPSG = gaussian_kernel(psg_size, psg_sigma)
        ymSE = convolve(spMdl[:,1], kerPSG, mode='same')
        ymS = convolve(spMdl[:,2], kerPSG, mode='same')
        ymE = convolve(spMdl[:,3], kerPSG, mode='same')
        ymTrn = convolve(spTrn[:,1], kerPSG, mode='same')

        # High-resolution, unbroadened solar spectrum used by the fit.
        solarHighRes = spMdl[:,2]
        solarWaveMrc = xm + dltDRwav
        
        #ymTrn=ymTr.2
        print(f"rdot={rdot:.1f} km/s, ddot={ddot:.1f} km/s, dltDRwav={dltDRwav:.4f} nm")

        spTrnMdl = interp1d(xmTrn, ymTrn, kind='linear',bounds_error=False,fill_value=1.0)        
        spTrnMdl = spTrnMdl(wavs)
        spSunMdl = interp1d(xm + dltDRwav, ymS, kind='linear',bounds_error=False,fill_value=1.0)        
        spSunMdl = spSunMdl(wavs)

        spMdlTrn = interp1d(xmTrn, ymTrn, kind='linear',bounds_error=False,fill_value=1.0)        
        spMdlTrn = spMdlTrn(wavs) ** 10
        spMdlSunMrc = interp1d(xm + dltDRwav, ymS, kind='linear',bounds_error=False,fill_value=1.0)        
        spMdlSunMrc = spMdlSunMrc(wavs)

        ypix = np.arange(ny,dtype=int)
        #spImg=np.zeros((nFibY,nFibX),dtype=float)

        #ax = axes[iFig // axes.shape[1], iFig % axes.shape[1]]; iFig += 1 # Calculate grid position                  
        #roix0,roix1,roiy0,roiy1 = 0,2400,0,100
        #vrng=[np.percentile(spDat[roiy0:roiy1,roix0:roix1], 2), np.percentile(spDat, 98)]
        dltWav =  ddot / 2.998E5 * np.mean(calwav1) + 0.0 #-0.08
        
        if(calwav1 >= 548 and calwav1 <= 568):   
            #wrng1=np.array([-1,1])*1.0 + 589.30 + dltWav
            wrng1 = np.array([float(x) for x in row.WRNG1.split(",")])
            #wrng2=[wrng1[0],wrng1[0]+0.45,wrng1[1]-0.45,wrng1[1]]
            wrng2 = np.array([float(x) for x in row.WRNG2.split(",")])+ dltWav
            wrng3=np.array([-1,1])*0.015 + 557.7339 + dltWav
            wrng4=np.array([-1,1])*0.025 + 557.7339 + dltWav
        elif(calwav1 >= 586 and calwav1 <= 598):   
            #wrng1=np.array([-1,1])*1.0 + 589.30 + dltWav
            wrng1 = np.array([float(x) for x in row.WRNG1.split(",")])
            #wrng2=[wrng1[0],wrng1[0]+0.45,wrng1[1]-0.45,wrng1[1]]
            wrng2 = np.array([float(x) for x in row.WRNG2.split(",")])+ dltWav
            wrng3=np.array([-1,1])*0.015 + 588.995 + dltWav
            wrng4=np.array([-1,1])*0.015 + 589.592 + dltWav
        elif(calwav1 >= 760 and calwav1 <= 780):   
            wrng1 = np.array([float(x) for x in row.WRNG1.split(",")])
            wrng1 = wrng1 + dltWav
            #wrng1=np.array([-1,1])*1.0 + 766.0 + dltWav
            #wrng2 = [wrng1[0],wrng1[0]+0.45,wrng1[1]-0.45,wrng1[1]]
            wrng2 = np.array([float(x) for x in row.WRNG2.split(",")])+ dltWav
            wrng3 = np.array([-1,1])*0.012 + 766.490 + dltWav
            wrng4 = np.array([-1,1])*0.012 + 769.897 + dltWav

        #wrng1=np.array([-1,1])*1.0 + 769.8965 + dltWav
        #wrng2=[wrng1[0],wrng1[0]+0.45,wrng1[1]-0.45,wrng1[1]]
        #wrng3=np.array([-1,1])*0.015 + 766.4899 + dltWav
        #wrng4=np.array([-1,1])*0.015 + 769.8965 + dltWav

        iwrng1=((wavs>=wrng1[0]) & (wavs<=wrng1[1]))
        iwrng2=((wavs>=wrng2[0]) & (wavs<=wrng2[1])) | ((wavs>=wrng2[2]) & (wavs<=wrng2[3]))
        iwrng3=(wavs>=wrng3[0]) & (wavs<=wrng3[1])
        iwrng4=(wavs>=wrng4[0]) & (wavs<=wrng4[1])

        # Fraunhofer fitting band, following mkMercEm4VgtI.py.
        # WRNG1 is used only to select D2 or D1.  The physical center of the
        # selected solar Fraunhofer line is calculated from RDOT + DELDOT,
        # and fraunhoferFitWidthNm specifies the full fitting width.
        fit_width_nm = float(fraunhoferFitWidthNm)
        if not np.isfinite(fit_width_nm) or fit_width_nm <= 0.0:
            raise ValueError(
                f"fraunhoferFitWidthNm must be positive; "
                f"got {fraunhoferFitWidthNm!r}"
            )

        if 548 <= calwav1 <= 568:
            fraunhofer_rest_wavelengths = {
                'D2': OI_D2_REST_NM,
                'D1': OI_D1_REST_NM,
            }
            species_name = 'OI'
        elif 586 <= calwav1 <= 598:
            fraunhofer_rest_wavelengths = {
                'D2': NA_D2_REST_NM,
                'D1': NA_D1_REST_NM,
            }
            species_name = 'Na'
        elif 760 <= calwav1 <= 780:
            fraunhofer_rest_wavelengths = {
                'D2': K_D2_REST_NM,
                'D1': K_D1_REST_NM,
            }
            species_name = 'K'
        else:
            raise ValueError(
                f"No D1/D2 Fraunhofer rest wavelengths for calwav1={calwav1:.5f} nm"
            )

        total_radial_velocity_kms = float(rdot + ddot)
        doppler_factor = 1.0 + total_radial_velocity_kms / C_KM_S
        fraunhofer_centers = {
            name: rest_nm * doppler_factor
            for name, rest_nm in fraunhofer_rest_wavelengths.items()
        }

        analysis_center_nm = float(np.mean(wrng1))
        fraunhofer_line = min(
            fraunhofer_centers,
            key=lambda name: abs(
                fraunhofer_centers[name] - analysis_center_nm
            ),
        )
        fraunhofer_rest_nm = float(
            fraunhofer_rest_wavelengths[fraunhofer_line]
        )
        fraunhofer_center_nm = float(
            fraunhofer_centers[fraunhofer_line]
        )
        fit_lo_nm = fraunhofer_center_nm - 0.5 * fit_width_nm
        fit_hi_nm = fraunhofer_center_nm + 0.5 * fit_width_nm
        fit_range_nm = (fit_lo_nm, fit_hi_nm)

        emission_ranges_nm = (tuple(wrng3), tuple(wrng4))
        solar_fit_band_mask = (
            (wavs >= fit_lo_nm) & (wavs <= fit_hi_nm)
        )
        solar_fit_mask = _physical_fit_mask(
            wavs, fit_range_nm, emission_ranges_nm
        )
        n_solar_fit = int(np.count_nonzero(solar_fit_mask))
        if n_solar_fit < 11:
            n_in_band = int(np.count_nonzero(solar_fit_band_mask))
            raise ValueError(
                f"{species_name} {fraunhofer_line} Fraunhofer fit band "
                f"{fit_lo_nm:.5f}-{fit_hi_nm:.5f} nm "
                f"(center={fraunhofer_center_nm:.5f} nm, "
                f"width={fit_width_nm:.5f} nm) contains only "
                f"{n_solar_fit} usable samples after emission exclusion "
                f"({n_in_band} before exclusion)."
            )

        actual_fit_wavs = wavs[solar_fit_mask]
        print(
            f"Fraunhofer fit {species_name} {fraunhofer_line}: "
            f"rest={fraunhofer_rest_nm:.6f} nm, "
            f"RDOT={rdot:+.3f} km/s, DELDOT={ddot:+.3f} km/s, "
            f"v_total={total_radial_velocity_kms:+.3f} km/s, "
            f"center={fraunhofer_center_nm:.6f} nm, "
            f"requested width={fit_width_nm:.5f} nm "
            f"({fit_lo_nm:.5f}-{fit_hi_nm:.5f} nm), "
            f"used={actual_fit_wavs.min():.5f}-"
            f"{actual_fit_wavs.max():.5f} nm, N={n_solar_fit}, "
            f"emission bands excluded; "
            f"CSV WAVSHIFT={csv_wavshift_nm:+.6f} nm; "
            f"residual fit allowance=+/-"
            f"{float(obsWaveShiftHalfRangeNm):.5f} nm, "
            f"solar Gaussian FWHM="
            f"{float(solarGaussianFwhmMinNm):.5f}-"
            f"{float(solarGaussianFwhmMaxNm):.5f} nm"
        )

        # ------------------------------------------------------------
        # Construct the sky spectrum to subtract.  ABINTERP retains the exact
        # historical interpolation formula; SKYBG uses the supplied background
        # directly; OFF performs no sky subtraction.
        # ------------------------------------------------------------
        if sky_mode == 'ABINTERP':
            ta = (jdObj - jdSkyA)
            tb = (jdSkyB - jdSkyA)
            spSkyObjWC = (spSkyAWC * tb + spSkyBWC * ta) / (ta + tb)
            medSkyObj = np.median(spSkyObjWC[np.ix_(iFibAct, iwrng1)])
            medSkyA = np.median(spSkyAWC[np.ix_(iFibAct, iwrng1)])
            medSkyB = np.median(spSkyBWC[np.ix_(iFibAct, iwrng1)])
            spSkyBgWC = spSkyObjWC
            medSkyBg = medSkyObj
            print(
                f"SkyA-SkyObj:{(jdObj-jdSkyA)*1440:.1f} min, "
                f"SkyB-skyObj:{(jdSkyB-jdObj)*1440:.1f} min"
            )
            print(
                f"medSkyA, medSkyObj, medSkyB = "
                f"{medSkyA:.1f}, {medSkyObj:.1f}, {medSkyB:.1f}"
            )
        elif sky_mode == 'SKYBG':
            spSkyObjWC = np.asarray(spSkyBgWC, dtype=float)
            medSkyBg = np.median(spSkyObjWC[np.ix_(iFibAct, iwrng1)])
            medSkyObj = medSkyBg
            print(f"medSkyBgWC = {medSkyBg:.1f}")
        else:
            spSkyObjWC = np.zeros_like(spDatWC, dtype=float)
            print("Sky subtraction: OFF; object spectrum is not sky-subtracted")

        spImg2 = np.zeros((nFibY,nFibX),dtype=float)
        spImg3 = np.zeros((nFibY,nFibX),dtype=float)
        spImg4 = np.zeros((nFibY,nFibX),dtype=float)
        spSky2 = np.zeros((nFibY,nFibX),dtype=float)
        actImg = np.zeros((nFibY,nFibX),dtype=np.int16)

        # Keep an untouched copy for the OBJWC extension.  In OFF mode this
        # copy is important because the subsequent SKYFLAT correction is done
        # in-place on spDatWC.
        spDatWC0 = np.array(spDatWC, copy=True)
        if sky_mode != 'OFF':
            spDatWC = spDatWC - spSkyObjWC  # sky-subtracted Mercury
        else:
            spDatWC = np.array(spDatWC, copy=True)

        # making Super sky 1d-spectrum.  OFF mode uses zeros only as an
        # internal placeholder; it is not subtracted from the data.
        if sky_mode != 'OFF':
            sub = spSkyObjWC[iFibAct, :].astype(float, copy=False)
            clipped = sigma_clip(
                sub, sigma=3.0, maxiters=5,
                cenfunc='median', stdfunc='std', axis=0
            )
            spSky1d = clipped.mean(axis=0).filled(np.nan)
            spSkyS01d = np.array(spSky1d, copy=True)
            spSkyMdl = interp1d(
                wavs + dltDRwav, spSky1d,
                kind='linear', bounds_error=False, fill_value=1.0
            )
            spSky1d = spSkyMdl(wavs)
        else:
            spSky1d = np.zeros_like(wavs, dtype=float)
            spSkyS01d = np.zeros_like(wavs, dtype=float)

        hd['SKYSUB'] = (sky_mode != 'OFF', 'Sky subtraction applied')
        hd['SKYMODE'] = (sky_mode, 'Sky subtraction mode')

        for j in iFibAct:
            ix = j % nFibX  # 剰余演算
            iy = j // nFibX  # 商の整数部
            spSky2[iy,ix] = np.sum(spSkyFltWC[j,iwrng2])

        for j in iFibAct:
            ix = j % nFibX  # 剰余演算
            iy = j // nFibX  # 商の整数部
            spDatWC[j,:] = spDatWC[j,:] / spSky2[iy,ix] * np.mean(spSky2)

        # Select the disk-average and individual-display fibers before fitting.
        # The selection metric is the pre-fit continuum level in iwrng2.
        # nDiskArea controls the fibers combined into the high-S/N mean/sum
        # spectrum used to determine the common wavelength shift and Gaussian
        # FWHM. nFibDisp controls how many individual bright-fiber diagnostic
        # plots are produced. By default nDiskArea comes from CSV NDSKAIFU,
        # and nFibDisp is set equal to the resolved nDiskArea.
        active_fibers = np.asarray(iFibAct, dtype=int)
        if active_fibers.size == 0:
            print(f"[{row.DSNO:.0f}] No active fibers; skipped")
            continue

        n_disk_requested, n_disk_source = resolve_fiber_count(
            row, override=nDiskArea, default=14
        )
        if nFibDisp is None:
            n_plot_requested = n_disk_requested
            n_plot_source = 'nDiskArea'
        elif nFibDisp == 0:
            n_plot_requested = 0
            n_plot_source = 'argument'
        else:
            n_plot_requested, n_plot_source = resolve_fiber_count(
                row, override=nFibDisp, default=n_disk_requested
            )

        continuum_metric = np.array([
            np.nanmedian(spDatWC[j, iwrng2]) for j in active_fibers
        ], dtype=float)
        continuum_metric = np.where(
            np.isfinite(continuum_metric), continuum_metric, -np.inf
        )
        order = np.argsort(continuum_metric)[::-1]
        n_disk_use = min(n_disk_requested, active_fibers.size)
        n_plot_use = min(n_plot_requested, active_fibers.size)
        print(
            f"Fiber counts: nDiskArea={n_disk_use} [{n_disk_source}], "
            f"nFibDisp={n_plot_use} [{n_plot_source}], "
            f"Nactive={active_fibers.size}"
        )
        iDskFib = np.sort(active_fibers[order[:n_disk_use]])
        iDispFib = np.sort(active_fibers[order[:n_plot_use]])
        print("iDskFib =", iDskFib.tolist())
        print("iDispFib =", iDispFib.tolist())

        def combine_fibers(array2d, fibers):
            """Selected fibersの平均、またはflgDiskTotal=Trueなら合計を返す。"""
            if flgDiskTotal:
                return np.nansum(array2d[fibers, :], axis=0)
            return np.nanmean(array2d[fibers, :], axis=0)

        # VgtHと同じ二段階方式：まずnDiskArea本の平均（または合計）
        # スペクトルだけで、共通の観測波長補正量とGaussian FWHMを決める。
        disk_observed_for_fit = combine_fibers(spDatWC, iDskFib)
        try:
            disk_fit_out = fit_observed_wavelength_solar_model(
                nominal_wavelength=wavs,
                observed_counts=disk_observed_for_fit,
                fit_range_nm=fit_range_nm,
                emission_ranges_nm=emission_ranges_nm,
                telluric_wavelength=xmTrn,
                telluric_transmission=spTrn[:,1],
                solar_wavelength=solarWaveMrc,
                solar_highres_spectrum=solarHighRes,
                solar_sample_step_nm=psg_wstep,
                telluric_sample_step_nm=float(np.nanmedian(np.diff(xmTrn))),
                wave_shift_half_range_nm=obsWaveShiftHalfRangeNm,
                gaussian_fwhm_init_nm=solarGaussianFwhmInitNm,
                gaussian_fwhm_min_nm=solarGaussianFwhmMinNm,
                gaussian_fwhm_max_nm=solarGaussianFwhmMaxNm,
                telluric_power=telluric_analysis_power,
            )
            common_wave_shift_nm = float(disk_fit_out['wave_shift_nm'])
            common_gaussian_fwhm_nm = float(
                disk_fit_out['gaussian_fwhm_nm']
            )
            disk_fit_scale = float(disk_fit_out['scale'])
            print(
                f"Disk-average solar fit (Nfib={n_disk_use}): "
                f"scale={disk_fit_scale:.6g}, "
                f"dWobs={common_wave_shift_nm:+.6f} nm, "
                f"G-FWHM={common_gaussian_fwhm_nm:.6f} nm"
            )
        except Exception as e:
            print(
                "[warn] disk-average wavelength/Gaussian fit failed; "
                "using zero shift and initial Gaussian FWHM:", e
            )
            common_wave_shift_nm = 0.0
            common_gaussian_fwhm_nm = float(np.clip(
                solarGaussianFwhmInitNm,
                solarGaussianFwhmMinNm,
                solarGaussianFwhmMaxNm,
            ))

        # Prepare one common template.  From this point onward the wavelength
        # correction and Gaussian width are fixed; each fiber fits scale only.
        fixed_model = prepare_fixed_wavelength_solar_model(
            nominal_wavelength=wavs,
            fit_range_nm=fit_range_nm,
            emission_ranges_nm=emission_ranges_nm,
            telluric_wavelength=xmTrn,
            telluric_transmission=spTrn[:,1],
            solar_wavelength=solarWaveMrc,
            solar_highres_spectrum=solarHighRes,
            solar_sample_step_nm=psg_wstep,
            telluric_sample_step_nm=float(np.nanmedian(np.diff(xmTrn))),
            wave_shift_nm=common_wave_shift_nm,
            gaussian_fwhm_nm=common_gaussian_fwhm_nm,
            telluric_power=telluric_analysis_power,
        )

        # Refit only the amplitude of the same nDiskArea mean/sum spectrum
        # with the now-fixed common shape.  These arrays are used directly in
        # the mean-spectrum panel, so that the displayed green curve is the
        # actual fit to the nDiskArea combined spectrum—not an average of the
        # individual-fiber fitted models.
        disk_scale_fit_out = fit_solar_scale_with_fixed_shape(
            nominal_wavelength=wavs,
            observed_counts=disk_observed_for_fit,
            fixed_model=fixed_model,
        )

        # Arrays on the common corrected physical wavelength grid.
        spDatWCCorr = np.full_like(spDatWC, np.nan, dtype=float)
        spMrcOvTrn = np.full_like(spDatWC, np.nan, dtype=float)
        spMdlTrnFit1 = np.full_like(spDatWC, np.nan, dtype=float)
        spMdlTrnFit10 = np.full_like(spDatWC, np.nan, dtype=float)
        spMdlSunMrcFit = np.full_like(spDatWC, np.nan, dtype=float)
        spMrcOvTrnFit = np.full_like(spDatWC, np.nan, dtype=float)

        spTrnFit = np.full_like(spDatWC, np.nan, dtype=float)
        spMdlFit = np.full_like(spDatWC, np.nan, dtype=float)
        spSkyFit = np.full_like(spDatWC, np.nan, dtype=float)
        spSkyS0 = np.full_like(spDatWC, np.nan, dtype=float)
        spEm = np.full_like(spDatWC, np.nan, dtype=float)
        solarFitScale = np.full(spDatWC.shape[0], np.nan, dtype=float)
        obsWaveFitShiftNm = np.full(spDatWC.shape[0], np.nan, dtype=float)
        solarFitGaussianFwhmNm = np.full(spDatWC.shape[0], np.nan, dtype=float)

        for j in iFibAct:
            try:
                fit_out = fit_solar_scale_with_fixed_shape(
                    nominal_wavelength=wavs,
                    observed_counts=spDatWC[j,:],
                    fixed_model=fixed_model,
                )
            except Exception as e:
                print(f"[warn] fixed-shape scale fit failed for fiber {j}: {e}")
                # Keep the common wavelength/FWHM and use a zero solar scale.
                actual_wavelength = np.asarray(
                    fixed_model['actual_wavelength'], dtype=float
                )
                raw_corrected = np.interp(
                    wavs, actual_wavelength, spDatWC[j,:],
                    left=np.nan, right=np.nan,
                )
                with np.errstate(divide='ignore', invalid='ignore'):
                    corrected_native = (
                        spDatWC[j,:]
                        / np.asarray(fixed_model['telluric_native'], dtype=float)
                    )
                corrected_grid = np.interp(
                    wavs, actual_wavelength, corrected_native,
                    left=np.nan, right=np.nan,
                )
                fit_out = dict(
                    scale=0.0,
                    wave_shift_nm=common_wave_shift_nm,
                    gaussian_fwhm_nm=common_gaussian_fwhm_nm,
                    raw_corrected_grid=raw_corrected,
                    telluric_corrected_grid=corrected_grid,
                    solar_fit_grid=np.zeros_like(wavs, dtype=float),
                    telluric_grid=np.asarray(
                        fixed_model['telluric_grid'], dtype=float
                    ),
                    telluric_plot_grid=np.asarray(
                        fixed_model['telluric_plot_grid'], dtype=float
                    ),
                    fit_mask_grid=np.asarray(
                        fixed_model['fit_mask_grid'], dtype=bool
                    ),
                )

            fit_scale = float(fit_out['scale'])
            raw_corrected = np.asarray(fit_out['raw_corrected_grid'], dtype=float)
            corrected_grid = np.asarray(fit_out['telluric_corrected_grid'], dtype=float)
            solar_fit_grid = np.asarray(fit_out['solar_fit_grid'], dtype=float)
            telluric_grid = np.asarray(fit_out['telluric_grid'], dtype=float)
            telluric_plot_grid = np.asarray(fit_out['telluric_plot_grid'], dtype=float)
            fit_mask_grid = np.asarray(fit_out['fit_mask_grid'], dtype=bool)

            solarFitScale[j] = fit_scale
            obsWaveFitShiftNm[j] = common_wave_shift_nm
            solarFitGaussianFwhmNm[j] = common_gaussian_fwhm_nm
            spDatWCCorr[j,:] = raw_corrected
            spMrcOvTrn[j,:] = corrected_grid
            spMrcOvTrnFit[j,:] = corrected_grid
            spMdlSunMrcFit[j,:] = solar_fit_grid

            # Display only. These arrays are independent of the analysis
            # exponent used by telluric_grid/telluric_corrected_grid.
            spMdlTrnPlot1 = np.clip(telluric_plot_grid, 0.0, np.inf)
            spMdlTrnPlot10 = (spMdlTrnPlot1 ** TELLURIC_DISPLAY_POWER)
            trn1_med = np.nanmedian(spMdlTrnPlot1[iwrng2])
            trn10_med = np.nanmedian(spMdlTrnPlot10[iwrng2])
            obs_med = np.nanmedian(raw_corrected[iwrng2])            
            if np.isfinite(trn1_med) and abs(trn1_med) > 1.0e-30:
                spMdlTrnFit1[j,:] = (spMdlTrnPlot1 / trn1_med * obs_med)
            else:
                spMdlTrnFit1[j,:] = spMdlTrnPlot1
            if np.isfinite(trn10_med) and abs(trn10_med) > 1.0e-30:
                spMdlTrnFit10[j,:] = (spMdlTrnPlot10 / trn10_med * obs_med)
            else:
                spMdlTrnFit10[j,:] = spMdlTrnPlot10

            # Legacy diagnostic arrays, normalized on the corrected grid.
            spTrnFit[j,:] = spMdlTrnFit10[j,:]
            model_med = np.nanmedian(spSunMdl[fit_mask_grid])
            if np.isfinite(model_med) and abs(model_med) > 1.0e-30:
                spMdlFit[j,:] = spSunMdl / model_med * obs_med
            sky_med = np.nanmedian(spSky1d[fit_mask_grid])
            if np.isfinite(sky_med) and abs(sky_med) > 1.0e-30:
                spSkyFit[j,:] = spSky1d / sky_med * obs_med
            sky0_med = np.nanmedian(spSkyS01d[fit_mask_grid])
            if np.isfinite(sky0_med) and abs(sky0_med) > 1.0e-30:
                spSkyS0[j,:] = spSkyS01d / sky0_med * obs_med

            spEm[j,:] = spMrcOvTrnFit[j,:] - spMdlSunMrcFit[j,:]

        finite_scales = solarFitScale[active_fibers]
        finite_scales = finite_scales[np.isfinite(finite_scales)]
        if finite_scales.size:
            print(
                f"Individual scale-only fits: median={np.median(finite_scales):.6g}, "
                f"min={np.min(finite_scales):.6g}, "
                f"max={np.max(finite_scales):.6g}"
            )

        for j in iFibAct:
            ix = j % nFibX
            iy = j // nFibX
            spImg2[iy,ix] = np.nanmedian(spDatWCCorr[j,iwrng2])
            spImg3[iy,ix] = np.nansum(spEm[j,iwrng3])
            spImg4[iy,ix] = np.nansum(spEm[j,iwrng4])
            actImg[iy,ix] = 1

        # Mean/sum-spectrum display uses the direct fit to
        # disk_observed_for_fit. Individual-fiber products above use the same
        # fixed wavelength shift and Gaussian FWHM, with scale fitted alone.
        disk_dat = np.asarray(disk_scale_fit_out['raw_corrected_grid'], dtype=float)
        disk_mrc_over_trn = np.asarray(disk_scale_fit_out['telluric_corrected_grid'], dtype=float)
        disk_mercury_for_plot = (disk_mrc_over_trn if telluric_correction_applied else disk_dat)
        mercury_label = (
            'Disk / Telluric'
            if telluric_correction_applied else 'Disk'
        )
        disk_sun_model = np.asarray(disk_scale_fit_out['solar_fit_grid'], dtype=float)
        disk_fit_mask_grid = np.asarray(disk_scale_fit_out['fit_mask_grid'], dtype=bool)
        disk_telluric_plot_grid = np.asarray(disk_scale_fit_out['telluric_plot_grid'], dtype=float)
        # Display-only T^1 and T^10 curves, each normalized independently to
        # the same observed continuum level.
        disk_telluric_plot1 = np.clip(disk_telluric_plot_grid, 0.0, np.inf)
        disk_telluric_plot10 = (disk_telluric_plot1 ** TELLURIC_DISPLAY_POWER)
        disk_trn1_med = np.nanmedian(disk_telluric_plot1[iwrng2])
        disk_trn10_med = np.nanmedian(disk_telluric_plot10[iwrng2])
        disk_obs_med = np.nanmedian(disk_dat[iwrng2])

        if np.isfinite(disk_trn1_med) and abs(disk_trn1_med) > 1.0e-30:
            disk_trn_model1 = (disk_telluric_plot1 / disk_trn1_med * disk_obs_med)
        else:
            disk_trn_model1 = disk_telluric_plot1
        if np.isfinite(disk_trn10_med) and abs(disk_trn10_med) > 1.0e-30:
            disk_trn_model10 = (disk_telluric_plot10 / disk_trn10_med * disk_obs_med)
        else:
            disk_trn_model10 = disk_telluric_plot10
        disk_emission = disk_mrc_over_trn - disk_sun_model
        disk_wave_shift_nm = common_wave_shift_nm
        disk_gaussian_fwhm_nm = common_gaussian_fwhm_nm
        disk_noise_per_bin, disk_noise_nfit, disk_emission_measurements = (summarize_disk_emission(wavs, disk_emission, disk_fit_mask_grid,emission_ranges_nm, labels=('D2', 'D1')))
        active_emission = disk_emission_measurements[fraunhofer_line]
        disk_column_density = summarize_disk_column_density(
            disk_emission_measurements,
            getattr(row, 'CTS2CDD2', np.nan),
            getattr(row, 'CTS2CDD1', np.nan),
            n_disk_use,
            disk_spectrum_is_sum=flgDiskTotal,
        )
        print(
            f"Disk {fraunhofer_line} emission: "
            f"{active_emission['counts']:.6g} +/- "
            f"{active_emission['error']:.6g} counts; "
            f"fit-residual std={disk_noise_per_bin:.6g} count/bin, "
            f"Nfit={disk_noise_nfit}, Nem={active_emission['n_bin']}"
        )
        for line_name in ('D2', 'D1'):
            cd_measurement = disk_column_density[line_name]
            if cd_measurement['valid']:
                print(
                    f"Disk-mean {line_name} column density: "
                    f"{cd_measurement['column_density']:.6g} +/- "
                    f"{cd_measurement['column_density_error']:.6g} cm^-2"
                )
            else:
                print(
                    f"[warning] Disk-mean {line_name} column density skipped: "
                    f"CTS2CD factor or derived value is missing/non-finite."
                )

        inactive_img = (actImg == 0)
        spImg2msk = np.ma.array(spImg2, mask=inactive_img)
        spImg3msk = np.ma.array(spImg3, mask=inactive_img)
        spImg4msk = np.ma.array(spImg4, mask=inactive_img)

        if 1 == 1 :
            hd['FRLINE'] = (fraunhofer_line, 'Fraunhofer line selected by WRNG1')
            hd['FRREST'] = (fraunhofer_rest_nm, 'Fraunhofer rest wavelength [nm]')
            hd['FRCENT'] = (fraunhofer_center_nm, 'RDOT+DELDOT center [nm]')
            hd['FRWIDTH'] = (fit_width_nm, 'Fraunhofer fit full width [nm]')
            hd['FRLO'] = (fit_lo_nm, 'Fraunhofer fit lower bound [nm]')
            hd['FRHI'] = (fit_hi_nm, 'Fraunhofer fit upper bound [nm]')
            # ``WAVSHIFT`` is retained with its historical meaning in this
            # script: the residual correction fitted by the solar/Fraunhofer
            # model.  ``CSVWSHFT`` is the manually supplied pre-correction.
            hd['WAVSHIFT'] = (
                common_wave_shift_nm,
                'Residual wavelength correction from solar fit [nm]'
            )
            hd['CSVWSHFT'] = (
                csv_wavshift_nm,
                'Manual absolute wavelength shift from CSV [nm]'
            )
            hd['TOTWSHFT'] = (
                csv_wavshift_nm + common_wave_shift_nm,
                'CSV manual + fitted residual wavelength shift [nm]'
            )
            hd['GFWHM'] = (common_gaussian_fwhm_nm, 'Fitted Gaussian FWHM [nm]')
            hd['TELLREQ'] = (bool(flgTelluricAbs), 'Telluric division requested')
            hd['TELLCOR'] = (bool(flgTelluricAbs), 'T^1 division applied')
            hd['TRNANPOW'] = (
                float(telluric_analysis_power),
                'Telluric exponent used for analysis division'
            )
            hd['TRNDPOW'] = (
                float(TELLURIC_DISPLAY_POWER),
                'Telluric exponent used for dotted display'
            )
            hd['NDSKAREA'] = (int(n_disk_use), 'Fibers in disk mean/sum spectrum')
            hd['DISKMODE'] = ('SUM' if flgDiskTotal else 'MEAN', 'Disk spectrum combination')
            hd['FITRSTD'] = (disk_noise_per_bin, 'Fit-region residual stddev [count/bin]')
            hd['FITRN'] = (int(disk_noise_nfit), 'Bins used for FITRSTD')
            hd['EMLINE'] = (fraunhofer_line, 'Line summarized by EMSUM and EMERR')
            hd['EMSUM'] = (active_emission['counts'], 'Disk emission sum [count]')
            hd['EMERR'] = (active_emission['error'], '1-sigma error of EMSUM [count]')
            hd['EMNPIX'] = (int(active_emission['n_bin']), 'Bins summed for EMSUM')
            for line_name in ('D2', 'D1'):
                line_measurement = disk_emission_measurements[line_name]
                hd[f'{line_name}SUM'] = (
                    line_measurement['counts'], f'Disk {line_name} emission sum [count]'
                )
                hd[f'{line_name}ERR'] = (
                    line_measurement['error'], f'1-sigma error of {line_name}SUM [count]'
                )
                hd[f'{line_name}NPIX'] = (
                    int(line_measurement['n_bin']), f'Bins summed for {line_name}SUM'
                )
            cd_header_keys = {
                'D2': ('NDSKCDD2', 'NDCDD2ER'),
                'D1': ('NDSKCDD1', 'NDCDD1ER'),
            }
            for line_name, (value_key, error_key) in cd_header_keys.items():
                cd_measurement = disk_column_density[line_name]
                if cd_measurement['valid']:
                    hd[value_key] = (
                        cd_measurement['column_density'],
                        f'Disk-mean {line_name} column density [cm-2]'
                    )
                    hd[error_key] = (
                        cd_measurement['column_density_error'],
                        f'1-sigma error of {value_key} [cm-2]'
                    )
                else:
                    # Astropy does not permit NaN floating values in a FITS
                    # header.  Remove any inherited stale keyword and let the
                    # rest of the FITS product be written normally.
                    for key in (value_key, error_key):
                        if key in hd:
                            del hd[key]
            # Combined image FITS: CONTINUUM, D2, D1 and fitted-model maps.
            hdu_list=[]
            hdu_list.append(fits.PrimaryHDU(data=spImg2.astype(np.float32), header=hd))
            hdu_list.append(fits.ImageHDU(data=spImg2.astype(np.float32), name='CONTINUUM'))
            hdu_list.append(fits.ImageHDU(data=spImg3.astype(np.float32), name='D2'))
            hdu_list.append(fits.ImageHDU(data=spImg4.astype(np.float32), name='D1'))
            hdu_list.append(fits.ImageHDU(data=spImg3.astype(np.float32), name='D2SM'))
            hdu_list.append(fits.ImageHDU(data=spImg4.astype(np.float32), name='D1SM'))
            hdu_list.append(fits.ImageHDU(data=actImg.astype(np.int16), name='ACTFIB'))
            hdu_list.append(fits.ImageHDU(data=iFib.astype(np.int16), name='FIBERS'))
            hdu_list.append(fits.ImageHDU(data=iFibAct.astype(np.int16), name='IFIBERS'))
            hdul = fits.HDUList(hdu_list)
            hdul.writeto(fileIMG, overwrite=True)
            print(fileIMG," saved")

            # Individual image-FITS output is intentionally disabled.  Keep
            # these examples for possible future restoration.
            # fits.PrimaryHDU(
            #     data=spImg2.astype(np.float32), header=hd
            # ).writeto(fileImCont, overwrite=True)
            # fits.PrimaryHDU(
            #     data=spImg3.astype(np.float32), header=hd
            # ).writeto(fileImD2, overwrite=True)
            # fits.PrimaryHDU(
            #     data=spImg4.astype(np.float32), header=hd
            # ).writeto(fileImD1, overwrite=True)
        ###############################
        if 1 == 1 :
            hdu_list=[]
            hdu_list.append(fits.PrimaryHDU(data=spDatWC.astype(np.float32), header=hd))
            hdu_list.append(fits.ImageHDU(data=spDatWC0.astype(np.float32), name='OBJWC'))
            hdu_list.append(fits.ImageHDU(data=spSkyObjWC.astype(np.float32), name='ISKYWC'))
            hdu_list.append(fits.ImageHDU(data=iFib.astype(np.int16), name='FIBERS'))
            hdu_list.append(fits.ImageHDU(data=iFibAct.astype(np.int16), name='IFIBERS'))
            hdul = fits.HDUList(hdu_list)
            hdul.writeto(fileSkySubWC, overwrite=True)
            print(fileSkySubWC," saved")
            #spSky2[iy,ix] = np.sum(spSkyFltWC[j,iwrng2])
        
        #ddot=-12 #km/s
        #spDat=spDatWC
        nWnd=0

        # ------------------------------------------------------------
        # VgtHと同じ表示形式：平均（または合計）スペクトル＋個別スペクトル
        # ------------------------------------------------------------
        nWnd = 0

        # VgtHと同じ横軸表示範囲。CSVのWRNG3を優先し、取得できない場合はwrng1を使う。
        try:
            wrng3o = np.array([float(x) for x in str(row.WRNG3).split(",")]) + dltWav
            if wrng3o.size != 2 or not np.all(np.isfinite(wrng3o)):
                raise ValueError
        except Exception:
            wrng3o = np.asarray(wrng1, dtype=float)

        try:
            wrng4o = np.array([float(x) for x in str(row.WRNG4).split(",")]) + dltWav
            if wrng4o.size != 2 or not np.all(np.isfinite(wrng4o)):
                raise ValueError
        except Exception:
            wrng4o = np.asarray(wrng4, dtype=float)

        roix0 = max(0, int((wrng3o[0] - rwmin) / rwstep))
        roix1 = min(nx - 1, int((wrng3o[1] - rwmin) / rwstep))
        if roix1 <= roix0:
            roix0 = max(0, int((wrng1[0] - rwmin) / rwstep))
            roix1 = min(nx - 1, int((wrng1[1] - rwmin) / rwstep))
        roiy0, roiy1 = 0, len(iFib)
        xrng = [wrng3o[0] - 0.5*rwstep, wrng3o[1] + 0.5*rwstep]
        roi_slice = slice(roix0, roix1 + 1)

        def safe_percentile(values, q, default=0.0):
            values = np.asarray(values, dtype=float)
            values = values[np.isfinite(values)]
            if values.size == 0:
                return float(default)
            return float(np.percentile(values, q))

        def build_fit_intervals(base_range, excluded_ranges):
            """Return contiguous intervals in base_range outside exclusions."""
            base_lo, base_hi = sorted(map(float, base_range))
            clipped = []
            for rng in excluded_ranges:
                lo, hi = sorted(map(float, rng))
                lo = max(lo, base_lo)
                hi = min(hi, base_hi)
                if hi > lo:
                    clipped.append((lo, hi))
            clipped.sort()

            intervals = []
            cursor = base_lo
            for lo, hi in clipped:
                if lo > cursor:
                    intervals.append((cursor, lo))
                cursor = max(cursor, hi)
            if cursor < base_hi:
                intervals.append((cursor, base_hi))
            return intervals

        solar_fit_intervals = build_fit_intervals(fit_range_nm, (wrng3, wrng4))

        def shade_fit_regions(ax):
            """Show solar least-squares regions and emission exclusions."""
            for k, (lo, hi) in enumerate(solar_fit_intervals):
                ax.axvspan(
                    lo, hi, alpha=0.08, color='gray',
                    label='Solar least-squares fit regions' if k == 0 else None
                )
            for k, rng in enumerate((wrng3, wrng4)):
                ax.axvspan(
                    rng[0], rng[1], alpha=0.10,
                    facecolor='red', edgecolor='red', hatch='///',
                    label='Emission integration regions' if k == 0 else None
                )

        def style_spectral_axis(ax):
            ax.tick_params(axis='both', labelsize=8)
            ax.grid(alpha=0.2)

        def add_disk_overlay(ax):
            if not flgLonLat:
                return

            # pltLonLatMerc03 expects west-positive longitudes.
            # JPL Horizons uses east-positive longitudes for Venus, so reverse
            # only the sub-observer/sub-solar longitudes passed to the overlay.
            lon_sign = -1.0 if str(row.DATATYPE).strip().upper() == 'VENUS' else 1.0

            ov = pltLonLatTerm(
                lon_sign * sOlon, sOlat, lon_sign * sSlon, sSlat,
                NPA_deg=overlay_npa, PA_deg=panorth
            )
            for seg in ov['meridians']:
                ax.plot(overlay_cpx + R_app_pix*seg[:,0],
                        overlay_cpy + R_app_pix*seg[:,1],
                        lw=0.3, color='white')
            for seg in ov['parallels']:
                ax.plot(overlay_cpx + R_app_pix*seg[:,0],
                        overlay_cpy + R_app_pix*seg[:,1],
                        lw=0.3, color='white')
            tf = ov['terminator']
            ax.plot(overlay_cpx + R_app_pix*tf[:,0],
                    overlay_cpy + R_app_pix*tf[:,1],
                    lw=1.0, color='white')
            disk = ov['disk']
            ax.plot(overlay_cpx + R_app_pix*disk[:,0],
                    overlay_cpy + R_app_pix*disk[:,1],
                    lw=0.3, color='white')

        def add_map_panel(fig, subplotspec, map_data, title, selected_fibers=None):
            ax = fig.add_subplot(subplotspec)
            if np.ma.isMaskedArray(map_data):
                active_values = np.asarray(map_data.compressed(), dtype=float)
            else:
                active_values = np.asarray(map_data[actImg == 1], dtype=float)
            vmax = safe_percentile(active_values, 99.9, default=1.0)
            if not np.isfinite(vmax) or vmax <= 0:
                vmax = 1.0
            im = ax.imshow(
                map_data, cmap='viridis', origin='lower', interpolation='none',
                vmin=0, vmax=vmax
            )
            ax.set_title(title, fontsize=8)
            ax.set(
                xlim=[-0.5, nFibX-0.5], ylim=[-0.5, nFibY-0.5],
                xlabel=f'IFU X (/{psIFU:.2f}")',ylabel=f'IFU Y (/{psIFU:.2f}")',
            )
            ax.tick_params(axis='both', labelsize=8)
            cbar = fig.colorbar(im, ax=ax, shrink=1.0)
            cbar.ax.tick_params(labelsize=8)
            if selected_fibers is not None:
                add_selected_fiber_outline(
                    ax, selected_fibers, nFibX, nFibY
                )
            add_disk_overlay(ax)
            ax.xaxis.set_major_locator(MultipleLocator(1))
            ax.yaxis.set_major_locator(MultipleLocator(1))
            return ax

        # -------------------- disk mean/sum spectrum --------------------
        #fig = plt.figure(figsize=(9,10), dpi=300)
        fig = plt.figure(figsize=(9,10), dpi=96)
        gs = gridspec.GridSpec(
            4, 2, height_ratios=[1,1,1,1], width_ratios=[15,1.2]
        )
        move_figure_to(0, 0, fig)
        plt.subplots_adjust(
            wspace=0.04, hspace=0.5,
            left=0.08, right=0.90, top=0.95, bottom=0.05
        )

        # top: 2-D spectra
        ax = fig.add_subplot(gs[0, 0])
        img_values = spDatWCCorr[np.ix_(active_fibers, np.arange(roix0, roix1+1))]
        vrng_img = [
            safe_percentile(img_values, 0.05, default=0.0),
            safe_percentile(img_values, 99.95, default=1.0),
        ]
        if vrng_img[1] <= vrng_img[0]:
            vrng_img[1] = vrng_img[0] + 1.0
        vrng_img[0]    =0
        im = ax.imshow(
            spDatWCCorr[roiy0:roiy1+1, roix0:roix1+1],
            cmap='viridis', aspect='auto', origin='lower', interpolation='none',
            vmin=vrng_img[0], vmax=vrng_img[1],
            extent=[xrng[0], xrng[1], roiy0-0.5, roiy1+0.5]
        )
        ax.set_title(
            str(int(row.DSNO)) + "  "
            + os.path.basename(os.path.dirname(fileWC)) + "/"
            + os.path.basename(fileWC) + '  sky subtracted',
            fontsize=9
        )
        ax.set(xlabel='Wavelength (nm)', ylabel='Fiber Number')
        ax.tick_params(axis='both', labelsize=8)

        ax_cbar = fig.add_subplot(gs[0, 1])
        ax_cbar.axis('off')
        cbar = fig.colorbar(im, ax=ax_cbar)
        cbar.ax.tick_params(labelsize=8)

        # middle-top: observed spectrum, solar model, telluric transmission, emission
        ax = fig.add_subplot(gs[1, 0])
        ax.plot(
            wavs, disk_dat, lw=1.0, color='black',
            label='Planet disk', drawstyle='steps-mid'
        )
        ax.plot(
            wavs, disk_mercury_for_plot, lw=1.5, color='blue',
            label=mercury_label, drawstyle='steps-mid'
        )

        ax.plot(
            wavs, disk_sun_model, lw=1.2, color='green',
            label=(f'Solar fit\n'
                   f'dWobs={disk_wave_shift_nm:+.5f} nm\n'
                   f'G-FWHM={disk_gaussian_fwhm_nm:.5f} nm'
                   )
        )

        # T^1 is calculated above but hidden by default.
        #ax.plot(
        #    wavs, disk_trn_model1, lw=1.0, ls='-.', color='orange',
        #    label='Telluric Trans.^1'
        #)
        #ax.plot(wavs, disk_trn_model10, lw=1.0, ls='--', color='orange',label=f"Telluric Trans.^{TELLURIC_DISPLAY_POWER}")
        ax.plot(wavs, disk_trn_model10, lw=1.0, ls='--', color='orange',label="Telluric Trans.")
        ax.plot(wavs, disk_emission, lw=1.0, color='red',label='Emission', drawstyle='steps-mid')
        shade_fit_regions(ax)
        ax.set_title(
            #f"Disk spectrum and solar model,  nDiskArea={n_disk_use}"
            #+ (" (sum)" if flgDiskTotal else " (mean)")
            #+ f",dWobs={obsWaveFitShiftNm:+.5f} nm, ",
            #+ f",  G-FWHM={disk_gaussian_fwhm_nm:.5f} nm",
            "Planet disk spectrum, solar model, and extracted emission ",
            fontsize=9
        )
        peak = safe_percentile(disk_dat[roi_slice], 99.95, default=1.0)
        if peak <= 0:
            peak = max(abs(safe_percentile(disk_dat[roi_slice], 0.05, default=-1.0)), 1.0)
        ax.set(
            xlim=xrng, ylim=[-0.10*peak, 1.05*peak],
            xlabel='Wavelength (nm)', ylabel='Count'
        )
        style_spectral_axis(ax)
        ax.axhline(y=0, color='black', linestyle='--', linewidth=1)
        ax.legend(loc='upper right', fontsize=6)

        # middle-bottom: emission only
        ax = fig.add_subplot(gs[2, 0])
        em_roi = disk_emission[roi_slice]
        em_lo = safe_percentile(em_roi, 0.05, default=-1.0)
        em_hi = 1.2 * safe_percentile(em_roi, 99.95, default=1.0)
        if em_hi <= em_lo:
            em_lo, em_hi = -1.0, 1.0
        ax.set_title(
            f"Emission spectrum: {fraunhofer_line} = "
            f"{active_emission['counts']:.2f} +/- "
            f"{active_emission['error']:.2f} counts",
            fontsize=9
        )
        ax.set(
            xlim=xrng, ylim=[em_lo, em_hi],
            xlabel='Wavelength (nm)', ylabel='Count'
        )
        shade_fit_regions(ax)
        ax.plot(
            wavs, disk_emission, label='Emission',
            drawstyle='steps-mid', lw=1.0, color='red'
        )
        ax.axhline(y=0, color='black', linestyle='--', linewidth=1)
        ax.legend(loc='upper right', fontsize=6)
        style_spectral_axis(ax)

        # The right-hand cell is otherwise unused on this row, so the
        # Gaussian-width diagnostic does not cover the emission spectrum.
        #add_gaussian_fwhm_panel(fig, gs[2, 1], disk_gaussian_fwhm_nm)

        # bottom: continuum, D2, D1 maps
        gs_row2 = gridspec.GridSpecFromSubplotSpec(
            1, 3, subplot_spec=gs[3, :], width_ratios=[1,1,1], wspace=0.5
        )
        add_map_panel(
            fig, gs_row2[0], spImg2msk,
            f"{int(row.DSNO)}  Continuum", selected_fibers=iDskFib
        )
        add_map_panel(
            fig, gs_row2[1], spImg3msk,
            f"D2, {wrng3[0]:.3f}-{wrng3[1]:.3f}", selected_fibers=iDskFib
        )
        add_map_panel(
            fig, gs_row2[2], spImg4msk,
            f"D1, {wrng4[0]:.3f}-{wrng4[1]:.3f}", selected_fibers=iDskFib
        )

        strDate = ((row.FILENAME).replace("fits/", ""))[0:8]
        filePng = (
            f"{cfg.current_dir}png/"
            + (os.path.basename(__file__)).replace('.py', '/' + strDate + '/')
            + f"{row.DSNO:.0f}_"
            + (os.path.basename(fileWC)).replace('.fits', '_afibN')
            + f"{n_disk_use:03d}.png"
        )
        print(filePng)
        if not os.path.exists(os.path.dirname(filePng)):
            os.makedirs(os.path.dirname(filePng))
        plt.savefig(filePng, bbox_inches='tight', pad_inches=0.05)
        nWnd += 1
        plt.draw()
        plt.pause(0.001)
        if flgPause:
            input("Press any key to proceed (mean spectrum)")

        # -------------------- individual spectra --------------------
        for j in iDispFib:
            ix = j % nFibX
            iy = j // nFibX
            print(j, ix, iy, nWnd, ' ', end='')

            #fig = plt.figure(figsize=(9,10), dpi=300)
            fig = plt.figure(figsize=(9,10), dpi=96)
            gs = gridspec.GridSpec(
                4, 2, height_ratios=[1,1,1,1], width_ratios=[15,1.2]
            )
            move_figure_to(0, 0, fig)
            plt.subplots_adjust(
                wspace=0.04, hspace=0.5,
                left=0.08, right=0.90, top=0.95, bottom=0.05
            )

            # top: 2-D spectra, selected fiber highlighted
            ax = fig.add_subplot(gs[0, 0])
            ax.axhline(y=j, color='black', linewidth=1)
            ax.axhline(y=j, color='white', ls='--', linewidth=1)
            im = ax.imshow(
                spDatWCCorr[roiy0:roiy1+1, roix0:roix1+1],
                cmap='viridis', aspect='auto', origin='lower', interpolation='none',
                vmin=vrng_img[0], vmax=vrng_img[1],
                extent=[xrng[0], xrng[1], roiy0-0.5, roiy1+0.5]
            )
            ax.set_title(
                str(int(row.DSNO)) + "  "
                + os.path.basename(os.path.dirname(fileWC)) + "/"
                + os.path.basename(fileWC)
                + f"   iFibAct={j}  sky subtracted",
                fontsize=8
            )
            ax.set(xlabel='Wavelength (nm)', ylabel='Fiber Number')
            ax.tick_params(axis='both', labelsize=8)

            ax_cbar = fig.add_subplot(gs[0, 1])
            ax_cbar.axis('off')
            cbar = fig.colorbar(im, ax=ax_cbar)
            cbar.ax.tick_params(labelsize=8)

            # middle-top: individual observed/model spectra
            ax = fig.add_subplot(gs[1, 0])
            peak_j = safe_percentile(spDatWCCorr[j, roi_slice], 99.95, default=1.0)
            if peak_j <= 0:
                peak_j = 1.0
            ax.set_title(f"iFibAct={j}", fontsize=8)
            ax.set(
                xlim=xrng, ylim=[-0.2*peak_j, 1.2*peak_j],
                xlabel='Wavelength (nm)', ylabel='Count'
            )
            shade_fit_regions(ax)
            ax.plot(
                wavs, spDatWCCorr[j,:], label='Planet disk',
                linewidth=1, color='black', drawstyle='steps-mid'
            )
            ax.plot(
                wavs,
                (spMrcOvTrnFit[j,:] if telluric_correction_applied
                 else spDatWCCorr[j,:]),
                label=mercury_label,
                linewidth=1.5, color='blue', drawstyle='steps-mid'
            )
            ax.plot(
                wavs, spMdlSunMrcFit[j,:],
                label=(f'Solar fit @ Mercury '
                       #f'(dWobs={obsWaveFitShiftNm[j]:+.5f} nm, '
                       #f'G-FWHM={solarFitGaussianFwhmNm[j]:.5f} nm)'
                       ),
                linewidth=1.0, color='green'
            )
            # T^1 is calculated above but hidden by default.
            #ax.plot(
            #    wavs, spMdlTrnFit1[j,:], label='Telluric Trans.^1',
            #    linewidth=1.0, linestyle='-.', color='orange'
            #)
            ax.plot(
                wavs, spMdlTrnFit10[j,:], label='Telluric Trans.^10',
                linewidth=1.0, linestyle=':', color='orange'
            )
            ax.plot(
                wavs, spEm[j,:], label='Emission',
                linewidth=1.0, color='red', drawstyle='steps-mid'
            )
            ax.axhline(y=0, color='black', linestyle='--', linewidth=1)
            ax.legend(loc='upper right', fontsize=6)
            style_spectral_axis(ax)

            # middle-bottom: individual emission only
            ax = fig.add_subplot(gs[2, 0])
            em_j = spEm[j, roi_slice]
            em_j_lo = safe_percentile(em_j, 0.05, default=-100.0)
            em_j_hi = 1.2 * safe_percentile(em_j, 99.95, default=200.0)
            if em_j_hi <= em_j_lo:
                em_j_lo, em_j_hi = -100.0, 200.0

            # Use the same fit-residual noise and emission-integration method
            # as the disk-fiber mean/sum spectrum.
            (
                fiber_noise_per_bin,
                fiber_noise_nfit,
                fiber_emission_measurements,
            ) = summarize_disk_emission(
                wavs,
                spEm[j, :],
                disk_fit_mask_grid,
                emission_ranges_nm,
                labels=('D2', 'D1'),
            )
            fiber_active_emission = fiber_emission_measurements[
                fraunhofer_line
            ]
            ax.set_title(
                f"Emission Spectrum: {fraunhofer_line} = "
                f"{fiber_active_emission['counts']:.2f} +/- "
                f"{fiber_active_emission['error']:.2f} [counts], "
                f"iFibAct={j}",
                fontsize=8,
            )
            ax.set(
                xlim=xrng, ylim=[em_j_lo, em_j_hi],
                xlabel='Wavelength (nm)', ylabel='Count'
            )
            shade_fit_regions(ax)
            ax.plot(
                wavs, spEm[j,:], label='Emission',
                drawstyle='steps-mid', linewidth=1.0, color='red'
            )
            ax.axhline(y=0, color='black', linestyle='--', linewidth=1)
            ax.legend(loc='upper right', fontsize=6)
            style_spectral_axis(ax)

            # bottom: continuum, D2, D1 maps
            gs_row2 = gridspec.GridSpecFromSubplotSpec(
                1, 3, subplot_spec=gs[3, :], width_ratios=[1,1,1], wspace=0.5
            )
            selected = [j]
            add_map_panel(
                fig, gs_row2[0], spImg2msk,
                f"{int(row.DSNO)}  [ix,iy]=[{ix},{iy}]\nCont.",
                selected_fibers=selected
            )
            add_map_panel(
                fig, gs_row2[1], spImg3msk,
                f"D2, {wrng3[0]:.3f}-{wrng3[1]:.3f}",
                selected_fibers=selected
            )
            add_map_panel(
                fig, gs_row2[2], spImg4msk,
                f"D1, {wrng4[0]:.3f}-{wrng4[1]:.3f}",
                selected_fibers=selected
            )

            strDate = ((row.FILENAME).replace("fits/", ""))[0:8]
            filePng = (
                f"{cfg.current_dir}png/"
                + (os.path.basename(__file__)).replace('.py', '/' + strDate + '/')
                + f"{row.DSNO:.0f}_"
                + (os.path.basename(fileWC)).replace('.fits', '_ifib')
                + f"{j:03d}.png"
            )
            print(filePng)
            if not os.path.exists(os.path.dirname(filePng)):
                os.makedirs(os.path.dirname(filePng))
            plt.savefig(filePng, bbox_inches='tight', pad_inches=0.05)
            nWnd += 1
            plt.draw()
            plt.pause(0.001)
            if flgPause:
                input("Press any key to proceed 1")

        df.at[index,'SKYMED'] = medSkyObj
        df.at[index,'SKYAMED'] = medSkyA
        df.at[index,'SKYBMED'] = medSkyB
        cd_csv_keys = {
            'D2': ('NDSKCDD2', 'NDCDD2ER'),
            'D1': ('NDSKCDD1', 'NDCDD1ER'),
        }
        for line_name, (value_key, error_key) in cd_csv_keys.items():
            cd_measurement = disk_column_density[line_name]
            if cd_measurement['valid']:
                df.at[index, value_key] = cd_measurement['column_density']
                df.at[index, error_key] = cd_measurement['column_density_error']
            else:
                # CSV supports missing values; keep unavailable results blank.
                df.at[index, value_key] = np.nan
                df.at[index, error_key] = np.nan

        plt.pause(0.01)
        
        for j in range(nWnd): plt.close()
        nWnd=0    
                
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
                                
    print("All finished")   
    plt.show() # stops at this line

# スクリプトの最後にこれを追加する
if __name__ == "__main__":
    df= pd.read_csv(cfg.fileCsv, low_memory=False)
    file_idx = df[(df.DATATYPE == 'MERCURY')
                  #& (df.DSNO >= 250630000) & (df.DSNO <= 250720000)                  
                  #& (df.DSNO >= 250707000) & (df.DSNO <= 250710000)                  
                  #& (df.DSNO >= 250812000) & (df.DSNO < 250815000)
                  #& (df.DSNO >= 250817000) & (df.DSNO < 250818000)
                  #& (df.DSNO >= 250819000) & (df.DSNO < 250820000)
                  #& (df.DSNO >= 250820000) & (df.DSNO < 250821000)
                  & (df.DSNO % 25 == 0)
                  #& (df.DSNO >= 250504200) & (df.DSNO <= 250504990)                  
                  & (df.DSNO >=  260217250) & (df.DSNO < 260217990)
                  #& (df.DSNO >= 251111000) & (df.DSNO < 251112000)
                  #& (df.DSNO >= 251112000) & (df.DSNO < 251113000)
                  #& (df.DSNO >= 251112650) & (df.DSNO < 251113000)
                  #& (df.DSNO >= 251208200) & (df.DSNO < 251210000)
                  #& (df.DSNO >=  260217200) & (df.DSNO < 260217990)
                  #& (df.DSNO >=  260422200) & (df.DSNO < 260422990)
                  #& (df.DSNO >=  260423200) & (df.DSNO < 260423990)
                  #& (df.DSNO >=  260424200) & (df.DSNO < 260424990)
                  #& (df.DSNO >=  260422200) & (df.DSNO < 260427990)
                  ]    
    dsno = file_idx.DSNO.astype('int64').tolist()
    #file_idx2 = file_idx[file_idx['DSNO'] % 25 ==0]
    #dsno = file_idx2['DSNO'].astype('int64').tolist()
    #dsno = [250816200,250816225,250816250,250816275,250816300]
    #dsno = [250710325]
    #dsno = [251112350,251112375,251112400,251112425]
    #dsno = [251112651,251112676,251112701,251112726]    
    #dsno = [251208226]
    #dsno = [250502250,250502300,250502350]

    ### === K D1 ===
    dsno = [250502251,250502301,250502351]
    #dsno = [250819276,250819301,250819326,250819351]
    #dsno = [251112351,251112376,251112401,251112426]
    #dsno = [251112651,251112676,251112701,251112726]
    #dsno = [251208226,251208276,251209226]
    #dsno = [260217276,260217301]
    
    ### === Na D2 ===
    #dsno = [250504200,250504225,250504250,250504275,250504300,250504325,250504350,250504375,250504400,250504425,250504450,250504475] #Na
    #dsno = [250816200,250816225,250816250,250816275]
    #dsno = [251111425,251111450,251111475,251111500,251111525]    
    #dsno = [251208250,251208350,251209200,251209300,251209325,251209350]
    #dsno = [260217250,260217325,260217350]

    #=== Na D2 all ===
    dsno = [250504200,250504225,250504250,250504275,250504300,250504325,250504350,250504375,250504400,250504425,250504450,250504475,
            250816200,250816225,250816250,250816275,250820250,
            250820200,250820250,250820275,250820300,250820400,250820425,250820450,250820475,250820500,250820525,250820550,250820575,
            251111425,251111450,251111475,251111500,251111525,
            251208250,251208350,251209200,251209300,251209325,251209350,
            260217250,260217325,260217350]

    #=== K D2 ===
    dsno = [251112200,251112350,251112375,251112400,251112425,] 
    #dsno = [250502200,250502225,250502250,250502300,250502350,] #bad
    #dsno = [250819275,250819300,250819325,250819350,] #bad
    #dsno = [251112200,251112350,251112375,251112400,251112425] # good
    #dsno = [251208225,251208275,251209225,] # bad
    #dsno = [260217275,260217300,260217400,] #bad
    
    dsno = [260811164,260811165,260811166,260811170,260811171]
    dsno = [260811170]
    dsno = [260811164,260811165,260811166,260811170]
    dsno = [260811171]
    dsno = [260915162,260915163,260915164]
    dsno = [260916161,260916162,260916163,260916164]
    dsno = [260917164]

    print(dsno)
    mkMercEmSpm4d(dsno, 
        flgPause=False,
        fibintwid=5,flgLonLat=True,
        flgTelluricAbs=True,
        nFibDisp=1, # nFibDisp omitted: use the resolved nDiskArea
        # nDiskArea omitted: use row.NDSKAIFU (fallback 14);                  
        #,flgDiskTotal=True
        )
