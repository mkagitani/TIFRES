# Step 3: individual Python reductions

Implemented in the existing `C:\work\TIFRES` solution. No alternate workspace or application regeneration was used. The initial integration left legacy files unchanged. Subsequent improvements change only legacy PNG roots and add cfg.png_path; see [the follow-up report](step3-improvements.md) for current behavior and validation. `legacy-inventory.json` records their SHA-256 hashes, every function signature (including helpers), imports, referenced configuration/CSV fields, file I/O calls, and live interactive calls. Generate it without importing any legacy code:

```powershell
python python/inspect_legacy.py python/legacy > docs/legacy-inventory.json
```

## Configuration and use

In Settings choose a Python 3.10+ executable, a directory containing the five legacy scripts and `cfg.py`, the dataset CSV, the raw CCD root, and the FITS output root. The latter also holds products from earlier individual steps. File/folder pickers are available. Save Settings persists to `Environment.SpecialFolder.LocalApplicationData/TIFRES/settings.json`; settings also save on Run and application close. There are no workstation-specific path defaults. Packaged legacy scripts are the initial script directory; choose the original script directory if it contains additional reference files.

Open the settings CSV using the Operations button or the Dataset tab, select a DSNO, then choose an individual step. Alternatively disable “Use selected Dataset DSNO” and enter comma/space-separated identifiers. Save dataset edits before running. Dataset and Settings editing are disabled during a run. CSV metadata is reloaded after successful processing. Run Required Steps, FITS viewing, `mkMercEmSpm`, and ephemeris execution are not implemented.

Options are an editable JSON object using the legacy names and defaults, except that overwrite is reserved exclusively for the checkbox and omitted from the editor. The launcher reads defaults from the selected source file's AST and rejects unknown names, wrong types, duplicate JSON keys, and invalid sizes. It passes a list of Python integers as `dsno`, never floating-point identifiers. The GUI now initializes mkFibFit with finterval=8/flgPause=false and mkWcalSpec with flgPlot=false, retaining last-used options; its noninteractive policy forces `flgPause=False`, and the explicit overwrite checkbox controls `overwrite` where that argument exists. Effective options appear in the log. `flgPlot`/`flgShowAll` remain editable; original Python function defaults are unchanged.

Example (replace all placeholder paths):

```text
python python/tifres_launcher.py --script-dir /path/to/legacy --csv /path/to/datasets.csv --raw-dir /path/to/raw --fits-dir /path/to/fits --step mkFibSpec4d --dsno 260914010 260914111 --options-json '{"fibintwid":5}'
```

`--check-only` performs path, CSV, options, input, output-conflict, and dependency preflight without importing the legacy processing module. `--overwrite` explicitly permits replacement of existing FITS products. CSV file references must be relative to their configured root; both slash styles are accepted, while rooted paths and parent traversal are rejected. Raw ORIGIN patterns preserve the original `file_search` regex semantics, including `{a,b}` alternatives.

## Interfaces and file contract

`N` below is `fibintwid`; suffix replacement follows the legacy `.replace('.fits', ...)` conventions. Every selected dataset requires DSNO and FILENAME. The full inventory includes every field access and helper signature.

| Callable and original defaults | Inputs | Published FITS outputs | Additional CSV fields |
| --- | --- | --- | --- |
| `mkSpFrames4f(dsno, overwrite=True, flgPause=True, nxFig=2, nyFig=5)` | Raw ORIGIN matches; DARKFRAME if specified | FILENAME and its `.m.fits` companion | DATATYPE, ORIGIN; metadata columns CCDTEMP, EXPTIME, EXPSTART, EXPSTOP, NFILES, EXPMID, FMSTD must exist |
| `mkFibFit4c(dsno, flgPause=False, finterval=1)` | FILENAME, DARKFRAME | FILENAME → `.fib.fits` | FIBX0, FIBX1, FIBXWID; NFIBXY and IFIBIACT columns, allowing blank legacy defaults |
| `mkFibSpec4d(dsno, flgPause=False, flgShowAll=False, fibintwid=5, overwrite=True)` | FILENAME, DARKFRAME, WLFLAT → `.fib.fits` | FILENAME → `.wNfsp.fits` | WLFLAT |
| `mkWavMap4d(dsno, flgPause=True, fibintwid=5, flgNoWLflat=False, fiberCoefDegree=2)` | FILENAME → `.wNfsp.fits`; WLFLAT → `.wNfsp.fits` when enabled; solar reference text | FILENAME → `.wNwmp.fits` | CALWAV1, WAVSTEP1, PIXWAV1, CALWAVS; PIXWAVS may be blank; PIXDWAVS required when PIXWAVS is supplied |
| `mkWcalSpec4d(dsno, flgPlot=True, fibintwid=5, overwrite=True, flgNoWLflat=False)` | FILENAME, its `.wNfsp.fits`, WAVMAP (replace `.wmp.fits` with `.wNwmp.fits`), WLFLAT extraction when enabled, SKYFLAT extraction when supplied | FILENAME → `.wNwc.fits` and `.wNimg.fits`; SKYFLAT → `.wNwc.fits` when supplied | WLFLAT, SKYFLAT, WAVMAP, WAVSHIFT (blank shift retains zero default) |

The `.ffsp.fits` and `.dcb.fits` names in `mkWcalSpec4d` are constructed but not written by the supplied code. The sky wavelength-calibrated output is a real additional product and is included in overwrite checks.

## Runtime boundary and safety

The launcher loads cfg into the child process and overrides only `fileCsv`, `original_path`, `fits_path`, `current_dir`, `pythonide`, and `flgWpos`. It never rewrites the original configuration. `current_dir` and `fits_path` point to a run staging directory, so mkSpFrames' DARKFRAME lookup uses the configured FITS root's staged copy. Required solar references are copied from the script directory into staging.

Each run creates `FITS_ROOT/.tifres-runs/<unique-id>/`. Required FITS inputs and the CSV are copied there. Raw CCD files are read directly. Numerical processing executes the original callable with its original helper functions. Only I/O/display behavior is adapted:

- Force Matplotlib Agg, including suppressing mkWcalSpec's hard-coded Qt5Agg backend switch. `show()` and `pause()` cannot block; PNG diagnostics use the configured PNG root (legacy script directory/png when unset), retaining script and dataset subdirectories.
- Disable optional pauses; any unexpected `input()` raises a visible error rather than supplying an answer to an error-recovery prompt.
- Normalize CSV path separators in the in-memory DataFrame, preserve DSNO as exact Python integers (including legacy `.0f` display), and keep original text for saving.
- Intercept the legacy pandas CSV write: merge only changed values in the seven mkSpFrames metadata columns for selected rows. Preserve the original column sequence, unedited values, strings, padding, blanks, leading-zero DSNO text, and separator rows. Reject schema changes or unexpected cell changes.
- Redirect mkSpFrames' Windows-style backup path into staging. Catch FITS-open failures even when legacy code catches their exceptions. Require every expected output and verify its FITS structure before publishing, so an early return is not reported as success.

Existing products are checked before numerical work. Only complete staged outputs are published. Without overwrite permission, same-filesystem hard-link creation atomically refuses an existing destination, including a racing writer. With permission, a complete temporary copy replaces each destination. Publication is per file, not an all-products transaction: interruption during publication can leave some completed products published. No Stop cleanup deletes any existing product. Staging, diagnostics, and input copies are retained even after success/failure/Stop and can consume substantial disk space. An output filesystem must support hard links for no-overwrite publication; unsupported operations fail visibly.

Metadata CSV changes are committed only after processing succeeds and the on-disk source still matches its original bytes, using a timestamped backup and temporary-file replacement. A concurrent external CSV edit aborts the commit. The app blocks concurrent reductions in-process; launcher OS locks serialize use of the same FITS root or CSV across launcher processes. OS locks release on process termination; lock files themselves can remain.

The C# service uses `System.Diagnostics.Process` with `ArgumentList`, shell execution disabled, UTF-8 redirected stdout/stderr, closed stdin, asynchronous waits, and `Kill(entireProcessTree: true)` on Stop. It validates Python's version with a timed probe. Closing the app during a run first requests cancellation and waits for completion. GUI logs are bounded to avoid indefinite memory growth; truncation is marked.

## Inspected dependencies and legacy issues

The five supported modules import only `cfg` as a local module. Required third-party packages: NumPy, SciPy, pandas, Matplotlib, Astropy (`python/requirements.txt`). Verified imports in the available Python 3.10 environment: NumPy 2.2.6, SciPy 1.15.3, pandas 2.3.2, Matplotlib 3.10.3, Astropy 6.1.7. The user-selected interpreter is checked separately at runtime; these installed versions are not forced or installed by this implementation.

Missing assets/dependencies:

- None of `psg/psgrad548-568.txt`, `psgrad586-596.txt`, `psgrad625-635.txt`, or `psgrad760-780.txt` is supplied. `mkWavMap4d` requires the file corresponding to CALWAV1 in the selected script directory. The launcher reports the exact missing path.
- PyQt5 is absent but is unnecessary in this launcher's noninteractive Agg mode.
- The out-of-scope `mkMercEmSpm4e.py` exposes `mkMercEmSpm4d(...)` and imports missing local `pltLonLatMerc03.pltLonLatTerm`. It also reads solar/telluric reference files, sky products and wavelength-calibrated products, writes image/sky-subtracted FITS and CSV metadata, moves windows, and pauses/prompts. It is inventoried but never offered or imported by the launcher.
- The out-of-scope `updCsvJPLHOR1d.py` exposes `updCsvJPLHOR1(dsno_list, target=None)` plus helpers. It requires Astroquery, Astropy coordinates/units, and JPL Horizons network access; reads FILENAME FITS and updates ephemeris/time CSV fields. Astroquery is installed in the inspected environment. Its CSV-error prompt is recorded in the inventory; it is not executed.

No scientific source changes were needed. Future legacy fixes to consider separately:

- `mkWcalSpec4d` calls `.replace` on WLFLAT before checking whether it is missing. The launcher rejects blank WLFLAT even if `flgNoWLflat=True`; fixing the legacy order would allow that case.
- Some legacy failures are printed and caught or skipped internally. Input preflight, FITS-open failure tracking, prompt rejection, and output verification cover the integration boundary; scientific fit-quality acceptance remains the original code's responsibility.
- mkSpFrames expects the `TEMP` header when updating CCDTEMP inside a broad metadata try/except; datasets with only `CCD-TEMP` may need a separate legacy correction. The numerical calculations are unchanged.

## Validation

Run from the solution directory:

```text
dotnet build TIFRES.sln
python -B -m unittest discover -s python/tests -v
dotnet run --project tests/Tifres.Reduction.Tests -- python
dotnet run --project tests/Tifres.Csv.Tests -- testdata/hmew202510MeBpy2.csv
dotnet run --project tests/Tifres.Gui.Tests
```

Launcher tests execute only mock functions and generated tiny FITS files in temporary directories; original scripts are inspected through AST, never reduced against observation data. Tests cover exact/multiple DSNO handling, defaults and JSON validation, runtime cfg overrides, all five dispatches, missing raw/FITS/reference files, overwrite protection including companion products, source/schema preservation, failure exit codes, unexpected prompts, Agg mode, locks, and path validation. C# tests cover settings, executable/path validation, argument handling, stdout/stderr, exit codes, cancellation including a child process, and conflict prevention. CSV regression tests retain Step 2 coverage. Linux and interactive desktop GUI behavior have not been exercised on this Windows host.

## Files changed or added for Step 3

Modified:
- src/Tifres.App/Tifres.App.csproj
- src/Tifres.App/ViewModels/MainWindowViewModel.cs
- src/Tifres.App/Views/MainWindow.axaml
- src/Tifres.App/Views/MainWindow.axaml.cs

Added:
- src/Tifres.App/Services/ReductionProcess.cs
- src/Tifres.App/ViewModels/SettingsViewModel.cs
- src/Tifres.App/ViewModels/OperationsViewModel.cs
- src/Tifres.App/Views/SettingsView.axaml
- src/Tifres.App/Views/SettingsView.axaml.cs
- src/Tifres.App/Views/OperationsView.axaml
- src/Tifres.App/Views/OperationsView.axaml.cs
- python/tifres_launcher.py
- python/inspect_legacy.py
- python/requirements.txt
- python/tests/test_launcher.py
- tests/Tifres.Reduction.Tests/Tifres.Reduction.Tests.csproj
- tests/Tifres.Reduction.Tests/Program.cs
- docs/legacy-inventory.json
- docs/step3.md

Final Windows validation: solution build passed with zero warnings and errors; 15 Python launcher tests, 16 C# process/settings checks, and 18 CSV regression checks passed. The five processing steps were exercised only through mock callables; no original observation data was reduced. Legacy files were supplied by the user and are not implementation changes, even if Git currently lists them as untracked.

## GUI follow-up fixes

- Opening a CSV requires an explicit dataset selection; the first row (including the sample's DSNO 1 placeholder) is no longer selected automatically. Filtering never substitutes a different dataset. Operations observes both selection changes and DSNO edits, including selection already present when it is constructed.
- Before creating process arguments, selected/manual IDs must resolve uniquely in the saved CSV. Selected rows must belong to the configured CSV and still match the on-disk record. Unsaved edits, missing selections, stale records, and placeholder/non-FITS filenames are rejected.
- Operations uses a bounded options scroller, pinned Run/Stop/status/elapsed/overwrite indicators, and a separate recent-log scroller that follows new output. The top splitter has a minimum height sufficient to keep these controls visible.
- Overwrite is removed from editable JSON. The checkbox supplies both the effective JSON boolean (for functions that accept it) and the launcher flag. The visible ON/OFF indicator and initial run log state the final policy.
- The headless Avalonia regression suite exercises real compiled bindings, Dataset table selection, tab switching, request construction, and layout at 900x650, 1100x760 and 1440x960. It runs without a visible desktop window or observation-data processing.
