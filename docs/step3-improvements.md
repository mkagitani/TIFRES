# Step 3 PNG, options and cancellation improvements

Implemented directly in C:\work\TIFRES after verifying TIFRES.sln. No real reduction was run. SHA-256 verification of all 334 pre-existing files under fits/ and testdata/ found zero changed or missing files, including the successfully reduced observation products and dataset CSV.

## Behavior

- Settings has a PNG output directory and folder browser, persisted in settings.json. Empty means the standalone legacy cfg.png_path, normally python/legacy/png. Script/DSNO subdirectories and PNG filenames are unchanged. PNG overwrite behavior remains independent of FITS permission.
- FITS overwrite starts ON in the GUI. The checkbox remains authoritative for all five steps, including those with internal overwrite=True or no overwrite parameter. OFF rejects existing planned outputs before calculation and uses atomic no-clobber publication.
- GUI mkFibFit4c starts with flgPause=false, finterval=8. The request conflicts: its options section specifies 8, while its validation list says 16. This implementation follows the detailed options section; 1 and 16 are accepted, and a saved 16 is restored. Original Python finterval=1 is unchanged.
- GUI mkWcalSpec4d starts with flgPlot=false; users can enable true. Per-step edited options persist on Save Settings, Run and normal application close. Original Python flgPlot=True is unchanged.
- Process start, waiting, termination and pipe draining execute off the UI thread. Logs are batched every 500 ms and bounded, with explicit truncation notices, so heavy logging cannot flood the dispatcher or force layout of enormous text blocks.
- Windows uses Process.Kill(entireProcessTree: true) plus a kill-on-close Job Object to own descendants even after their parent exits. Linux starts an isolated session through setsid and kills the process group, including reparented descendants. Linux requires util-linux/setsid; this Windows session did not execute Linux runtime tests.
- Stop immediately requests cancellation; UI ends in Cancelled, Failed or Completed and makes Run available again. Cancellation cannot be reported as success. Readers have bounded shutdown waits, including descendants retaining stdout/stderr handles.

## Publication and recovery

Legacy calculations write into a unique FITS_ROOT/.tifres-runs/run-id directory. All expected FITS files must exist and validate before publication. Failed or cancelled generation never publishes these files. Before any destination replacement, publication preserves prior products in .previous and prepares complete replacements in .prepared. Each destination replacement is atomic; the whole group of outputs is not a filesystem transaction.

If stopped during publication, some complete new files may already have been published. The GUI reports the retained run directory containing recovery.json, original products in .previous, generated products, source.csv and staged dataset.csv. The manifest records published paths and a potentially interrupted replacement. Hard termination may leave the manifest at its last phase. No automatic deletion or rollback is attempted; recoverable copies remain available. Successful runs also retain their staging and recovery copies, requiring additional disk space.

## Legacy changes (separate from integration)

Only these scientific-source edits were made:

| File | Reason |
| --- | --- |
| python/legacy/cfg.py | Define standalone png_path from the legacy directory with os.path.join and a trailing separator. Runtime overrides never rewrite cfg.py. |
| python/legacy/mkSpFrames4f.py | Replace 5 PNG root expressions with cfg.png_path. |
| python/legacy/mkFibFit4c.py | Replace 3 PNG root expressions with cfg.png_path. |
| python/legacy/mkFibSpec4d.py | Replace 1 PNG root expression with cfg.png_path. |
| python/legacy/mkWavMap4d.py | Replace 4 PNG root expressions with cfg.png_path. |
| python/legacy/mkWcalSpec4d.py | Replace 1 PNG root expression with cfg.png_path. |

No function default, PNG suffix, plot content or numerical algorithm changed. Regression tests compare normalized AST hashes against the actual pre-edit scripts, allowing only those root substitutions, and evaluate all PNG expressions for standalone/custom roots. This verifies source compatibility without executing scientific processing.

## Validation (Windows)

| Command | Result |
| --- | --- |
| dotnet build TIFRES.sln | Passed, 0 warnings and 0 errors |
| python -B -m unittest discover -s python/tests -v | 23 tests passed |
| dotnet run --project tests/Tifres.Reduction.Tests | 26 checks passed |
| dotnet run --project tests/Tifres.Gui.Tests | 106 headless GUI checks passed |
| dotnet run --project tests/Tifres.Csv.Tests | 18 checks passed |

Coverage includes PNG fallback/override/routing/persistence, standalone defaults, all five steps with overwrite ON/OFF, option persistence, child termination after parent exit, inherited pipes, stdout/stderr flooding, Stop through the GUI command, partial staged writes, preservation of prior FITS and CSV files, publication interruption and recovery copies. Only temporary files and mock processing functions were used. No missing Python dependencies were reported by the test suite. Linux termination is implemented but not runtime-verified here.

## Other modified or added files

- src/Tifres.App/Services/ReductionProcess.cs
- src/Tifres.App/Services/ProcessTree.cs (new)
- src/Tifres.App/ViewModels/OperationsViewModel.cs
- src/Tifres.App/ViewModels/SettingsViewModel.cs
- src/Tifres.App/Views/SettingsView.axaml
- src/Tifres.App/Views/SettingsView.axaml.cs
- src/Tifres.App/Tifres.App.csproj
- python/tifres_launcher.py
- python/tifres_publication.py (new)
- python/tests/test_launcher.py
- python/tests/test_png_and_publication.py (new)
- python/tests/legacy_png_baseline.json (new)
- tests/Tifres.Reduction.Tests/Program.cs
- tests/Tifres.Reduction.Tests/CancellationRegression.cs (new)
- tests/Tifres.Gui.Tests/Program.cs
- tests/Tifres.Gui.Tests/GuiCancellationRegression.cs (new)
- docs/legacy-inventory.json (refreshed)
- docs/step3.md
- docs/step3-improvements.md (this report)
- docs/step3-products-before.json (pre-edit data hashes)
