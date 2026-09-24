using Tifres.App.Services;
namespace Tifres.App.ViewModels;
public sealed partial class IfuDisplayViewModel
{
    private FitsCube? _cube;
    private double[] _ifuValues=Enumerable.Repeat(double.NaN,120).ToArray(), _spectrumValues=[];
    private readonly HashSet<int> _selected=[];
    private string _viewerStatus="Open a calibrated FITS product.", _cursor="", _waveFirst="", _waveLast="", _waveError="";
    private string _spectrumMin="0",_spectrumMax="1",_spectrumError="";
    private double _zoomMin,_zoomMax;
    private bool _loading;
    private int _integrationRevision, _spectrumRevision;
    private (double Min,double Max) _spectrumRange=(0,1);
    private CancellationTokenSource? _loadCancellation, _integrationCancellation, _spectrumCancellation;
    public FitsCube? Cube=>_cube;
    public IReadOnlySet<int> SelectedFibers=>_selected;
    public IReadOnlyList<double> SpectrumValues=>_spectrumValues;
    public string[] IntegrationModes { get; }=["Single","Mean","Sum"];
    public string[] CombinationModes { get; }=["Mean","Sum"];
    public bool IsLoading {get=>_loading;private set=>SetProperty(ref _loading,value);}
    public string ViewerStatus {get=>_viewerStatus;set=>SetProperty(ref _viewerStatus,value);}
    public string CursorText {get=>_cursor;set=>SetProperty(ref _cursor,value);}
    public string Filename=>Cube?.Metadata.Filename??"No FITS loaded";
    public string CubeInfo=>Cube==null?"":$"{Cube.Samples} × 12 × 10 · {Cube.Metadata.Active.Length}/120 active";
    public string WavelengthInfo=>Cube==null?"Wavelength":$"{Cube.Wavelengths[0]:G8} – {Cube.Wavelengths[^1]:G8} ({Cube.Metadata.WavelengthUnit})";
    public string ZoomInfo=>Cube==null?"":$"{ZoomMin:G8} – {ZoomMax:G8} · {Cube.Metadata.WavelengthUnit}";
    public string IntensityInfo=>$"{SpectrumRange.Min:G5} – {SpectrumRange.Max:G5} · {Cube?.Metadata.IntensityUnit??"intensity"}";
    public double ZoomMin=>_zoomMin;
    public double ZoomMax=>_zoomMax;
    public string WaveError {get=>_waveError;private set=>SetProperty(ref _waveError,value);}
    public string WaveFirst {get=>_waveFirst;set{if(SetProperty(ref _waveFirst,value))RefreshIntegration();}}
    public string WaveLast {get=>_waveLast;set{if(SetProperty(ref _waveLast,value))RefreshIntegration();}}
    public double SliderMin=>Cube?.Wavelengths[0]??0;
    public double SliderMax=>Cube?.Wavelengths[^1]??1;
    public double SliderStep=>Cube==null?1:Cube.Wavelengths[1]-Cube.Wavelengths[0];
    public double SliderValue
    {
        get=>Cube!=null && Number(WaveFirst,out var value)?Cube.Wavelengths[Cube.Nearest(value)]:SliderMin;
        set{if(Cube!=null && double.IsFinite(value))WaveFirst=Format(Cube.Wavelengths[Cube.Nearest(value)]);}
    }
    public bool IsInterval => IntegrationMode != "Single";
    public string IntegrationMode {get=>Applied.Integration;set{if(!IntegrationModes.Contains(value))return;Commit(Applied with {Integration=value});OnPropertyChanged(nameof(IntegrationMode));OnPropertyChanged(nameof(IsInterval));RefreshIntegration();}}
    public string CombinationMode {get=>Applied.Combination;set{if(!CombinationModes.Contains(value))return;Commit(Applied with{Combination=value});OnPropertyChanged(nameof(CombinationMode));RefreshSpectrum();}}
    public bool AutoIfu {get=>Applied.AutoIfu;set{Commit(Applied with{AutoIfu=value});if(value)AutoIfuRange();}}
    public bool AutoSpectral {get=>Applied.AutoSpectral;set{Commit(Applied with{AutoSpectral=value});if(value)AutoSpectralRange();}}
    public bool AutoSpectrum {get=>Applied.AutoSpectrum;set{Commit(Applied with{AutoSpectrum=value});OnPropertyChanged(nameof(AutoSpectrum));OnPropertyChanged(nameof(SpectrumValues));OnPropertyChanged(nameof(IntensityInfo));}}
    public string SpectrumMin {get=>_spectrumMin;set{if(SetProperty(ref _spectrumMin,value))ApplySpectrumRange();}}
    public string SpectrumMax {get=>_spectrumMax;set{if(SetProperty(ref _spectrumMax,value))ApplySpectrumRange();}}
    public string SpectrumError {get=>_spectrumError;private set=>SetProperty(ref _spectrumError,value);}
    public (double Min,double Max) SpectrumRange=>AutoSpectrum?_spectrumRange:(Applied.SpectrumMin,Applied.SpectrumMax);
    private static (double Min,double Max) Range(IEnumerable<double> values)
    {
        double min=double.PositiveInfinity,max=double.NegativeInfinity;
        foreach(var v in values)if(double.IsFinite(v)){min=Math.Min(min,v);max=Math.Max(max,v);}
        return FitsCube.Expand(min,max);
    }
    private void ApplySpectrumRange()
    {
        if(!Number(SpectrumMin,out var min)||!Number(SpectrumMax,out var max)||min>=max){SpectrumError="Require finite Min < Max.";return;}
        SpectrumError="";Commit(Applied with{SpectrumMin=min,SpectrumMax=max,AutoSpectrum=false});
        OnPropertyChanged(nameof(AutoSpectrum));OnPropertyChanged(nameof(SpectrumValues));OnPropertyChanged(nameof(IntensityInfo));
    }
    public async Task LoadAsync(string python,string path)
    {
        _loadCancellation?.Cancel();
        using var cancellation=new CancellationTokenSource();
        _loadCancellation=cancellation;IsLoading=true;ViewerStatus="Loading FITS…";
        try
        {
            var cube=await Task.Run(()=>FitsCubeLoader.LoadAsync(python,path,cancellation.Token),cancellation.Token);
            cancellation.Token.ThrowIfCancellationRequested();SetCube(cube);
            ViewerStatus="Loaded. "+string.Join(" ",cube.Metadata.Warnings);
        }
        catch(OperationCanceledException){if(_loadCancellation==cancellation)ViewerStatus="Load cancelled.";}
        catch(Exception ex){if(_loadCancellation==cancellation)ViewerStatus="Open failed: "+ex.Message;}
        finally{if(_loadCancellation==cancellation){_loadCancellation=null;IsLoading=false;}}
    }
    public void CloseCube()
    {
        _loadCancellation?.Cancel();_integrationCancellation?.Cancel();_spectrumCancellation?.Cancel();_integrationRevision++;_spectrumRevision++;_spectrumRange=(0,1);_cube=null;_selected.Clear();_ifuValues=Enumerable.Repeat(double.NaN,120).ToArray();_spectrumValues=[];
        ViewerStatus="Cube closed.";NotifyCube();
    }
    public void SetCube(FitsCube cube)
    {
        _cube=cube;_selected.Clear();_ifuValues=Enumerable.Repeat(double.NaN,120).ToArray();_spectrumValues=[];_spectrumRange=(0,1);CursorText="";
        _waveFirst=Format(cube.Wavelengths[0]);_waveLast=Format(cube.Wavelengths[^1]);
        _zoomMin=cube.Wavelengths[0];_zoomMax=cube.Wavelengths[^1];
        RefreshIntegration();RefreshSpectrum();if(AutoSpectral)AutoSpectralRange();NotifyCube();
    }
    private void NotifyCube()
    {
        foreach(var name in new[]{nameof(Cube),nameof(Filename),nameof(CubeInfo),nameof(WavelengthInfo),nameof(ZoomInfo),
            nameof(IfuValues),nameof(SpectrumValues),nameof(SliderMin),nameof(SliderMax),nameof(SliderStep),nameof(SliderValue),
            nameof(WaveFirst),nameof(WaveLast),nameof(SelectionText),nameof(SelectedFibers),nameof(IntensityInfo)})OnPropertyChanged(name);
    }
    private async void RefreshIntegration()
    {
        _integrationCancellation?.Cancel();
        var revision=++_integrationRevision;
        if(Cube==null)return;
        if(!Number(WaveFirst,out var first)){WaveError="Enter a finite wavelength.";return;}
        double last=first;
        if(IntegrationMode!="Single"&&(!Number(WaveLast,out last)||first>last))
        {WaveError="Enter finite wavelengths with λ1 ≤ λ2.";return;}
        if(IntegrationMode=="Single"){first=Cube.Wavelengths[Cube.Nearest(first)];_waveFirst=Format(first);OnPropertyChanged(nameof(WaveFirst));}
        var cube=Cube;var mode=IntegrationMode;
        using var cancellation=new CancellationTokenSource();_integrationCancellation=cancellation;
        try
        {
            double[] values;
            if(cube.Samples>16384 && mode!="Single")
            {
                await Task.Delay(20,cancellation.Token);
                values=await Task.Run(()=>cube.Integrate(mode,first,last,cancellation.Token),cancellation.Token);
            }
            else values=cube.Integrate(mode,first,last);
            if(revision!=_integrationRevision || Cube!=cube)return;
            _ifuValues=values;
            WaveError=_ifuValues.Any(double.IsFinite)?"":"No valid samples in this selection.";
            OnPropertyChanged(nameof(IfuValues));OnPropertyChanged(nameof(SliderValue));if(AutoIfu)AutoIfuRange();
        }
        catch(OperationCanceledException){}
        finally{if(_integrationCancellation==cancellation)_integrationCancellation=null;}
    }
    private void AutoIfuRange()
    {
        var r=Range(_ifuValues);_ifuMin=Format(r.Min);_ifuMax=Format(r.Max);
        Commit(Applied with{IfuMin=r.Min,IfuMax=r.Max});OnPropertyChanged(nameof(IfuMin));OnPropertyChanged(nameof(IfuMax));IfuRangeError="";
    }
    private void AutoSpectralRange()
    {
        if(Cube==null)return;var r=Cube.Range();_spectralMin=Format(r.Min);_spectralMax=Format(r.Max);
        Commit(Applied with{SpectralMin=r.Min,SpectralMax=r.Max});OnPropertyChanged(nameof(SpectralMin));OnPropertyChanged(nameof(SpectralMax));SpectralRangeError="";
    }
    public void SelectFiber(int fiber,bool toggle)
    {
        if(Cube==null||fiber<0||fiber>=120||!Cube.Selectable[fiber]){CursorText="Inactive or invalid fiber; selection unchanged.";return;}
        if(!toggle)_selected.Clear();if(!_selected.Add(fiber))_selected.Remove(fiber);SelectionChanged();
    }
    public void SelectRectangle(int a,int b,bool add)
    {
        if(Cube==null)return;if(!add)_selected.Clear();
        for(var y=Math.Min(a/10,b/10);y<=Math.Max(a/10,b/10);y++)
            for(var x=Math.Min(a%10,b%10);x<=Math.Max(a%10,b%10);x++)if(Cube.Selectable[y*10+x])_selected.Add(y*10+x);
        SelectionChanged();
    }
    public void SelectFiberRange(int a,int b,bool add)
    {
        if(Cube==null)return;if(!add)_selected.Clear();
        for(var f=Math.Max(0,Math.Min(a,b));f<=Math.Min(119,Math.Max(a,b));f++)if(Cube.Selectable[f])_selected.Add(f);
        SelectionChanged();
    }
    public void ClearSelection(){_selected.Clear();SelectionChanged();}
    private void SelectionChanged(){OnPropertyChanged(nameof(SelectedFibers));OnPropertyChanged(nameof(SelectedFiber));OnPropertyChanged(nameof(SelectionText));RefreshSpectrum();}
    private async void RefreshSpectrum()
    {
        _spectrumCancellation?.Cancel();
        var revision=++_spectrumRevision;var cube=Cube;var ids=_selected.ToArray();var mode=CombinationMode;
        using var cancellation=new CancellationTokenSource();_spectrumCancellation=cancellation;
        try
        {
            double[] values;
            if(cube is {Samples:>16384})
            {
                await Task.Delay(20,cancellation.Token);
                values=await Task.Run(()=>cube.Spectrum(ids,mode,cancellation.Token),cancellation.Token);
            }
            else values=cube?.Spectrum(ids,mode)??[];
            if(revision!=_spectrumRevision || Cube!=cube)return;
            _spectrumValues=values;_spectrumRange=Range(values);OnPropertyChanged(nameof(SpectrumValues));OnPropertyChanged(nameof(IntensityInfo));
        }
        catch(OperationCanceledException){}
        finally{if(_spectrumCancellation==cancellation)_spectrumCancellation=null;}
    }
    public void ResetZoom(){if(Cube!=null){_zoomMin=SliderMin;_zoomMax=SliderMax;ZoomChanged();}}
    public void Zoom(double factor,double fraction)
    {
        if(Cube==null)return;
        var width=Math.Clamp((ZoomMax-ZoomMin)*factor,SliderStep,SliderMax-SliderMin);
        var anchor=ZoomMin+(ZoomMax-ZoomMin)*fraction;
        _zoomMin=Math.Clamp(anchor-width*fraction,SliderMin,SliderMax-width);_zoomMax=_zoomMin+width;ZoomChanged();
    }
    public void Pan(double fraction)
    {
        if(Cube==null)return;var width=ZoomMax-ZoomMin;
        _zoomMin=Math.Clamp(ZoomMin+width*fraction,SliderMin,SliderMax-width);_zoomMax=_zoomMin+width;ZoomChanged();
    }
    private void ZoomChanged(){OnPropertyChanged(nameof(ZoomInfo));OnPropertyChanged(nameof(ZoomMin));OnPropertyChanged(nameof(IntensityInfo));}
}
