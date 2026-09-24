# Quick Look implementation and validation

Implemented directly in C:/work/TIFRES after verifying the working directory and TIFRES.sln. The existing application was extended, not regenerated. Dataset, Settings, Operations, status inspection and the FITS viewer remain available.

## Workflow

1. Select a saved representative Dataset, then open Quick Look and choose New Preset.
2. Review calibration references and the expandable preset/options editor, name the preset, and Save Preset.
3. Select raw FITS (or enter ORIGIN), and review/edit DSNO, DATATYPE and FILENAME.
4. Preview Registration: review all matched files, inferred headers, the proposed row, calibration checks and reuse/run decisions.
5. Check the review confirmation, then Reduce & Open.

Only mkSpFrames4f → mkFibSpec4d → mkWcalSpec4d → viewer runs. Calibration generation is never added automatically.

Run/Stop, status, elapsed time, progress and logs remain outside the scrolling form. Dataset/Settings editing and manual Operations execution are blocked while Quick Look runs. Application close stops either workflow and waits asynchronously.

## Session presets

Presets are stored separately in session-presets.json alongside settings.json:
- Windows: %LOCALAPPDATA%/TIFRES/session-presets.json.
- Other platforms: the existing LocalApplicationData settings directory.

The atomically replaced JSON array stores an independent ID, name, string-valued fixed CSV fields, per-step JSON options, default DATATYPE, notes and source DSNO. Presets do not enter the CSV until registration. New, Save, Duplicate and confirmed Delete are implemented.

New copies the selected saved Dataset's fixed fields; without a selection these are empty and require explicit input. Options initialize from existing application/last-used options. Positive FIBINTWID must come from the selected row or explicit input and controls both extraction and wavelength calibration. mkFibFit4c options including finterval are retained but never executed here.

Shared fields: DARKFRAME, WLFLAT, WLFLAT2, SKYFLAT, WAVMAP, FIBINTWID, FIBX0, FIBX1, FIBXWID, YFIBRANGE, NFIBXY, IFIBIACT and WAVSHIFT. Detailed observation editing remains in Dataset.

## Proposals and CSV safety

DSNO: extend only an observed nine-digit YYMMDD plus three-digit sequence for the same observing date and DATATYPE. Propose maximum suffix plus one, rejecting duplicates/overflow. Without a reliable series, require explicit input. IDs remain strings, including identifiers beyond floating-point precision.

ORIGIN: retain the directory relative to configured Raw CCD directory. Common numeric exposure suffixes produce prefix_*.fits (preserving extension case); one file uses its exact relative filename. Other safe names use legacy brace alternatives. Multi-directory selections require manual ORIGIN. Evaluate every proposal with the existing raw_matches semantics, show the complete matched list and warn if it differs from the selection. All registrations require explicit confirmation.

FILENAME: propose prefix_*.fits → prefix.sp.fits only when that transformation is evidenced in the loaded CSV. Otherwise require explicit input. Proposals remain editable and appear in the preview.

Headers: show common observation date, OBJECT information, DATATYPE, exposure and CCD temperature when available. Copy only compatible schema fields. Conflicts are displayed and not inferred; user-entered DSNO/DATATYPE/FILENAME are retained. Timestamp fields needing legacy conversion stay unset until reduction computes them.

Registration uses the existing DatasetCsv validator and timestamped-backup/temporary-file/verified-replacement save. It preserves all columns (98 in the supplied schema), existing strings, separators and empty missing values. Duplicate IDs, unsafe filenames, another dataset's FILENAME and names reserved by calibration references are rejected. Recheck the CSV and raw list/file size/mtime before registration; changed settings/form require a new preview. Registration respects the launcher's CSV lock.

## Calibration checks, reuse and execution

Preflight uses the existing dependency contract and structural FITS validator:
- DARKFRAME frame.
- WLFLAT-derived fiber trace.
- WLFLAT width-specific fiber spectrum, unless flgNoWLflat is enabled.
- Actual WAVMAP reference using exactly the existing width substitution.
- SKYFLAT width-specific fiber spectrum when configured.
- Raw FITS, configured paths, required CSV fields and legacy option names/types/ranges.

An unrelated missing flat wavelength map is not a dependency. All mandatory calibrations are checked before registration; missing calibrations are not generated.

Complete, structurally valid science output sets are reused by default, independently of Operations overwrite. SpFrames includes both frames, Fiber Spec its spectrum, and Wcal Spec the selected dataset's calibrated spectrum and image. Partial/invalid sets block unless Force regenerate Quick Look products is explicitly enabled. Force defaults OFF and grants staged overwrite permission to this workflow's science outputs.

The existing asynchronous ReductionProcess and process-tree cancellation infrastructure runs each step sequentially. Failure/cancellation stops remaining steps and auto-open, and cannot become success. Valid completed products remain. A row registered before later failure/cancellation is retained; retry that DSNO through Operations.

The launcher adds an opt-in --quick-look publication policy. The legacy Wcal function may calculate a SKYFLAT wc side product in staging: Quick Look verifies it but excludes it from publication and published-product provenance. Existing calibration FITS are not replaced. Manual launcher behavior is unchanged.

PNG filenames and script/DSNO subdirectories keep legacy behavior inside a new GUID directory per run:
- Configured PNG root: <PNG root>/quick-look/<run-id>/.
- If unset: <FITS output>/quick-look-png/quick-look/<run-id>/.

Failure/cancellation retains .tifres-runs/<run-id> and reports recovery paths. If interrupted during publication, the existing journal, prepared files and previous-product copies remain recoverable. Quick Look deletes no observation products.

## Viewer and next dataset

Use the exact calibrated contract output and verify it against successful launcher-reported paths. Reused products use the same contract. Normally open <FILENAME without .fits>.w<fibintwid>wc.fits.

Prefer the optional documented dcb companion only if the viewer accepts its 3D layout and its calibrated samples, wavelengths and original active fiber IDs exactly match the wc product. Stale/invalid/unrelated cubes cannot substitute for it.

Viewer failure is reported separately while reduction remains completed. After completion retain the selected preset, calibrations and DATATYPE; clear raw/FILENAME/preview inputs and propose the next DSNO.

## Validation results

No real observation reduction was executed.

| Check | Result |
|---|---|
| dotnet build TIFRES.sln | Passed; 0 warnings, 0 errors |
| Headless GUI regressions | 343 checks passed |
| CSV regressions | 18 checks passed |
| Process/reduction regressions | 34 checks passed |
| Complete Python unittest discovery | 74 tests passed |
| Final focused Quick Look Python suite | 11 tests passed |
| Release win-x64 self-contained publish | Passed |
| Relocated package startup/import/viewer/status smoke | Passed |
| Protected data/legacy SHA-256 comparison | 456/456 unchanged |

New tests cover preset CRUD/confirmation, 98-column registration, large exact DSNOs, proposals/ambiguity, missing calibrations, reuse/Force, exact order, every step's failure/cancellation, actual mock three-step execution and synthetic FITS viewer loading, preset retention/next DSNO, and an actual Python child interrupted during extraction. Stop returns immediately, kills the child, prevents partial publication, preserves existing science/calibration FITS, and reports retained staging.

The legacy integrity test initially failed under Python 3.12 because its AST adds empty type_params fields absent from the Python 3.10 baseline. The test now removes only empty fields before hashing. All five original reference hashes match; neither the baseline hashes nor scientific source were changed.

The existing GUI suite regenerated docs/step6-synthetic-viewer.png from synthetic data. This documentation image is not an observation PNG. Logs and preservation results are under artifacts/quicklook-*.

Updated package:
- Directory: C:/work/TIFRES/artifacts/windows/TIFRES-win-x64
- ZIP: C:/work/TIFRES/artifacts/windows/TIFRES-win-x64.zip
- ZIP SHA-256: 3EC4329ADA69D7AB0062E6066D9186EFB305CCDF12CFB9C32F40151FC37D7923

Relocated startup test:
C:/Users/mkagi/AppData/Local/Temp/TIFRES distribution test d5cdf808186a49b1b36583b05c48f1e4/TIFRES-win-x64

The smoke test verified bundled Quick Look imports and existing viewer/status/settings using synthetic files. Python and the existing documented scientific packages remain separately installed/configurable.

## Remaining limitations

- Unreliable new-date/type DSNO or filename convention requires manual entry.
- Multi-directory selections require manually reviewed ORIGIN.
- Reuse is structural validation, not a scientific-quality/freshness guarantee.
- Failed runs retain registration; use Operations to retry that existing DSNO.
- SKYFLAT wc side products remain staged. The unchanged manual status inspector may still show that secondary product missing if none existed; the Quick Look science result does not require publishing it.
- The viewer retains its documented 10 × 12 mapping restrictions.
- Runtime validation was on Windows. Existing Linux-compatible paths and process termination are reused; no Linux host was available for execution testing.

## Added or modified files

Application:
- src/Tifres.App/Models/SessionPreset.cs — new preset model/store.
- src/Tifres.App/Services/QuickLook.cs — proposals, registration, inspection, sequence.
- src/Tifres.App/ViewModels/QuickLookViewModel.cs — workflow state/commands.
- src/Tifres.App/Views/QuickLookView.axaml — compact tab.
- src/Tifres.App/Views/QuickLookView.axaml.cs — picker/deletion dialog.
- src/Tifres.App/ViewModels/MainWindowViewModel.cs — shared viewer/busy integration.
- src/Tifres.App/ViewModels/OperationsViewModel.cs — external busy guard; reusable defaults.
- src/Tifres.App/ViewModels/OperationsStatus.cs — inspection overlap guard.
- src/Tifres.App/Views/MainWindow.axaml — appended Quick Look tab.
- src/Tifres.App/Views/MainWindow.axaml.cs — close/Stop integration.
- src/Tifres.App/Tifres.App.csproj — bundle backend.

Python and tests:
- python/tifres_quicklook.py — new read-only inspection/planning/viewer backend.
- python/tifres_launcher.py — opt-in safe publication policy.
- python/tests/test_quicklook.py — synthetic backend regressions.
- python/tests/quicklook_fixture.py — GUI fixtures/mock callables.
- python/tests/test_png_and_publication.py — Python 3.12 test compatibility.
- tests/Tifres.Gui.Tests/QuickLookRegression.cs — GUI/service/process regressions.
- tests/Tifres.Gui.Tests/Program.cs — run new regressions.

Packaging/documentation:
- scripts/publish-win.ps1 — require bundled Quick Look module.
- scripts/deployment-smoke.py — verify installed backend import.
- docs/quick-look.md — this report.
- docs/step6-synthetic-viewer.png — regenerated by existing synthetic GUI test.

Legacy Python files modified: none.
Scientific algorithms and observation FITS/PNG/CSV files modified: none.
