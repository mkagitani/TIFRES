using System.Collections.ObjectModel;
using System.Windows.Input;
using Tifres.App.Services;

namespace Tifres.App.ViewModels;

public sealed partial class OperationsViewModel
{
    private CancellationTokenSource? _statusCancellation;
    private Task? _inspection;
    private int _statusRevision;
    private bool _isInspecting;
    private string _statusDiagnostics = "";
    public string StatusDiagnostics { get => _statusDiagnostics; private set => SetProperty(ref _statusDiagnostics, value); }
    private string _statusMessage = "Select a dataset and Refresh Status. Inspection never starts reduction.";
    private ProductNode? _selectedProductStatus;
    public ProductNode? SelectedProductStatus { get => _selectedProductStatus; set => SetProperty(ref _selectedProductStatus, value); }
    public ObservableCollection<ProductNode> ProductStatuses { get; } = new();
    public ObservableCollection<ProductNode> CalibrationStatuses { get; } = new();
    public bool IsInspecting { get => _isInspecting; private set => SetProperty(ref _isInspecting, value); }
    public string ProductStatusMessage { get => _statusMessage; private set => SetProperty(ref _statusMessage, value); }
    public ICommand RefreshStatusCommand { get; private set; } = null!;

    private void InitializeStatus()
    {
        RefreshStatusCommand = new ActionCommand(async () => await RefreshProductStatusAsync());
        _settings.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName is nameof(SettingsViewModel.CsvPath) or nameof(SettingsViewModel.RawDirectory)
                or nameof(SettingsViewModel.FitsDirectory) or nameof(SettingsViewModel.ScriptDirectory)
                or nameof(SettingsViewModel.PythonExecutable)) InvalidateProductStatus();
        };
        _dataset.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(DatasetViewModel.IsDirty)) InvalidateProductStatus();
        };
    }

    private void InvalidateProductStatus()
    {
        _statusRevision++;
        _statusCancellation?.Cancel();
        ProductStatuses.Clear(); CalibrationStatuses.Clear(); SelectedProductStatus = null; StatusDiagnostics = "";
        ProductStatusMessage = "Selection, settings or options changed. Refresh Status to inspect saved data.";
    }

    public Task RefreshProductStatusAsync()
    {
        if (IsRunning || IsInspecting || ExternalBusy?.Invoke() == true) return _inspection ?? Task.CompletedTask;
        return _inspection = InspectProductsAsync();
    }

    private async Task InspectProductsAsync()
    {
        var revision = _statusRevision;
        using var cancellation = new CancellationTokenSource();
        _statusCancellation = cancellation;
        IsInspecting = true;
        ProductStatuses.Clear(); CalibrationStatuses.Clear(); SelectedProductStatus = null; StatusDiagnostics = "";
        try
        {
            if (_dataset.IsDirty) throw new InvalidOperationException("Save dataset edits before inspecting product freshness.");
            if (_dataset.Selected == null) throw new InvalidOperationException("Select a dataset in the Dataset tab.");
            if (!string.Equals(Path.GetFullPath(_settings.CsvPath), Path.GetFullPath(_dataset.FilePath),
                    OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
                throw new InvalidOperationException("Open the Settings CSV and select its dataset before inspecting.");
            var options = Steps.ToDictionary(step => step, step => _settings.StepOptions.GetValueOrDefault(step, DefaultOptions(step)));
            options[Step] = OptionsJson; // report malformed edits instead of silently using previous valid options
            ProductStatusMessage = $"Inspecting DSNO {_dataset.Selected.Dsno} (read-only)…";
            var report = await ReductionStatus.InspectAsync(new StatusRequest(_settings.PythonExecutable, _settings.ScriptDirectory,
                _settings.CsvPath, _settings.RawDirectory, _settings.FitsDirectory, _dataset.Selected.Dsno, options), cancellation.Token);
            if (revision != _statusRevision) return;
            foreach (var node in report.Steps) ProductStatuses.Add(node);
            SelectedProductStatus = ProductStatuses.FirstOrDefault(n => n.Step == Step) ?? ProductStatuses.FirstOrDefault();
            var selected = report.Steps.Select(n => n.Id).ToHashSet();
            foreach (var node in report.Nodes.Where(n => !selected.Contains(n.Id))) CalibrationStatuses.Add(node);
            ProductStatusMessage = $"Status inspection completed. {report.Steps.Length} steps inspected. Historical runs: {report.HistoricalRuns}. Warnings: {report.WarningCount}.";
            StatusDiagnostics = $"DSNO {report.Dsno} · inspected {DateTime.Now:T}. Complete means structurally valid with matching provenance; it is not a scientific quality rating.\n" + string.Join("\n", report.Notes.Distinct());

        }
        catch (OperationCanceledException) { if (revision == _statusRevision) ProductStatusMessage = "Status inspection cancelled."; }
        catch (Exception ex) { if (revision == _statusRevision) ProductStatusMessage = "Status unknown: " + ex.Message; }
        finally { IsInspecting = false; if (_statusCancellation == cancellation) _statusCancellation = null; }
    }
}
