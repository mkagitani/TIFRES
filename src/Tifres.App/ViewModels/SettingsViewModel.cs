using System.Text.Json;
using System.Windows.Input;

namespace Tifres.App.ViewModels;

public sealed record ReductionSettings(string PythonExecutable, string ScriptDirectory, string CsvPath, string RawDirectory, string FitsDirectory, string PngDirectory = "", Dictionary<string, string>? StepOptions = null);

public sealed class SettingsViewModel : ViewModelBase
{
    private string _python = OperatingSystem.IsWindows() ? "python" : "python3";
    private string _scripts = Path.Combine(AppContext.BaseDirectory, "python", "legacy");
    private string _csv = "", _raw = "", _fits = "", _png = "", _message = "";
    public string PythonExecutable { get => _python; set => SetProperty(ref _python, value); }
    public string ScriptDirectory { get => _scripts; set => SetProperty(ref _scripts, value); }
    public string CsvPath { get => _csv; set => SetProperty(ref _csv, value); }
    public string RawDirectory { get => _raw; set => SetProperty(ref _raw, value); }
    public string FitsDirectory { get => _fits; set => SetProperty(ref _fits, value); }
    public string PngDirectory { get => _png; set => SetProperty(ref _png, value); }
    public Dictionary<string, string> StepOptions { get; } = new(StringComparer.Ordinal);
    public string Message { get => _message; set => SetProperty(ref _message, value); }
    public ICommand SaveCommand { get; }
    public string StoragePath { get; }
    public SettingsViewModel(string? storagePath = null)
    {
        StoragePath = storagePath ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TIFRES", "settings.json");
        SaveCommand = new ActionCommand(Save);
        try
        {
            if (File.Exists(StoragePath))
            {
                var settings = JsonSerializer.Deserialize<ReductionSettings>(File.ReadAllText(StoragePath)) ?? throw new InvalidDataException("Empty settings file.");
                PythonExecutable = settings.PythonExecutable; ScriptDirectory = settings.ScriptDirectory;
                CsvPath = settings.CsvPath; RawDirectory = settings.RawDirectory; FitsDirectory = settings.FitsDirectory;
                PngDirectory = settings.PngDirectory ?? "";
                if (settings.StepOptions != null)
                    foreach (var pair in settings.StepOptions) StepOptions[pair.Key] = pair.Value;
            }
            Message = $"Settings file: {StoragePath}";
        }
        catch (Exception ex) { Message = $"Could not restore settings: {ex.Message}"; }
    }
    public void Save()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(StoragePath)!);
            var temp = StoragePath + "." + Guid.NewGuid().ToString("N") + ".tmp";
            File.WriteAllText(temp, JsonSerializer.Serialize(new ReductionSettings(PythonExecutable, ScriptDirectory, CsvPath, RawDirectory, FitsDirectory, PngDirectory, StepOptions), new JsonSerializerOptions { WriteIndented = true }));
            File.Move(temp, StoragePath, true);
            Message = $"Settings saved: {StoragePath}";
        }
        catch (Exception ex) { Message = $"Could not save settings: {ex.Message}"; }
    }
}
