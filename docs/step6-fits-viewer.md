# Step 6 — Functional FITS viewer and status diagnostics

Implemented directly in C:/work/TIFRES. Existing reduction, launcher,
CSV editing, dependency contracts, Run/Stop and scientific calculations are
preserved. No observation product was generated or changed.

## Inspection of the actual legacy products

mkWcalSpec4d constructs spDatDcb with NumPy shape [wavelength, NFIBY, NFIBX].
Its output loop explicitly sets save_flg=False for that cube. Consequently,
no representative *.dcb.fits exists in this repository. This implementation
does not enable that output or change the reduction function.

The actual usable calibrated product is:
FILENAME.replace(".fits", ".w{fibintwid}wc.fits")
For example: 20260914/veA01_clf590w.sp.w5wc.fits.

The representative WC files contain:
- PRIMARY: float32, NumPy shape [120, 2048].
- FIBERS: int16, original IDs 0..119.
- IFIBERS: int16, 113 active original IDs.
- NFIBX=10, NFIBY=12.
- CTYPE1=WAVE, CTYPE2=FIBERID, CRPIX1=1.
- CRVAL1=585.01337, CDELT1=0.00331.
- Neither CUNIT1 nor BUNIT is present.

*.w{width}img.fits is a [12,10] image. Legacy code fills it with the
median of calibrated samples 512:1536 (after applicable sky-flat scaling).
It does not contain the wavelength spectra and cannot be used as a cube.
The viewer rejects it explicitly.

## Supported FITS structures

1. Actual WC: primary floating-point [120,N] with CTYPE1=WAVE and
   CTYPE2=FIBERID. This is logically reshaped into the wavelength/12/10 cube.
2. Standard 3D: primary floating-point [N,12,10] with CTYPE3=WAVE and
   CRVAL3/CDELT3/CRPIX3.
3. Documented legacy DCB: filename ends in dcb.fits, primary [N,12,10],
   copied WC header CTYPE1=WAVE, CTYPE2=FIBERID and WAVMIN/WAVSTEP/WAVMAX.
   This explicit legacy exception uses the copied wavelength metadata for
   the first NumPy axis, not FITS axis 1 spatial X.

All variants require NFIBX=10, NFIBY=12, exactly one FIBERS image HDU
containing integer IDs 0..119, and one IFIBERS image HDU with unique
in-range active IDs. Float32 and float64 are supported. N is variable;
at least two wavelength samples are required. Decoded numerical data is
limited to 1 GB. FITS warnings/checksum failures, malformed axes and
unsupported formats are reported; no wavelength axis is fabricated.

Supported calibration is finite, increasing, linear wavelength WCS:
lambda[i] = CRVALk + (i + 1 - CRPIXk) * CDELTk.
The final sample is lambda[N-1]. Legacy WAVMAX is one sample step past
the final center, not a sample to interpolate onto. WAVMIN/WAVSTEP, when
present, must agree with WCS; WAVMAX may be inclusive or exclusive but
must agree with one of those bounds.

CUNIT is retained and checked as a length unit when provided. Missing
CUNIT is explicitly displayed as “unspecified (CUNIT absent)”; nm is not
assumed from numerical magnitude. No unit conversion or wavelength
recalibration is applied. BUNIT is displayed when available.

## Fiber and display conventions

Original fiber ID f maps to X=f%10, Y=f/10 (integer division).
Coordinates mark pixel centers X=0..9, Y=0..11, with physical +Y upward.
Inactive IFIBERS entries are not renumbered or silently selected.
All-invalid active fibers are also excluded from selection. Inactive
pixels are dark blue-gray; nonfinite samples are purple.

IFU integration:
- Single chooses the nearest calibrated wavelength center; ties choose
  the lower sample. Out-of-range requests clamp to the nearest endpoint.
- Mean and Sum include centers satisfying lambda1 <= lambda <= lambda2.
- Nonfinite values are ignored independently for each fiber.
- No valid samples produces NaN and an explicit empty-selection message.
- Sum is the arithmetic sample sum, never a wavelength-weighted integral.

Click selects one fiber; Ctrl-click toggles it. IFU drag selects a spatial
rectangle; spectral-image drag selects an original-ID range. Both views
share SelectedFibers. Inversion applies the same transformation to image,
selection and ellipse, and mouse coordinates map back to original IDs.

Selected-fiber spectra use either Mean or Sum, with nonfinite values
ignored at each wavelength. If none are valid, the plotted value is NaN,
which breaks the line. Only the selected combination is displayed.

Ellipse axes are full lengths. Angle zero aligns width with +X; positive
angle is counterclockwise in physical coordinates before inversion.
The ellipse is a separate overlay. The IFU retains equal X/Y pixel scale
through a uniform 10:12 Viewbox and nearest-neighbor cell rendering.

Wheel zooms the shared wavelength viewport; Shift-wheel pans it. Dragging
the 1D spectrum also pans. Full resets to the actual full wavelength range.
Cursor wavelength, intensity and original fiber ID appear below the
spectral image. Each image has independent auto/manual intensity limits,
with a third independent intensity range for the 1D spectrum.

## Loading, transfer and performance

Use Open FITS without any dataset, or DSNO FITS for the explicitly
selected dataset. DSNO resolution uses its FILENAME and the current
mkWcalSpec4d fibintwid option. It checks WC and DCB only at that width.
If both exist, a chooser requires explicit selection. No other dataset
or width is substituted, and opening never starts reduction.

The configured Python executable runs the shipped tifres_viewer.py.
Astropy opens the file read-only and releases its HDUs after export.
A single binary transfer caches the numerical data in C#. There is no
Python worker or FITS read on slider movement, display edits or selection.

stdout protocol version 1:
- 4-byte unsigned little-endian JSON metadata byte count.
- UTF-8 JSON metadata (dimensions, active IDs, units, dtype and ordering).
- N float64 little-endian wavelength samples.
- 120*N float64 little-endian values, C-contiguous [fiber,wavelength].
  The conceptual 3D shape is [N,12,10].
- stderr carries errors; a nonzero exit is rejected.

Float32 values are promoted exactly to float64; float64 precision and NaN
are retained. C# decodes the binary transfer, not FITS. The numerical
cache is not altered by visualization. A bounded byte buffer avoids an
extra cube-sized C# byte array.

Loading runs off the UI thread. Large integrations/spectrum combinations
are debounced, calculated in the background and cancelled when superseded.
Revision checks prevent stale results or post-close updates. Closing
cancels loading/calculation and drops numerical and bitmap references.
Failed loads retain the previous cube with an explicit error.

The spectral bitmap is buffered at display resolution and rebuilt only
for a new cube, wavelength viewport, size or spectral intensity limits.
Ellipse, selection and IFU integration changes reuse it. Large 1D plots
use a display-only min/max envelope to bound draw calls and retain peaks.

## Compact controls and persistence

The main root 2:1, internal columns 1:4, and rows 4:2 remain unchanged.
The persistent panel stays scrollable. Labels and values share compact
rows, with related pairs side by side when width permits and wrapping
at narrow sizes. Abbreviations and full values have tooltips. Wavelength
text is committed on focus loss to avoid snapping while typing.

Validated ellipse, inversion, intensity limits, auto/manual choices and
combination modes persist in display-settings.json beside settings.json.
Previous-version manual ranges are migrated without switching them to auto.\nFile data and selections are released by Close; FITS is never auto-opened
or automatically reduced at startup.

## Status diagnostics

Refresh reports steps inspected, historical-run count and warning count.
Inspection diagnostics are available in an Expander separately from the
summary. The existing dependency/product-state logic is unchanged.

- Historical folders without optional recovery.json do not establish
  completed provenance and produce informational details.
- A missing manifest with .prepared/.previous publication evidence warns.
- Malformed metadata, failed runs, interrupted publication and recovery
  errors remain warnings with paths and diagnostic text.
- Existing provenance is still validated even if recovery.json is absent.
- Identical diagnostics are deduplicated within each inspection.
- No old run directories are removed.

## Build and automated results

- dotnet build TIFRES.sln --no-restore: successful; 0 warnings, 0 errors.
- GUI regression suite: 290 checks passed, including actual Skia rendering.
- Existing reduction/process suite: 34 checks passed.
- Existing CSV suite: 18 checks passed.
- Full Python unittest suite: 63 tests passed.
- Windows was tested; Linux runtime verification remains outstanding.

## Validation and real-data coverage

Tests use synthetic files and temporary directories. The representative
veA01_clf590w.sp.w5wc.fits was copied to a temporary directory, then loaded
through the actual Python/binary/C# path. It verified 2048 samples,
113 active fibers, exact last-sample wavelength and explicit missing units.
Original WC and IMG headers were inspected read-only.

3D loading, all-axis orientation, integration, invalid pixels, original
fiber mapping, four inversions, ellipse alignment, actual click/Ctrl-click/
drag events, buffered rendering and large-array updates use synthetic data.
A Skia-rendered synthetic screenshot is step6-synthetic-viewer.png.
No real 3D DCB file exists, so that variant was tested synthetically.
No real reduction pipeline was executed.

The environment has NumPy 2.2.6 and Astropy 6.1.7. No additional dependency
installation was needed. Windows build and tests were run; Linux uses the
same portable APIs but was not runtime-tested here.

See step6-*-tests.txt for test output and step6-preservation-before.json
for the SHA-256 baseline. All 557 protected observation/testdata/legacy
files were confirmed unchanged.

## Files modified or added

Application:
- src/Tifres.App/Tifres.App.csproj
- src/Tifres.App/Services/FitsCube.cs (new)
- src/Tifres.App/Services/ReductionStatus.cs
- src/Tifres.App/ViewModels/IfuDisplayViewModel.cs
- src/Tifres.App/ViewModels/CubeViewerViewModel.cs (new)
- src/Tifres.App/ViewModels/OperationsStatus.cs
- src/Tifres.App/Views/IfuPreview.cs
- src/Tifres.App/Views/MainWindow.axaml
- src/Tifres.App/Views/MainWindow.axaml.cs
- src/Tifres.App/Views/OperationsView.axaml

Python:
- python/tifres_viewer.py (new read-only viewer)
- python/tifres_status.py (diagnostic classification only)
- python/tests/test_viewer.py (new)
- python/tests/test_status.py
- No python/legacy file changed.

GUI tests:
- tests/Tifres.Gui.Tests/Program.cs
- tests/Tifres.Gui.Tests/IfuDisplayRegression.cs
- tests/Tifres.Gui.Tests/CubeViewerRegression.cs (new)
- tests/Tifres.Gui.Tests/GuiCancellationRegression.cs

Documentation/evidence (new):
- docs/step6-fits-viewer.md
- docs/step6-preservation-before.json
- docs/step6-synthetic-viewer.png
- docs/step6-gui-tests.txt
- docs/step6-python-tests.txt
- docs/step6-status-tests.txt
- docs/step6-process-tests.txt
- docs/step6-csv-tests.txt
