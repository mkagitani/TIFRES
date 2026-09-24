# Windows distribution validation

## Outputs
- Publish directory: C:/work/TIFRES/artifacts/windows/TIFRES-win-x64
- ZIP: C:/work/TIFRES/artifacts/windows/TIFRES-win-x64.zip
- ZIP SHA-256: 1D683B709B0B372A2097ECEF5E873C71F316E15DED4E49596B98BA65A1B154D1
- 301 payload files, 371,165,662 bytes unpacked.
- ZIP size: 105,559,212 bytes (about 101 MiB).

Run scripts/publish-win.ps1 with PowerShell 7. The script discovers the
checkout relative to its own location and pins SDK 10.0.401 via global.json.
A dedicated Windows NuGet lock prevents normal development restores from
invalidating the distribution's runtime lock. Repeated publication from
identical inputs produced byte-identical ZIP files. The hash above was
checked across two successive publishes.

The package contains a complete self-contained .NET runtime, all supplied
legacy .py scripts, all six launcher/viewer/status/support modules, static
PSG reference text tables, portable cfg.py, requirements.txt, README and
a SHA-256 manifest. cfg.py is replaced only in distribution output; the
repository legacy configuration and scientific functions remain unchanged.
No actual CSV, observation FITS, PNG products, raw files, temporary runs,
PDBs, developer settings or Python/Anaconda interpreter is packaged.

## Verification
- dotnet build TIFRES.sln: success, zero warnings/errors.
- Release win-x64 self-contained publish: success.
- GUI regression checks: 290 passed.
- Process/reduction checks: 34 passed.
- CSV checks: 18 passed.
- Python tests: 63 passed.
- Fresh CPython 3.10 virtual environment: exact pinned requirements installed;
  pip check reported no broken requirements.
- All 557 protected observation/testdata/legacy files retained their hashes.
- No real observation reduction was executed.

The final ZIP was expanded and the native EXE was launched from:
C:\Users\mkagi\AppData\Local\Temp\TIFRES distribution test 287e7c310862434da7300033c99a9bd7\TIFRES-win-x64\

The application's loaded .NET runtime location was:
C:\Users\mkagi\AppData\Local\Temp\TIFRES distribution test 287e7c310862434da7300033c99a9bd7\TIFRES-win-x64\

A separate fresh Python virtual environment outside the checkout was
configured explicitly. Test working directory and settings were also
outside the checkout. DOTNET_ROOT was deliberately set to a nonexistent
path; the EXE correctly used its bundled runtime. The test verified:
- every file against manifest.json;
- package exclusions and absence of checkout/Anaconda strings in Python
  code and the application assembly;
- all package modules imported from the installed package;
- five legacy modules import under the actual noninteractive adapters;
- reference spectra exist at their expected relative paths;
- synthetic FITS binary transfer, viewer integration and selection;
- five-step status inspection and isolated settings persistence.

scripts/test-win-package.ps1 repeats the test. Its Python helper is copied
to the temporary test directory before execution. The opted-in
--deployment-smoke-test startup path uses only supplied temporary inputs.
Normal startup and user Settings are unchanged.

## Remaining deployment dependencies
Users need Windows x64, separately installed CPython 3.10 x64 and the
packages in requirements.txt. No installed .NET runtime or Anaconda is
required. Python/data/output paths remain user-configurable. Installation
of dependencies needs internet access or a separately prepared wheel cache.

Direct interactive legacy execution may need a Qt binding; the GUI uses
Agg and does not. The included but GUI-unsupported mkMercEmSpm4e.py needs
the missing local module pltLonLatMerc03. It was not supplied and no
scientific substitute was introduced. This does not affect the five GUI
steps, viewer or status inspector. The ZIP is unsigned.

## Files changed or added for this task
- scripts/publish-win.ps1
- scripts/test-win-package.ps1
- scripts/deployment-smoke.py
- packaging/cfg.py
- packaging/requirements-win-py310.txt
- packaging/README-Windows.md
- packaging/packages.win-x64.lock.json
- global.json
- src/Tifres.App/packages.lock.json
- src/Tifres.App/Tifres.App.csproj
- src/Tifres.App/App.axaml.cs
- src/Tifres.App/Services/DeploymentSmokeTest.cs
- README.md
- docs/windows-distribution.md

Generated outputs, manifests, smoke reports, dependency-install logs and
test results are under ignored artifacts/. They are not source changes
or observation products.
