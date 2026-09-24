# IFU UI completion

Implemented directly in C:/work/TIFRES after verifying TIFRES.sln. This change is UI-only.

## Requirement status

| Requirement | Status |
|---|---|
| Root viewer:right tabs 2:1, right tabs full height | Already implemented; retained and tested |
| Four requested quadrants and horizontal 1:4 ratio | Already implemented; retained and tested |
| Startup top:bottom 4:2; splitter does not override startup | Implemented |
| Equal IFU and 1D spectrum outer heights | Already implemented; retained and measured |
| Independently scrollable persistent panel | Already implemented; compact working controls added |
| Selected DSNO and observation notes | Already implemented; bindings preserved |
| Ellipse enabled, full width/height, center, angle and color | Implemented |
| Separate ellipse overlay, synthetic 10 x 12 image | Implemented |
| X/Y inversion and original fiber selection | Implemented |
| Independent IFU/spectral display ranges and validation | Implemented |
| Display settings persistence | Implemented |
| DSNO/value/selected checkbox row | Implemented |
| Run/Stop/Overwrite checkbox row | Implemented |
| Original Run/Stop commands, overwrite default ON | Already implemented; retained |
| Requested regression coverage | Implemented |

No requested UI functionality remains unimplemented.

## Coordinates and persistence

Synthetic IFU fiber IDs are 0 through 119, with ID = Y * 10 + X.
Centers have X=0..9 and Y=0..11. Positive physical Y points upwards.
Width and height are full ellipse axis lengths. Zero angle aligns width with
positive X; positive angles rotate counterclockwise before display inversion.
The image and overlay use the same transform, including inverse mouse mapping.
The uniform Viewbox preserves the physical aspect ratio when resized.

Valid display changes save immediately in display-settings.json beside the
existing settings.json (normally the local application-data TIFRES directory).
Reduction settings and their schema are unchanged. Invalid numeric ranges,
nonfinite values, nonpositive axes and invalid colors retain the previous
valid display; validation errors appear beside the controls.
Intensity scaling affects rendering only. Synthetic arrays remain unchanged.
Both image previews are explicitly labeled synthetic; no FITS reader was added.

## Validation

- dotnet build TIFRES.sln --no-restore: success, zero warnings/errors.
- dotnet run --project tests/Tifres.Gui.Tests: 243 checks passed.
- dotnet run --project tests/Tifres.Reduction.Tests: 34 checks passed.
- dotnet run --project tests/Tifres.Csv.Tests: 18 checks passed.
- python -B -m unittest discover -s python/tests -v: 52 tests passed.
- Layout measured at 900x650, 1100x760 and 1440x960: top/bottom 2:1,
  equal bottom panel heights, scrollable controls and accessible run/log area.
- All 120 original IDs round-trip under all four inversion combinations at
  two image sizes. Actual headless mouse events verify overlay selection.
- SHA-256 comparison: all 572 protected files unchanged from the pre-task
  snapshot, including observation products, test data, Python files and the
  protected CSV/process/Operations source files.

Only temporary and synthetic test inputs were used. No real reduction ran.
No legacy Python file or scientific algorithm was modified in this task.
Existing unrelated workspace modifications were retained.

## Files changed or added in this task

- src/Tifres.App/ViewModels/ViewModelBase.cs
- src/Tifres.App/ViewModels/MainWindowViewModel.cs
- src/Tifres.App/ViewModels/IfuDisplayViewModel.cs (new)
- src/Tifres.App/Views/MainWindow.axaml
- src/Tifres.App/Views/OperationsView.axaml
- src/Tifres.App/Views/IfuPreview.cs (new)
- tests/Tifres.Gui.Tests/Program.cs
- tests/Tifres.Gui.Tests/CompactLayoutRegression.cs
- tests/Tifres.Gui.Tests/IfuDisplayRegression.cs (new)
- docs/ifu-display-controls.md (new)
- docs/ifu-ui-preservation-before.json (new preservation snapshot)
- docs/ifu-gui-test-results.txt (new test output)
