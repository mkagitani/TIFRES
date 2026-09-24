# TIFRES

Tohoku Integral-Field high-Resolution Spectrograph desktop application.
Avalonia MVVM provides dataset CSV editing, five individual Python reduction
steps, read-only dependency/status inspection, and a wavelength-calibrated
FITS viewer. Python/Astropy reads FITS; cached arrays are rendered in Avalonia.

## Windows distribution

See [installation and first-run instructions](packaging/README-Windows.md).

With PowerShell 7 and the SDK pinned by global.json:

    dotnet build TIFRES.sln
    pwsh -File scripts/publish-win.ps1

The self-contained win-x64 Release output and complete ZIP are under
artifacts/windows. Use -Force for a subsequent publish. Python and
observation data are deliberately separate; the package includes verified
requirements.txt, portable Python configuration and static PSG references.

Test the ZIP from a separate temporary directory:

    pwsh -File scripts/test-win-package.ps1 -Python <python.exe>

## Development

    dotnet run --project src/Tifres.App/Tifres.App.csproj

Python dependencies are listed in python/requirements.txt; the verified
Windows dependency closure is pinned in packaging/requirements-win-py310.txt.
Linux development needs a graphical desktop and Avalonia platform libraries.

## Automated tests

    dotnet run --project tests/Tifres.Gui.Tests
    dotnet run --project tests/Tifres.Reduction.Tests
    dotnet run --project tests/Tifres.Csv.Tests
    python -B -m unittest discover -s python/tests -v

Tests use temporary/synthetic inputs. They do not execute real reductions.
See docs/step6-fits-viewer.md for FITS conventions and viewer limitations.
