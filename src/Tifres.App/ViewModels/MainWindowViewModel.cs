namespace Tifres.App.ViewModels;

public sealed class MainWindowViewModel : ViewModelBase
{
    public DatasetViewModel Dataset { get; } = new();
    public SettingsViewModel Settings { get; }
    public OperationsViewModel Operations { get; }
    public IfuDisplayViewModel Display { get; }
    public QuickLookViewModel QuickLook { get; }
    public bool CanEdit => !Operations.IsRunning && !QuickLook.IsRunning;
    public MainWindowViewModel() : this(new SettingsViewModel()) { }
    public MainWindowViewModel(SettingsViewModel settings)
    {
        Settings = settings;
        Display = new IfuDisplayViewModel(Path.Combine(Path.GetDirectoryName(settings.StoragePath)!, "display-settings.json"));
        Operations = new OperationsViewModel(Settings, Dataset);
        QuickLook = new QuickLookViewModel(Settings, Dataset, () => Operations.IsRunning || Operations.IsInspecting,
            async (path, token) =>
            {
                var product = await Services.QuickLook.InspectAsync<Services.QuickViewer>(Settings.PythonExecutable, new { action = "viewer", wc = path }, token);
                path = product.Path;
                using var registration = token.Register(() => Avalonia.Threading.Dispatcher.UIThread.Post(Display.CloseCube));
                await Display.LoadAsync(Settings.PythonExecutable, path);
                token.ThrowIfCancellationRequested();
                return Display.ViewerStatus.StartsWith("Loaded.", StringComparison.Ordinal) && Display.Filename == path;
            }) { IsViewerLoading = () => Display.IsLoading };
        Operations.ExternalBusy = () => QuickLook.IsRunning;
        QuickLook.PropertyChanged += (_, e) => { if(e.PropertyName == nameof(QuickLook.IsRunning)) OnPropertyChanged(nameof(CanEdit)); };
        Operations.PropertyChanged += (_, e) => { if(e.PropertyName == nameof(Operations.IsRunning)) OnPropertyChanged(nameof(CanEdit)); };
        if (File.Exists(Settings.CsvPath)) Dataset.Open(Settings.CsvPath);
    }
    private string _observationNotes = string.Empty;

    public string Title => "TIFRES";
    public string InstrumentName => "Tohoku Integral-Field high-Resolution Spectrograph";
    public string Status => "No observation loaded";

    // UI state only; acquisition and reduction are intentionally not implemented.
    public string ObservationNotes
    {
        get => _observationNotes;
        set => SetProperty(ref _observationNotes, value);
    }
}
