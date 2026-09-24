# TIFRES Windows x64 distribution

## Installation
Extract the whole ZIP into a user-writable folder on Windows 10/11 x64.
Keep Tifres.App.exe, all DLLs and python/ together. Start Tifres.App.exe.
The .NET runtime is included; no .NET SDK/runtime installation is required.
Do not copy settings.json from the development PC.

Python is not bundled. Install CPython 3.10 x64 and run PowerShell from
the extracted TIFRES-win-x64 folder:

    py -3.10 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv\Scripts\python.exe -m pip check

requirements.txt pins the verified Windows/CPython 3.10 dependency closure.
NumPy, SciPy, Pandas, Matplotlib and Astropy serve the five GUI steps, viewer
and status inspector. Astroquery serves the standalone JPL utility.
Internet access is needed for Python package installation. No Anaconda is
copied or required. The application does not download packages on startup.

## First-run Settings
- Python executable: browse to this installation's .venv\Scripts\python.exe.
- Python script directory: defaults to python\legacy beside the EXE.
- Dataset CSV: choose your own dataset CSV.
- Raw CCD directory: choose your own observation inputs.
- FITS output directory: choose a writable product directory.
- PNG output directory: choose a writable plot directory.
Save Settings, Open CSV in Dataset, and explicitly select a dataset.

Settings remain per user in %LOCALAPPDATA%\TIFRES and are not shipped.
If an earlier installation left a stale script path, browse to this
installation's python\legacy. When moving an already configured install,
update explicit Python/script paths in Settings. Fresh settings derive
scripts from the EXE location, independently of the working directory.

The distribution cfg.py uses portable defaults. The launcher overrides
CSV/raw/FITS/current/PNG paths in memory. Original cfg.py and numerical
algorithms are unchanged. With no PNG override, the distribution defaults
to %LOCALAPPDATA%\TIFRES\png.

No observation FITS, raw CCD, PNG products, actual CSV, run history,
developer settings, Python interpreter or virtual environment is included.
python\legacy\psg contains static solar/transmission reference text tables;
these are required resources, not observation products.

## Scope and optional legacy dependencies
The five GUI reductions, FITS viewer, status inspector and CSV editor are
packaged. Installing or testing the package never runs real reduction.
GUI reduction uses Matplotlib Agg, so Qt is not required. Direct standalone
interactive Qt scripts may need an additional Qt binding.

All supplied legacy .py files are retained. mkMercEmSpm4e.py is outside the
GUI's five-step scope and imports pltLonLatMerc03, which is absent from
this repository. It cannot run independently until that local module and
its dependencies are supplied. No scientific replacement was fabricated.
Additional standalone SPICE/ICam/JPL work requires its user data/services.

## Rebuilding
Install PowerShell 7 and the .NET SDK pinned by global.json:

    pwsh -File <checkout>\scripts\publish-win.ps1
    pwsh -File <checkout>\scripts\publish-win.ps1 -Force

Outputs: artifacts\windows\TIFRES-win-x64 and TIFRES-win-x64.zip.
Locked NuGet restore uses packaging/packages.win-x64.lock.json, separate from the ordinary development-build lock. Publishing is Release,
win-x64, self-contained, untrimmed and not single-file.
Only explicit Python and reference-resource inputs are copied.
manifest.json records SHA-256 for every payload file. ZIP entries are
sorted and timestamped consistently. Reproducibility assumes unchanged
inputs, pinned SDK and the same PowerShell/compression runtime.
-Force replaces only the generated distribution and ZIP.
The package is unsigned; signing remains a deployment responsibility.

## Reproducible package smoke test
From the source checkout, run:

    pwsh -File scripts/test-win-package.ps1 -Python <python.exe>

This extracts the ZIP into a unique system temporary directory outside
that checkout, verifies all manifest hashes and excludes observation files,
imports all five legacy functions without executing them, creates synthetic
FITS/CSV inputs, and launches the packaged EXE with an isolated settings
file and a deliberately invalid DOTNET_ROOT. It checks the bundled runtime,
viewer integration and status inspector, then exits. A JSON report and the
temporary directory are retained. No user settings or observation products
are accessed. The EXE's --deployment-smoke-test diagnostic is opt-in and is
not used during normal startup.
