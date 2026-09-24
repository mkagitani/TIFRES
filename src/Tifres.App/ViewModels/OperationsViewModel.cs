using System.Diagnostics;
using System.ComponentModel;
using Tifres.App.Models;
using System.Windows.Input;
using Avalonia.Threading;
using Tifres.App.Services;

namespace Tifres.App.ViewModels;

public sealed partial class OperationsViewModel : ViewModelBase
{
    public Func<bool>? ExternalBusy { get; set; }
    private readonly SettingsViewModel _settings;
    private readonly DatasetViewModel _dataset;
    private readonly ReductionProcess _process = new();
    private readonly DispatcherTimer _timer;
    private readonly Stopwatch _clock = new();
    private CancellationTokenSource? _cancellation;
    private readonly object _logLock = new();
    private readonly ConsoleLogBuffer _console = new();
    private bool _logDirty;
    private DatasetRow? _observedSelection;
    private string _overwriteState = "Effective overwrite: ON — existing FITS products may be replaced.";
    private string _step = ReductionRequest.Steps[0], _options = "", _dsno = "", _selectedDsno = "No dataset selected";
    private string _status = "Idle", _log = "", _running = "", _elapsed = "00:00:00";
    private bool _busy, _overwrite = true, _useSelected = true;
    public string[] Steps => ReductionRequest.Steps;
    public string Step { get => _step; set { if (SetProperty(ref _step, value)) OptionsJson = _settings.StepOptions.GetValueOrDefault(value, DefaultOptions(value)); } }
    public string OptionsJson
    {
        get => _options;
        set
        {
            // Preserve incomplete JSON while typing; remove the reserved key once valid.
            var valid = false;
            try { value = ReductionRequest.EditableOptions(value); valid = true; }
            catch (System.Text.Json.JsonException) { }
            catch (ArgumentException) { }
            if (SetProperty(ref _options, value)) InvalidateProductStatus();
            if (valid) _settings.StepOptions[Step] = value;
        }
    }
    public string Dsno { get => _dsno; set => SetProperty(ref _dsno, value); }
    public string SelectedDsno { get => _selectedDsno; private set => SetProperty(ref _selectedDsno, value); }
    public bool UseSelected { get => _useSelected; set => SetProperty(ref _useSelected, value); }
    public bool Overwrite
    {
        get => _overwrite;
        set
        {
            if (SetProperty(ref _overwrite, value))
                EffectiveOverwriteState = value
                    ? "Effective overwrite: ON — existing FITS products may be replaced."
                    : "Effective overwrite: OFF — existing FITS products are protected.";
        }
    }
    public string EffectiveOverwriteState { get => _overwriteState; private set => SetProperty(ref _overwriteState, value); }
    public bool IsRunning { get => _busy; private set => SetProperty(ref _busy, value); }
    public string Status { get => _status; private set => SetProperty(ref _status, value); }
    public string Log { get => _log; private set => SetProperty(ref _log, value); }
    public string RunningDescription { get => _running; private set => SetProperty(ref _running, value); }
    public string Elapsed { get => _elapsed; private set => SetProperty(ref _elapsed, value); }
    public ICommand RunCommand { get; }
    public ICommand StopCommand { get; }
    public ICommand UseCsvCommand { get; }
    public OperationsViewModel(SettingsViewModel settings, DatasetViewModel dataset)
    {
        _settings = settings; _dataset = dataset;
        OptionsJson = settings.StepOptions.GetValueOrDefault(Step, DefaultOptions(Step));
        RunCommand = new ActionCommand(async () => await RunAsync());
        StopCommand = new ActionCommand(Stop);
        UseCsvCommand = new ActionCommand(() => { if (!IsRunning) _dataset.Open(_settings.CsvPath); });
        dataset.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(DatasetViewModel.Selected)) ObserveSelection();
            if (e.PropertyName == nameof(DatasetViewModel.FilePath) && File.Exists(dataset.FilePath)) settings.CsvPath = dataset.FilePath;
        };
        ObserveSelection();
        InitializeStatus();
        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(500) };
        _timer.Tick += (_, _) => { FlushLogs(); Elapsed = _clock.Elapsed.ToString(@"hh\:mm\:ss"); };
    }
    private void ObserveSelection()
    {
        InvalidateProductStatus();
        if (_observedSelection != null) _observedSelection.PropertyChanged -= SelectedRowChanged;
        _observedSelection = _dataset.Selected;
        if (_observedSelection != null) _observedSelection.PropertyChanged += SelectedRowChanged;
        SelectedDsno = string.IsNullOrWhiteSpace(_observedSelection?.Dsno) ? "No dataset selected" : _observedSelection.Dsno;
    }
    private void SelectedRowChanged(object? sender, PropertyChangedEventArgs e)
    {
        InvalidateProductStatus();
        if (e.PropertyName == nameof(DatasetRow.Dsno))
            SelectedDsno = string.IsNullOrWhiteSpace(_observedSelection?.Dsno) ? "No dataset selected" : _observedSelection.Dsno;
    }
    public ReductionRequest CreateRequest()
    {
        if (_dataset.IsDirty) throw new InvalidOperationException("Save dataset edits before running a reduction.");
        if (UseSelected && (_dataset.Selected == null || !_dataset.FilteredRows.Contains(_dataset.Selected)))
            throw new InvalidOperationException("Select a dataset in the Dataset tab before running.");
        if (UseSelected && !string.Equals(Path.GetFullPath(_settings.CsvPath), Path.GetFullPath(_dataset.FilePath),
                OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
            throw new InvalidOperationException("The selected dataset belongs to a different CSV. Open the Settings CSV and select it again.");
        var ids = UseSelected ? _dataset.Selected!.Dsno : Dsno;
        var parsed = ReductionRequest.ParseDsno(ids);
        if (UseSelected && parsed.Length != 1) throw new InvalidOperationException("Selected dataset must have exactly one DSNO.");
        var disk = DatasetCsv.Load(_settings.CsvPath);
        var idColumn = Array.IndexOf(disk.Columns, "DSNO");
        var filenameColumn = Array.IndexOf(disk.Columns, "FILENAME");
        foreach (var id in parsed)
        {
            var matches = disk.Rows.Where(r => !disk.IsSeparator(r) && r[idColumn].TrimStart('0') == id.TrimStart('0')).ToArray();
            if (matches.Length != 1) throw new InvalidOperationException($"DSNO {id} is missing or duplicated in the CSV.");
            if (!matches[0][filenameColumn].EndsWith(".fits", StringComparison.Ordinal))
                throw new InvalidOperationException($"DSNO {id} has no valid FITS FILENAME. Select an observation dataset.");
            if (UseSelected && !matches[0].SequenceEqual(_dataset.Selected!.Values))
                throw new InvalidOperationException("The CSV has changed. Reopen it and select the dataset again.");
        }
        var request = new ReductionRequest(_settings.PythonExecutable,
            Path.Combine(AppContext.BaseDirectory, "python", "tifres_launcher.py"), _settings.ScriptDirectory,
            _settings.CsvPath, _settings.RawDirectory, _settings.FitsDirectory, Step, ids, OptionsJson, Overwrite, _settings.PngDirectory, Guid.NewGuid().ToString("N"));
        return request with { OptionsJson = request.EffectiveOptionsJson() };
    }
    public void Stop()
    {
        if (!IsRunning) return;
        Status = "Stopping process tree…";
        _cancellation?.Cancel();
    }
    public async Task RunAsync()
    {
        if (IsRunning || ExternalBusy?.Invoke() == true) return;
        if (IsInspecting)
        {
            _statusCancellation?.Cancel();
            if (_inspection != null) await _inspection;
        }
        if (IsRunning || ExternalBusy?.Invoke() == true) return;
        Log = "";
        lock (_logLock) { _console.Clear(); _logDirty = false; }
        string? recoveryDirectory = null;
        try
        {
            var request = CreateRequest();
            recoveryDirectory = request.RecoveryDirectory;
            var start = request.StartInfo();
            _cancellation = new CancellationTokenSource();
            IsRunning = true; Status = "Validating Python and reduction inputs…";
            RunningDescription = $"{request.Step} · DSNO {request.Dsno}";
            _clock.Restart(); Elapsed = "00:00:00"; _timer.Start();
            AppendLog(EffectiveOverwriteState);
            _settings.Save();
            Action<string> log = QueueLog;
            await _process.VerifyPythonAsync(request.Python, log, _cancellation.Token);
            Status = "Running (launcher validates inputs before processing)…";
            var result = await _process.RunWithOutputAsync(start, chunk => QueueLog(chunk.Text), _cancellation.Token);
            var cancelled = result.Cancelled || _cancellation.IsCancellationRequested || result.ExitCode == 130;
            Status = cancelled ? "Cancelled" : result.ExitCode == 0 ? "Completed" : $"Failed (exit code {result.ExitCode}); see log.";
            if (!cancelled && result.ExitCode == 0 && File.Exists(_dataset.FilePath))
            {
                var selectedId = _dataset.Selected?.Dsno;
                _dataset.Open(_dataset.FilePath);
                _dataset.Selected = _dataset.FilteredRows.FirstOrDefault(r => r.Dsno == selectedId) ?? null;
            }
        }
        catch (OperationCanceledException) { Status = "Cancelled"; }
        catch (Exception ex) { Status = "Failed"; AppendLog(ex.Message); }
        finally
        {
            _timer.Stop(); FlushLogs(); _clock.Stop();
            if (recoveryDirectory != null && Directory.Exists(recoveryDirectory))
                AppendLog($"Retained run files and publication recovery manifest: {recoveryDirectory}");
            Elapsed = _clock.Elapsed.ToString(@"hh\:mm\:ss");
            IsRunning = false; _cancellation?.Dispose(); _cancellation = null;
            await RefreshProductStatusAsync();
        }
    }
    private void QueueLog(string characters)
    {
        lock (_logLock) { _console.Append(characters); _logDirty = true; }
    }
    private void FlushLogs()
    {
        string text;
        lock (_logLock)
        {
            if (!_logDirty) return;
            text = _console.Text; _logDirty = false;
        }
        Log = text;
    }
    private void AppendLog(string message)
    {
        lock (_logLock) { _console.AppendMessage(message); _logDirty = true; }
        FlushLogs();
    }
    public static string DefaultOptions(string step) => step switch
    {
        "mkSpFrames4f" => "{\"overwrite\":true,\"flgPause\":true,\"nxFig\":2,\"nyFig\":5}",
        "mkFibFit4c" => "{\"flgPause\":false,\"finterval\":8}",
        "mkFibSpec4d" => "{\"flgPause\":false,\"flgShowAll\":false,\"fibintwid\":5,\"overwrite\":true}",
        "mkWavMap4d" => "{\"flgPause\":true,\"fibintwid\":5,\"flgNoWLflat\":false,\"fiberCoefDegree\":2}",
        "mkWcalSpec4d" => "{\"flgPlot\":false,\"fibintwid\":5,\"overwrite\":true,\"flgNoWLflat\":false}",
        _ => "{}"
    };
}
