# Compact UI and console formatting

Implemented directly in C:\work\TIFRES after verifying the existing TIFRES.sln. The repository already contained Step 4 changes and newer observation products; those were preserved. No scientific processing was run against observation data.

## Layout

The root now has a 2:1 left/right column ratio and a splitter. Dataset, Settings and Operations occupy the full-height right panel. The left display area has 1:4 columns and 1:1 rows, with independent column and row splitters:

| | Left (1) | Right (4) |
| --- | --- | --- |
| Top (1) | Persistent observation information, selected DSNO, notes and disabled future display-control placeholders | 2D spectrum placeholder; wavelength / IFU-number axes |
| Bottom (1) | Centered IFU placeholder with a uniform 10:12 aspect ratio | 1D spectrum placeholder; wavelength / intensity axes |

The old three-row layout is removed. Minimum dimensions protect controls when the window or splitters are resized; consequently exact ratios may be constrained near minimum panel sizes. No viewer, screenshot handling or keyboard hooks were added.

Shared compact Light styles use 12 px normal text, 11 px table/detail text, 13 px headings, approximately 26 px inputs/buttons, and 3–4 px spacing. The Dataset list and parameter editor scroll independently. Presentation rows pair short fields and allocate full-width rows to paths, filenames, known lists and existing long/comma-separated values. TextBox contents remain complete and horizontally scrollable, with full-value tooltips. All 98 fields remain editable. CSV parsing, serialization, validation and backup code were not changed.

Settings uses six Label | TextBox | Browse rows. JSON persistence and stored paths retain their original behavior. Operations has a bounded options area, pinned Run/Stop/execution state/Refresh controls, a five-row status table, selected-stage details, and an independently scrollable recent log. Calibration relationships and explanations remain available in the details panel. The details/log splitter allows adjusting their heights. Status classification and dependency logic are unchanged.

## Reproduced logging bug and fix

The previous implementation already used StreamReader.ReadAsync, not OutputDataReceived, ErrorDataReceived or ReadLineAsync. However, it split each read on CR/LF and removed those characters. Operations then called AppendLine on every fragment and TrimEnd when flushing. A received chunk was therefore incorrectly treated as a completed line.

A regression using the real GUI append/flush methods reproduced the bug before the fix: three separate dots produced ".\r\n.\r\n.\r\n". The same test now produces "...".

ProcessOutput carries unmodified text plus stdout/stderr identity. Asynchronous reads preserve dots, print(end=''), explicit newlines, blank lines, carriage returns and partial lines. The GUI's bounded ConsoleLogBuffer applies CR as a return to column zero and LF as a line ending, including CRLF split across reads. It does not add a newline per chunk or per dot. Normal application status/recovery messages use a separate append-message method with deliberate line boundaries.

Display changes remain batched on the existing 500 ms timer. The buffer retains roughly 16–20 thousand recent characters and marks earlier output truncation. Stdout and stderr are both displayed, without injecting a repeated stderr label into partial lines. The status inspector consumes separately identified raw streams as well. Existing asynchronous process lifecycle, bounded pipe draining, process-tree termination and staged-output safety are unchanged.

No Python source, progress print statement, algorithm or diagnostic PNG content was changed for this task.

## Validation

| Command | Result |
| --- | --- |
| dotnet build TIFRES.sln | Passed; 0 warnings, 0 errors |
| dotnet run --project tests/Tifres.Gui.Tests | 191 checks passed |
| dotnet run --project tests/Tifres.Reduction.Tests | 34 checks passed |
| dotnet run --project tests/Tifres.Csv.Tests | 18 checks passed |
| python -B -m unittest discover -s python/tests -v | 48 tests passed |
| git diff --check -- src tests docs | Passed |

New tests cover actual rendered proportions, quadrant placement, full-height tabs, splitter keyboard resizing, 900×650 / 1100×760 / 1440×960 layouts, IFU centering and aspect ratio, all five status rows without clipping, independent scroll areas, compact Dataset and Settings controls, notes/selection bindings, all 98 fields, long-value edits and temporary-file persistence. Stream tests cover exact raw stdout/stderr, repeated dots, end='', LF, CR, split CRLF, blank lines, partial text, bounded logs and cancellation while continuously emitting dots without line endings. Existing mock pipeline, cancellation, provenance, dependency and CSV tests still pass.

SHA-256 checks against compact-ui-preservation-before.json verified all 507 pre-existing files under fits/, png/, testdata/ and python/legacy/ unchanged, with no additions or removals. Existing user modifications to FITS/PNG files were not reverted.

## Files changed in this task

Modified:

- src/Tifres.App/App.axaml
- src/Tifres.App/Services/ReductionProcess.cs
- src/Tifres.App/Services/ReductionStatus.cs
- src/Tifres.App/ViewModels/DatasetViewModel.cs
- src/Tifres.App/ViewModels/MainWindowViewModel.cs
- src/Tifres.App/ViewModels/OperationsViewModel.cs
- src/Tifres.App/ViewModels/OperationsStatus.cs
- src/Tifres.App/Views/MainWindow.axaml
- src/Tifres.App/Views/DatasetView.axaml
- src/Tifres.App/Views/SettingsView.axaml
- src/Tifres.App/Views/OperationsView.axaml
- tests/Tifres.Csv.Tests/Tifres.Csv.Tests.csproj
- tests/Tifres.Gui.Tests/Program.cs
- tests/Tifres.Reduction.Tests/Program.cs
- tests/Tifres.Reduction.Tests/CancellationRegression.cs

Added:

- src/Tifres.App/Styles/Compact.axaml
- src/Tifres.App/Services/ConsoleLogBuffer.cs
- src/Tifres.App/ViewModels/ParameterEditorRow.cs
- tests/Tifres.Gui.Tests/CompactLayoutRegression.cs
- tests/Tifres.Gui.Tests/LogFormattingRegression.cs
- tests/Tifres.Reduction.Tests/StreamFormattingRegression.cs
- docs/compact-ui-preservation-before.json
- docs/compact-ui-and-logs.md

## Remaining limitations

The display implements plain text and CR/LF progress behavior, not a full ANSI terminal emulator. The original relative ordering of independently written stdout and stderr cannot be guaranteed across separate OS pipes; order within each stream is preserved. The GUI intentionally keeps a bounded recent log rather than a full-run archive. Long labels/file summaries may use ellipsis at narrow widths, with complete values in tooltips, editable fields or selected-step details. Validation ran on Windows with headless Avalonia layout tests; Linux desktop rendering was not tested here.
