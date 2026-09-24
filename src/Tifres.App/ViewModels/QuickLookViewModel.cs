using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows.Input;
using Avalonia.Threading;
using Tifres.App.Models;
using Tifres.App.Services;
using Workflow = Tifres.App.Services.QuickLook;
namespace Tifres.App.ViewModels;

public sealed class QuickLookViewModel : ViewModelBase
{
    private readonly SettingsViewModel settings;
    private readonly DatasetViewModel dataset;
    private readonly Func<bool> externalBusy;
    private readonly Func<string,CancellationToken,Task<bool>> openViewer;
    private readonly SessionPresetStore store;
    private readonly ConsoleLogBuffer console=new();
    private readonly DispatcherTimer timer;
    private readonly Stopwatch overall=new(), stepClock=new();
    private CancellationTokenSource? cancellation;
    private SessionPreset? selected;
    private string name="", fields="{}", sp="{}", fib="{}", wc="{}", interval="", notes="";
    private string dsno="", dataType="", origin="", filename="", status="Select or create a session preset.", preview="", rawSummary="", log="", elapsed="", progress="", observingDate="";
    private string[] selectedFiles=[];
    private Dictionary<string,string> metadata=new();
    private bool busy, force, confirmed;
    private byte[]? previewCsv;
    private string? previewSignature, previewRawFingerprint;
    private QuickPlan? previewPlan;
    public ObservableCollection<SessionPreset> Presets {get;}=[];
    public string StoragePath=>store.Path;
    public Func<bool>? IsViewerLoading {get;set;}
    public SessionPreset? SelectedPreset {get=>selected;set {if(SetProperty(ref selected,value)&&value!=null){Name=value.Name;FieldsJson=JsonSerializer.Serialize(value.Fields,new JsonSerializerOptions{WriteIndented=true});SpOptions=value.Options.GetValueOrDefault(Workflow.Steps[0],"{}");FiberOptions=value.Options.GetValueOrDefault(Workflow.Steps[1],"{}");WcalOptions=value.Options.GetValueOrDefault(Workflow.Steps[2],"{}");Interval=value.Options.GetValueOrDefault("mkFibFit4c","{}");Notes=value.Notes;if(string.IsNullOrWhiteSpace(DataType))DataType=value.DefaultDataType;Confirmed=false;}}}
    public string Name {get=>name;set=>SetProperty(ref name,value);}
    public string FieldsJson {get=>fields;set {SetProperty(ref fields,value);OnPropertyChanged(nameof(CalibrationSummary));}}
    public string CalibrationSummary {get {try {var f=ReadFields();return string.Join("\n",new[]{"DARKFRAME","WLFLAT","SKYFLAT","WAVMAP","FIBINTWID"}.Select(k=>$"{k}: {f.GetValueOrDefault(k,"(unset)")}"));}catch{return "Edit calibration fields as a JSON object of strings.";}}}
    public string SpOptions {get=>sp;set=>SetProperty(ref sp,value);}
    public string FiberOptions {get=>fib;set=>SetProperty(ref fib,value);}
    public string WcalOptions {get=>wc;set=>SetProperty(ref wc,value);}
    public string Interval {get=>interval;set=>SetProperty(ref interval,value);}
    public string Notes {get=>notes;set=>SetProperty(ref notes,value);}
    public string Dsno {get=>dsno;set=>SetProperty(ref dsno,value);}
    public string DataType {get=>dataType;set=>SetProperty(ref dataType,value);}
    public string Origin {get=>origin;set=>SetProperty(ref origin,value);}
    public string Filename {get=>filename;set=>SetProperty(ref filename,value);}
    public string Status {get=>status;set=>SetProperty(ref status,value);}
    public string Preview {get=>preview;private set=>SetProperty(ref preview,value);}
    public string RawSummary {get=>rawSummary;private set=>SetProperty(ref rawSummary,value);}
    public string Log {get=>log;private set=>SetProperty(ref log,value);}
    public string Elapsed {get=>elapsed;private set=>SetProperty(ref elapsed,value);}
    public string Progress {get=>progress;private set=>SetProperty(ref progress,value);}
    public bool IsRunning {get=>busy;private set=>SetProperty(ref busy,value);}
    public bool Force {get=>force;set=>SetProperty(ref force,value);}
    public bool Confirmed {get=>confirmed;set=>SetProperty(ref confirmed,value);}
    public ICommand NewCommand {get;}
    public ICommand SaveCommand {get;}
    public ICommand DuplicateCommand {get;}
    public ICommand PreviewCommand {get;}
    public ICommand RunCommand {get;}
    public ICommand StopCommand {get;}
    public QuickLookViewModel(SettingsViewModel settings,DatasetViewModel dataset,Func<bool> externalBusy,
        Func<string,CancellationToken,Task<bool>> openViewer)
    {
        this.settings=settings;this.dataset=dataset;this.externalBusy=externalBusy;this.openViewer=openViewer;
        store=new(Path.Combine(Path.GetDirectoryName(settings.StoragePath)!,"session-presets.json"));
        try {foreach(var preset in store.Load())Presets.Add(preset);SelectedPreset=Presets.FirstOrDefault();}
        catch(Exception ex){Status="Could not load presets: "+ex.Message;}
        NewCommand=new ActionCommand(()=>Guard(NewPreset));SaveCommand=new ActionCommand(()=>Guard(SavePreset));
        DuplicateCommand=new ActionCommand(()=>Guard(DuplicatePreset));
        PreviewCommand=new ActionCommand(async()=>await PreviewAsync());
        RunCommand=new ActionCommand(async()=>await RunAsync());StopCommand=new ActionCommand(Stop);
        timer=new DispatcherTimer{Interval=TimeSpan.FromMilliseconds(250)};
        timer.Tick+=(_,_)=>{lock(console)Log=console.Text;Elapsed=$"Total {overall.Elapsed:hh\\:mm\\:ss} · step {stepClock.Elapsed:hh\\:mm\\:ss}";};
    }
    private void Guard(Action action){try{if(IsRunning)return;action();}catch(Exception ex){Status=ex.Message;}}
    private Dictionary<string,string> ReadFields() => JsonSerializer.Deserialize<Dictionary<string,string>>(FieldsJson)??throw new InvalidDataException("Preset fields must be a JSON object.");
    private Dictionary<string,string> ReadOptions()
    {
        var f=ReadFields();
        if(!int.TryParse(f.GetValueOrDefault("FIBINTWID"),out var width)||width<=0)throw new InvalidDataException("Set a positive FIBINTWID explicitly or copy it from the selected Dataset.");
        var result=new Dictionary<string,string>();
        foreach(var pair in new[]{(Workflow.Steps[0],SpOptions),(Workflow.Steps[1],FiberOptions),(Workflow.Steps[2],WcalOptions),("mkFibFit4c",Interval)})
        {
            var node=JsonNode.Parse(ReductionRequest.EditableOptions(pair.Item2))!.AsObject();
            if(pair.Item1 is "mkFibSpec4d" or "mkWcalSpec4d")node["fibintwid"]=width;
            result[pair.Item1]=node.ToJsonString();
        }
        return result;
    }
    public void NewPreset()
    {
        var fixedValues=Workflow.FixedFields.ToDictionary(k=>k,_=>"");
        if(dataset.IsDirty)throw new InvalidOperationException("Save Dataset edits before copying a preset.");
        if(dataset.Selected!=null)
            foreach(var field in dataset.Groups.SelectMany(g=>g.Fields))
                if(fixedValues.ContainsKey(field.Name))fixedValues[field.Name]=field.Value;
        var opts=ReductionRequest.Steps.Where(s=>s!="mkWavMap4d").ToDictionary(s=>s,s=>settings.StepOptions.GetValueOrDefault(s,OperationsViewModel.DefaultOptions(s)));
        // These are existing application defaults, except width must come from an explicit preset field.
        var value=new SessionPreset(Guid.NewGuid().ToString("N"),"New session",fixedValues,opts,dataset.Selected?.DataType.Trim()??"",SourceDsno:dataset.Selected?.Dsno??"");
        Presets.Add(value);SelectedPreset=value;Status="Preset copied from selected dataset (or empty). Review fields and Save Preset.";
    }
    public void SavePreset()
    {
        if(string.IsNullOrWhiteSpace(Name))throw new InvalidDataException("Preset name is required.");
        var value=new SessionPreset(SelectedPreset?.Id??Guid.NewGuid().ToString("N"),Name,ReadFields(),ReadOptions(),DataType,Notes,SelectedPreset?.SourceDsno??"");
        var items=Presets.Where(p=>p.Id!=value.Id).Append(value).ToList();store.Save(items);
        if(SelectedPreset!=null)Presets.Remove(SelectedPreset);Presets.Add(value);SelectedPreset=value;
        Status="Session preset saved: "+StoragePath;
    }
    public void DuplicatePreset()
    {
        if(SelectedPreset==null)throw new InvalidOperationException("Select a preset.");
        var value=SelectedPreset with{Id=Guid.NewGuid().ToString("N"),Name=Name+" copy",Fields=ReadFields(),Options=ReadOptions(),Notes=Notes};
        Presets.Add(value);SelectedPreset=value;SavePreset();
    }
    public void DeletePreset(bool confirmation)
    {
        if(SelectedPreset==null)return;
        var items=Presets.ToList();store.Delete(items,SelectedPreset.Id,confirmation);
        Presets.Remove(SelectedPreset);SelectedPreset=Presets.FirstOrDefault();
        if(SelectedPreset==null){Name="";FieldsJson="{}";}
        Status="Preset deleted.";
    }
    private void Begin(string message)
    {
        if(IsRunning||externalBusy()||IsViewerLoading?.Invoke()==true)throw new InvalidOperationException("Wait for the current operation or viewer load.");
        if(dataset.IsDirty)throw new InvalidOperationException("Save Dataset edits first.");
        IsRunning=true;cancellation=new();Status=message;overall.Restart();stepClock.Restart();timer.Start();
    }
    private void End(){timer.Stop();overall.Stop();stepClock.Stop();lock(console)Log=console.Text;IsRunning=false;cancellation?.Dispose();cancellation=null;}
    public void Stop(){if(IsRunning){Status="Stopping process tree…";cancellation?.Cancel();}}
    public async Task SelectRawAsync(string[] paths)
    {
        if(IsRunning)return;
        try {Begin("Inspecting raw FITS…");selectedFiles=paths;var info=await InspectRaw("",cancellation!.Token);ApplyRaw(info);Status="Review inferred metadata and proposed fields; Preview Registration.";}
        catch(OperationCanceledException){Status="Cancelled";}
        catch(Exception ex){Status=ex.Message;}
        finally{if(IsRunning)End();}
    }
    private Task<QuickRaw> InspectRaw(string pattern,CancellationToken token)=>Workflow.InspectAsync<QuickRaw>(settings.PythonExecutable,new{action="raw",raw=settings.RawDirectory,selected=selectedFiles,origin=pattern},token);
    private void ApplyRaw(QuickRaw info)
    {
        Origin=info.Origin;metadata=info.Metadata;observingDate=info.ObservingDate;Confirmed=false;
        if(string.IsNullOrWhiteSpace(DataType)&&metadata.TryGetValue("DATATYPE",out var type))DataType=type;
        var csv=DatasetCsv.Load(settings.CsvPath);
        if(string.IsNullOrWhiteSpace(Dsno))Dsno=Workflow.ProposeDsno(csv,observingDate,DataType);
        if(string.IsNullOrWhiteSpace(Filename))Filename=Workflow.ProposeFilename(csv,Origin);
        RawSummary=$"Raw directory: {settings.RawDirectory}\n{info.Files.Length} matched files · first: {info.Files.FirstOrDefault()} · last: {info.Files.LastOrDefault()}\nDate: {observingDate}\n"+
            string.Join("\n",info.Notes)+"\n"+string.Join("\n",metadata.Select(p=>$"Header: {p.Key} = {p.Value}"))+"\n"+string.Join("\n",info.Files);
    }
    private Dictionary<string,string> BuildRow(DatasetCsv csv)
    {
        if(SelectedPreset==null)throw new InvalidOperationException("Select or create a session preset.");
        var values=ReadFields();
        if(values.Keys.Any(k=>!Workflow.FixedFields.Contains(k)))throw new InvalidDataException("Only the listed session calibration/fixed fields belong in a preset.");
        foreach(var pair in metadata)if(pair.Key!="DATATYPE")values[pair.Key]=pair.Value;
        values["DSNO"]=Dsno.Trim();values["DATATYPE"]=DataType.Trim();values["ORIGIN"]=Origin.Trim();values["FILENAME"]=Filename.Trim();
        values["NOTE"]=Notes;
        var row=Workflow.Row(csv,values);Workflow.ValidateRow(csv,row);return row;
    }
    private string Signature()=>JsonSerializer.Serialize(new{Dsno,DataType,Origin,Filename,FieldsJson,SpOptions,FiberOptions,WcalOptions,Interval,Notes,Force,
        settings.PythonExecutable,settings.ScriptDirectory,settings.CsvPath,settings.RawDirectory,settings.FitsDirectory,settings.PngDirectory});
    private Task<QuickPlan> Plan(Dictionary<string,string> row,CancellationToken token)=>Workflow.InspectAsync<QuickPlan>(settings.PythonExecutable,
        new{action="plan",row,raw=settings.RawDirectory,fits=settings.FitsDirectory,scripts=settings.ScriptDirectory,options=ReadOptions(),force=Force},token);
    public async Task PreviewAsync()
    {
        if(IsRunning)return;
        try
        {
            Begin("Checking raw files, calibration products and registration…");Confirmed=false;previewSignature=null;
            var info=await InspectRaw(Origin,cancellation!.Token);ApplyRaw(info);
            var bytes=File.ReadAllBytes(settings.CsvPath);var csv=DatasetCsv.Load(settings.CsvPath);var row=BuildRow(csv);var plan=await Plan(row,cancellation.Token);
            if(!bytes.SequenceEqual(File.ReadAllBytes(settings.CsvPath)))throw new InvalidOperationException("CSV changed during preview.");
            previewRawFingerprint=info.Fingerprint;previewCsv=bytes;previewPlan=plan;previewSignature=Signature();
            Preview="NEW ROW — "+string.Join("\n",row.Where(p=>!string.IsNullOrEmpty(p.Value)).Select(p=>$"{p.Key}: {p.Value}"))+
                "\n\nCalibration inputs:\n"+string.Join("\n",plan.Calibrations)+"\n\n"+string.Join("\n",plan.Steps.Select(s=>$"{s.Step}: {(s.Reuse?"reuse valid outputs":"run")}"))+
                "\nViewer: "+plan.Viewer+"\nExisting calibration products are protected. PNGs go to a new run directory.";
            Status="Review registration, matched raw list and proposals; check confirmation, then Reduce & Open.";
        }
        catch(OperationCanceledException){Status="Cancelled";}
        catch(Exception ex){Status="Preview blocked: "+ex.Message;Preview="";}
        finally{if(IsRunning)End();}
    }
    public async Task RunAsync()
    {
        if(IsRunning)return;
        string? recovery=null;
        bool registered=false;
        try
        {
            Begin("Rechecking preview…");
            if(!Confirmed||previewSignature!=Signature()||previewCsv==null||previewPlan==null)throw new InvalidOperationException("Preview Registration, review values and confirm before reducing. Changed fields require a new preview.");
            var token=cancellation!.Token;
            var info=await InspectRaw(Origin,token);
            if(info.Fingerprint!=previewRawFingerprint)throw new InvalidDataException("Raw file list or files changed since preview; preview and confirm again.");
            var csv=DatasetCsv.Load(settings.CsvPath);var row=BuildRow(csv);
            var plan=await Plan(row,token);var opts=ReadOptions();
            token.ThrowIfCancellationRequested();
            var backup=Workflow.Register(settings.CsvPath,row,previewCsv);registered=true;Confirmed=false;previewSignature=null;
            lock(console){console.Clear();console.AppendMessage("CSV registered. Backup: "+backup);}
            dataset.Open(settings.CsvPath);dataset.Selected=dataset.FilteredRows.FirstOrDefault(r=>r.Dsno==Dsno);
            var states=Workflow.Steps.Append("Viewer").ToDictionary(s=>s,_=>"Waiting");
            var runningDsno=Dsno;var pngRoot=string.IsNullOrWhiteSpace(settings.PngDirectory)?Path.Combine(settings.FitsDirectory,"quick-look-png"):settings.PngDirectory;
            var png=Path.Combine(pngRoot,"quick-look",Guid.NewGuid().ToString("N"));
            Status="Reducing DSNO "+runningDsno;
            var result=await Workflow.ExecuteAsync(plan,async (step,ct)=>
            {
                var request=new ReductionRequest(settings.PythonExecutable,Path.Combine(AppContext.BaseDirectory,"python","tifres_launcher.py"),settings.ScriptDirectory,
                    settings.CsvPath,settings.RawDirectory,settings.FitsDirectory,step.Step,runningDsno,opts[step.Step],Force,png,Guid.NewGuid().ToString("N"));
                recovery=request.RecoveryDirectory;var start=request.StartInfo();start.ArgumentList.Add("--quick-look");
                var report=new System.Text.StringBuilder();
                var output=await new ReductionProcess().RunWithOutputAsync(start,p=>{lock(console){console.Append(p.Text);if(!p.IsError && report.Length<65536)report.Append(p.Text[..Math.Min(p.Text.Length,65536-report.Length)]);}},ct);
                if(!output.Cancelled && output.ExitCode==0)
                {
                    var line=report.ToString().Split('\n').FirstOrDefault(l=>l.StartsWith("{\"dsno\"",StringComparison.Ordinal));
                    if(line==null)throw new InvalidDataException("Launcher did not report its output paths.");
                    using var json=JsonDocument.Parse(line);
                    var actual=json.RootElement.GetProperty("outputs").EnumerateArray().Select(p=>Path.GetFullPath(Path.Combine(settings.FitsDirectory,p.GetString()!))).ToArray();
                    if(!step.Outputs.All(p=>actual.Contains(Path.GetFullPath(p),OperatingSystem.IsWindows()?StringComparer.OrdinalIgnoreCase:StringComparer.Ordinal)))
                        throw new InvalidDataException("Launcher outputs differ from the reviewed contract.");
                }
                return output;
            },openViewer,(step,state)=>{states[step]=state;Progress="DSNO "+runningDsno+"\n"+string.Join("\n",states.Select(p=>p.Key+": "+p.Value));if(state=="Running")stepClock.Restart();},token);
            Status=result.Cancelled?"Cancelled":result.Completed?"Reduction completed · Viewer "+result.ViewerState:"Failed — remaining steps were not run.";
            dataset.Open(settings.CsvPath);dataset.Selected=dataset.FilteredRows.FirstOrDefault(r=>r.Dsno==runningDsno);
            if(result.Completed)ResetForNext();
        }
        catch(OperationCanceledException){Status="Cancelled";}
        catch(Exception ex){Status="Quick Look blocked/failed: "+ex.Message;}
        finally
        {
            if(recovery!=null&&Directory.Exists(recovery)){lock(console)console.AppendMessage("Retained run/recovery directory: "+recovery);}
            if(registered && !Status.StartsWith("Reduction completed",StringComparison.Ordinal))Status+=" CSV registration retained; inspect/retry this DSNO in Operations.";
            if(IsRunning)End();
        }
    }
    public void ResetForNext()
    {
        Dsno=Workflow.ProposeDsno(DatasetCsv.Load(settings.CsvPath),observingDate,DataType);
        Origin="";Filename="";selectedFiles=[];metadata.Clear();RawSummary="";Preview="";Confirmed=false;previewSignature=null;
    }
}
