using System.Globalization;
using System.Text.Json;
using Avalonia.Media;

namespace Tifres.App.ViewModels;

public sealed record IfuDisplaySettings(bool EllipseEnabled = true, double Width = 6, double Height = 8,
    double CenterX = 4.5, double CenterY = 5.5, double Angle = 0, string Color = "#FF4040",
    bool InvertX = false, bool InvertY = false, double IfuMin = 0, double IfuMax = 119,
    double SpectralMin = -1, double SpectralMax = 1, bool AutoIfu = true, bool AutoSpectral = true,
    string Integration = "Single", string Combination = "Mean", bool AutoSpectrum = true, double SpectrumMin = 0, double SpectrumMax = 1);

public sealed partial class IfuDisplayViewModel : ViewModelBase
{
    private IfuDisplaySettings _applied = new();
    private string _width = "6", _height = "8", _cx = "4.5", _cy = "5.5", _angle = "0", _color = "#FF4040";
    private string _ifuMin = "0", _ifuMax = "119", _spectralMin = "-1", _spectralMax = "1";
    private string _ellipseError = "", _ifuError = "", _spectralError = "", _storageMessage = "";
    private bool _enabled = true, _invertX, _invertY, _restoring;
    public IfuDisplaySettings Applied => _applied;
    public string StoragePath { get; }
    public IReadOnlyList<double> IfuValues => _ifuValues;
    public IReadOnlyList<double> SpectralValues => SpectrumValues;
    public string Width { get => _width; set { if (SetProperty(ref _width, value)) ApplyEllipse(); } }
    public string Height { get => _height; set { if (SetProperty(ref _height, value)) ApplyEllipse(); } }
    public string CenterX { get => _cx; set { if (SetProperty(ref _cx, value)) ApplyEllipse(); } }
    public string CenterY { get => _cy; set { if (SetProperty(ref _cy, value)) ApplyEllipse(); } }
    public string Angle { get => _angle; set { if (SetProperty(ref _angle, value)) ApplyEllipse(); } }
    public string LineColor { get => _color; set { if (SetProperty(ref _color, value)) ApplyEllipse(); } }
    public bool EllipseEnabled { get => _enabled; set { if (SetProperty(ref _enabled, value)) Commit(_applied with { EllipseEnabled = value }); } }
    public bool InvertX { get => _invertX; set { if (SetProperty(ref _invertX, value)) Commit(_applied with { InvertX = value }); } }
    public bool InvertY { get => _invertY; set { if (SetProperty(ref _invertY, value)) Commit(_applied with { InvertY = value }); } }
    public string IfuMin { get => _ifuMin; set { if (SetProperty(ref _ifuMin, value)) ApplyRanges(false); } }
    public string IfuMax { get => _ifuMax; set { if (SetProperty(ref _ifuMax, value)) ApplyRanges(false); } }
    public string SpectralMin { get => _spectralMin; set { if (SetProperty(ref _spectralMin, value)) ApplyRanges(true); } }
    public string SpectralMax { get => _spectralMax; set { if (SetProperty(ref _spectralMax, value)) ApplyRanges(true); } }
    public string EllipseError { get => _ellipseError; private set => SetProperty(ref _ellipseError, value); }
    public string IfuRangeError { get => _ifuError; private set => SetProperty(ref _ifuError, value); }
    public string SpectralRangeError { get => _spectralError; private set => SetProperty(ref _spectralError, value); }
    public string StorageMessage { get => _storageMessage; private set => SetProperty(ref _storageMessage, value); }
    public int? SelectedFiber { get => SelectedFibers.Count == 0 ? null : SelectedFibers.First(); set { if(value is int id)SelectFiber(id,false);else ClearSelection(); } }
    public string SelectionText => SelectedFibers.Count == 0 ? "No fibers selected" : "Fibers: " + string.Join(", ",SelectedFibers.Order());
    public IfuDisplayViewModel(string storagePath)
    {
        StoragePath = storagePath;
        try
        {
            if (!File.Exists(storagePath)) return;
            var json = File.ReadAllText(storagePath);
            using var document = JsonDocument.Parse(json);
            var saved = JsonSerializer.Deserialize<IfuDisplaySettings>(json) ?? throw new InvalidDataException("Empty display settings.");
            // Previous versions stored manual limits without auto/manual flags.
            if (!document.RootElement.TryGetProperty("AutoIfu", out _)) saved = saved with { AutoIfu = false };
            if (!document.RootElement.TryGetProperty("AutoSpectral", out _)) saved = saved with { AutoSpectral = false };
            _restoring = true;
            Width = Format(saved.Width); Height = Format(saved.Height); CenterX = Format(saved.CenterX); CenterY = Format(saved.CenterY);
            Angle = Format(saved.Angle); LineColor = saved.Color;
            InvertX = saved.InvertX; InvertY = saved.InvertY; EllipseEnabled = saved.EllipseEnabled;
            IfuMin = Format(saved.IfuMin); IfuMax = Format(saved.IfuMax); SpectralMin = Format(saved.SpectralMin); SpectralMax = Format(saved.SpectralMax);
            ApplyEllipse(); ApplyRanges(false); ApplyRanges(true);
            _applied = _applied with { AutoIfu=saved.AutoIfu, AutoSpectral=saved.AutoSpectral,
                Integration=IntegrationModes.Contains(saved.Integration)?saved.Integration:"Single",
                Combination=CombinationModes.Contains(saved.Combination)?saved.Combination:"Mean",
                AutoSpectrum=saved.AutoSpectrum, SpectrumMin=saved.SpectrumMin, SpectrumMax=saved.SpectrumMax };
            if(!double.IsFinite(saved.SpectrumMin)||!double.IsFinite(saved.SpectrumMax)||saved.SpectrumMin>=saved.SpectrumMax)
            { _applied=_applied with { SpectrumMin=0,SpectrumMax=1,AutoSpectrum=true }; SpectrumError="Invalid saved spectrum range; using automatic range."; }
            _spectrumMin=Format(_applied.SpectrumMin); _spectrumMax=Format(_applied.SpectrumMax);
        }
        catch (Exception ex) { StorageMessage = "Cannot restore display settings: " + ex.Message; }
        finally { _restoring = false; }
    }
    private static string Format(double value) => value.ToString("G17", CultureInfo.InvariantCulture);
    private static bool Number(string text, out double value) => double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out value) && double.IsFinite(value);
    private void ApplyEllipse()
    {
        if (!Number(Width, out var width) || !Number(Height, out var height) || width <= 0 || height <= 0 ||
            !Number(CenterX, out var cx) || !Number(CenterY, out var cy) || !Number(Angle, out var angle) || !Color.TryParse(LineColor, out _))
        { EllipseError = "Use finite numbers, positive full axis lengths and a valid color (#RRGGBB or name). Last valid ellipse retained."; return; }
        EllipseError = "";
        Commit(_applied with { Width = width, Height = height, CenterX = cx, CenterY = cy, Angle = angle, Color = LineColor });
    }
    private void ApplyRanges(bool spectral)
    {
        var valid = Number(spectral ? SpectralMin : IfuMin, out var min) && Number(spectral ? SpectralMax : IfuMax, out _);
        Number(spectral ? SpectralMax : IfuMax, out var max);
        if (!valid || min >= max)
        {
            var error = "Enter finite Min < Max. Last valid range retained.";
            if (spectral) SpectralRangeError = error; else IfuRangeError = error;
            return;
        }
        if (spectral) SpectralRangeError = ""; else IfuRangeError = "";
        Commit(spectral ? _applied with { SpectralMin = min, SpectralMax = max, AutoSpectral = false } : _applied with { IfuMin = min, IfuMax = max, AutoIfu = false });
    }
    private void Commit(IfuDisplaySettings settings)
    {
        if (_applied == settings) return;
        _applied = settings; OnPropertyChanged(nameof(Applied)); OnPropertyChanged(nameof(AutoIfu)); OnPropertyChanged(nameof(AutoSpectral));
        if (_restoring) return;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(StoragePath)!);
            var temp = StoragePath + ".tmp";
            File.WriteAllText(temp, JsonSerializer.Serialize(_applied, new JsonSerializerOptions { WriteIndented = true }));
            File.Move(temp, StoragePath, true); StorageMessage = "";
        }
        catch (Exception ex) { StorageMessage = "Cannot save display settings: " + ex.Message; }
    }
}
