using System.Diagnostics;
using System.Text.Json;
using Avalonia.Controls;
using Avalonia.Threading;
using Tifres.App.Models;
using Tifres.App.Services;
using Tifres.App.ViewModels;
using Tifres.App.Views;
using Workflow=Tifres.App.Services.QuickLook;

internal static class QuickLookRegression
{
    private static void Reject(Action action,Action<bool,string> check,string message)
    {try{action();}catch(Exception ex) when(ex is InvalidOperationException or InvalidDataException){check(true,message);return;}throw new Exception("Expected rejection: "+message);}
    private static void Pump(Task task)
    {
        var clock=Stopwatch.StartNew();
        while(!task.IsCompleted){Dispatcher.UIThread.RunJobs();Thread.Sleep(10);if(clock.Elapsed.TotalSeconds>90)throw new TimeoutException("Quick Look GUI test timed out.");}
        Dispatcher.UIThread.RunJobs();task.GetAwaiter().GetResult();
    }
    public static void Run(string directory,Action<bool,string> check)
    {
        var root=Path.Combine(directory,"quick-look");Directory.CreateDirectory(root);
        var columns=new[]{"DSNO","DATATYPE","FILENAME","ORIGIN","NOTE","DARKFRAME","WLFLAT","SKYFLAT","WAVMAP","FIBINTWID","WAVSHIFT","CCDTEMP","EXPTIME","EXPSTART","EXPSTOP","NFILES","EXPMID","FMSTD","NFIBXY","IFIBIACT"}
            .Concat(Enumerable.Range(0,78).Select(i=>"UNKNOWN"+i)).ToArray();
        var existing=columns.Select(_=>"").ToArray();
        var values=new Dictionary<string,string>{{"DSNO","260914111"},{"DATATYPE","SKY"},{"FILENAME","old.sp.fits"},{"ORIGIN","old_*.fits"},
            {"DARKFRAME","dark.sp.fits"},{"WLFLAT","flat.sp.fits"},{"SKYFLAT","sky.sp.fits"},{"WAVMAP","cal.wmp.fits"},{"FIBINTWID","5"},{"UNKNOWN0","keep, \"quoted\"\nstring"}};
        for(int i=0;i<columns.Length;i++)existing[i]=values.GetValueOrDefault(columns[i],"");
        var csv=new DatasetCsv(columns,[existing]);var path=Path.Combine(root,"dataset.csv");csv.Save(path);
        check(columns.Length==98,"Quick Look fixture uses 98-column schema");
        check(Workflow.ProposeDsno(csv,"2026-09-14","SKY")=="260914112","DSNO extends only observed date/type series");
        check(Workflow.ProposeDsno(csv,"2026-09-15","SKY")=="","Unknown observing-date series requires manual DSNO");
        check(Workflow.ProposeDsno(csv,"2026-09-14","VENUS")=="","Unknown type series requires manual DSNO");
        check(Workflow.ProposeFilename(csv,"new_*.fits")=="new.sp.fits","FILENAME proposal uses evidenced CSV convention");
        check(Workflow.ProposeFilename(csv,"odd.fits")=="","Ambiguous FILENAME requires explicit entry");
        var row=Workflow.Row(csv,new(values){["DSNO"]="900719925474099312345",["FILENAME"]="large.sp.fits",["ORIGIN"]="new_*.fits"});
        var backup=Workflow.Register(path,row,File.ReadAllBytes(path));
        var saved=DatasetCsv.Load(path);
        check(File.Exists(backup)&&saved.Columns.SequenceEqual(columns),"Quick Look registration uses existing safe CSV backup and schema");
        check(saved.Rows[0].SequenceEqual(existing),"Registration preserves every unedited value, comma, quote and newline");
        check(saved.Rows[1][0]=="900719925474099312345","Quick Look registration preserves DSNO beyond floating-point precision");
        check(saved.Rows[1][Array.IndexOf(columns,"UNKNOWN1")]=="","Unset new-row values remain empty");
        Reject(()=>Workflow.ValidateRow(saved,new(row){["FILENAME"]="other.sp.fits"}),check,"Duplicate DSNO is rejected before saving");
        Reject(()=>Workflow.ValidateRow(saved,new(row){["DSNO"]="123"}),check,"A FILENAME owned by another dataset is rejected");
        Reject(()=>Workflow.Register(path,new(row){["DSNO"]="123",["FILENAME"]="other.sp.fits"},[1,2]),check,"Stale registration preview cannot replace CSV");
        Reject(()=>Workflow.ValidateRow(saved,new(row){["DSNO"]="123",["FILENAME"]="cal.w5wmp.fits"}),check,"Calibration references anywhere in CSV reserve their products against Quick Look overwrite");
        var settings=new SettingsViewModel(Path.Combine(root,"settings.json")){CsvPath=path};
        var dataset=new DatasetViewModel();dataset.Open(path);dataset.Selected=dataset.FilteredRows.First();
        var vm=new QuickLookViewModel(settings,dataset,()=>false,(_,_)=>Task.FromResult(true));
        vm.NewPreset();vm.Name="Night session";vm.SavePreset();
        var id=vm.SelectedPreset!.Id;
        check(vm.CalibrationSummary.Contains("dark.sp.fits"),"New preset copies calibration references from selected dataset");
        var restored=new SessionPresetStore(vm.StoragePath).Load();
        check(restored.Single().Name=="Night session"&&restored[0].Fields["FIBINTWID"]=="5","Session preset save/load preserves explicit calibration width");
        check(restored[0].Options.ContainsKey("mkFibFit4c"),"Session preset retains finterval options without running calibration");
        vm.DuplicatePreset();check(vm.Presets.Count==2&&vm.SelectedPreset!.Id!=id,"Duplicate preset has independent identity");
        Reject(()=>vm.DeletePreset(false),check,"Preset deletion requires confirmation");
        vm.DeletePreset(true);check(vm.Presets.Count==1&&new SessionPresetStore(vm.StoragePath).Load().Count==1,"Confirmed deletion persists");
        var view=new QuickLookView{DataContext=vm};
        var window=new Window{Content=view,Width=420,Height=500};window.Show();Dispatcher.UIThread.RunJobs();
        check(view.Bounds.Height>0,"Compact Quick Look view lays out at resized dimensions");
        foreach(var size in new[]{(320d,480d),(450d,700d)})
        {
            window.Width=size.Item1;window.Height=size.Item2;Dispatcher.UIThread.RunJobs();
            var run=view.FindControl<Button>("QuickRun")!;var stop=view.FindControl<Button>("QuickStop")!;
            var scroll=view.FindControl<ScrollViewer>("QuickFormScroll")!;
            check(scroll.Viewport.Height>0 && run.Bounds.Height>0 && stop.Bounds.Height>0,"Quick Look form scrolls while Run/Stop retain allocated height at "+size);
        }
        window.Close();
        Task.Run(async()=>
        {
            var plan=new QuickPlan(Workflow.Steps.Select(s=>new QuickStep(s,false,["output"])).ToArray(),"actual-calibrated.fits",[]);
            var order=new List<string>();string? opened=null;
            var result=await Workflow.ExecuteAsync(plan,(s,_)=>{order.Add(s.Step);return Task.FromResult(new ProcessResult(0,false));},
                (p,_)=>{opened=p;return Task.FromResult(true);},(_,_)=>{},CancellationToken.None);
            check(order.SequenceEqual(Workflow.Steps)&&result.Completed,"Quick Look executes SpFrames, Fiber Spec, Wcal Spec in exact order");
            check(opened==plan.Viewer&&result.ViewerState=="Opened","Quick Look auto-opens planned actual calibrated output");
            foreach(var failed in Workflow.Steps)
            {
                order.Clear();opened=null;
                result=await Workflow.ExecuteAsync(plan,(s,_)=>{order.Add(s.Step);return Task.FromResult(new ProcessResult(s.Step==failed?7:0,false));},
                    (p,_)=>{opened=p;return Task.FromResult(true);},(_,_)=>{},CancellationToken.None);
                check(!result.Completed&&order.Last()==failed&&opened==null,"Failure at "+failed+" stops remaining sequence and viewer");
            }
            foreach(var cancelled in Workflow.Steps)
            {
                order.Clear();opened=null;
                result=await Workflow.ExecuteAsync(plan,(s,_)=>{order.Add(s.Step);return Task.FromResult(new ProcessResult(0,s.Step==cancelled));},
                    (p,_)=>{opened=p;return Task.FromResult(true);},(_,_)=>{},CancellationToken.None);
                check(result.Cancelled&&!result.Completed&&order.Last()==cancelled&&opened==null,"Cancellation at "+cancelled+" cannot report success");
            }
            using(var stop=new CancellationTokenSource())
            {
                result=await Workflow.ExecuteAsync(plan,async(s,t)=>{stop.Cancel();await Task.Delay(10,t);return new(0,false);},
                    (_,_)=>Task.FromResult(true),(_,_)=>{},stop.Token);
                check(result.Cancelled,"Quick Look cancellation token interrupts pending step");
            }
            result=await Workflow.ExecuteAsync(plan,(_,_)=>Task.FromResult(new ProcessResult(0,false)),(_,_)=>Task.FromResult(false),(_,_)=>{},CancellationToken.None);
            check(result.Completed&&result.ViewerState=="Load failed","Viewer failure remains separate from successful reduction");
            result=await Workflow.ExecuteAsync(plan,(_,_)=>Task.FromResult(new ProcessResult(0,false)),(_,_)=>throw new IOException("viewer mock"),(_,_)=>{},CancellationToken.None);
            check(result.Completed&&result.ViewerState=="Load failed","Viewer exception preserves completed reduction state");
            var reused=plan with{Steps=plan.Steps.Select(s=>s with{Reuse=true}).ToArray()};
            result=await Workflow.ExecuteAsync(reused,(_,_)=>throw new Exception("Must reuse"),(_,_)=>Task.FromResult(true),(_,_)=>{},CancellationToken.None);
            check(result.Completed,"Valid products skip every reduction even when global overwrite is ON");
        }).GetAwaiter().GetResult();
        // Complete the UI workflow through the real launcher and temporary mock callables.
        var fixture=Path.GetFullPath(Path.Combine(AppContext.BaseDirectory,"../../../../../python/tests/quicklook_fixture.py"));
        var start=ReductionProcess.CreateStartInfo(ReductionRequest.ResolvePython("python"));
        foreach(var arg in new[]{"-B",fixture,root})start.ArgumentList.Add(arg);
        var setup=new ReductionProcess().RunAsync(start,Console.Write,CancellationToken.None).GetAwaiter().GetResult();
        check(setup.ExitCode==0,"Quick Look synthetic raw/calibration and mock callable fixture created");
        settings.ScriptDirectory=Path.Combine(root,"scripts");settings.RawDirectory=Path.Combine(root,"raw");settings.FitsDirectory=Path.Combine(root,"fits");
        var calibration=Path.Combine(settings.FitsDirectory,"sky.sp.w5wc.fits");
        var originalCalibration=File.ReadAllBytes(calibration);
        string? viewerPath=null;
        var display=new IfuDisplayViewModel(Path.Combine(root,"quick-display.json"));
        vm=new QuickLookViewModel(settings,dataset,()=>false,async(p,t)=>
        {
            viewerPath=p;
            await display.LoadAsync(settings.PythonExecutable,p);
            t.ThrowIfCancellationRequested();
            return display.ViewerStatus.StartsWith("Loaded.",StringComparison.Ordinal);
        });
        var presetId=vm.SelectedPreset!.Id;var presetFields=vm.FieldsJson;
        var context=SynchronizationContext.Current;SynchronizationContext.SetSynchronizationContext(new AvaloniaSynchronizationContext());
        try
        {
            Pump(vm.SelectRawAsync([Path.Combine(settings.RawDirectory,"new_0001.fits"),Path.Combine(settings.RawDirectory,"new_0002.fits")]));
            check(vm.Dsno=="260914112"&&vm.Filename=="new.sp.fits"&&vm.Origin=="new_*.fits","Raw selection proposes DSNO, ORIGIN and conventional FILENAME without overwriting input");
            Pump(vm.PreviewAsync());check(vm.Status.StartsWith("Review registration"),"GUI preview verifies all calibrations before registration: "+vm.Status);
            vm.Confirmed=true;Pump(vm.RunAsync());
            check(vm.Status=="Reduction completed · Viewer Opened","GUI Reduce & Open completes mock pipeline: "+vm.Status);
            check(display.Cube!=null&&viewerPath==Path.Combine(settings.FitsDirectory,"new.sp.w5wc.fits"),"GUI automatically selects actual launcher-reported wc product");
            check(vm.SelectedPreset?.Id==presetId&&vm.FieldsJson==presetFields,"Successful Quick Look retains selected preset and calibrations");
            check(vm.Dsno=="260914113"&&vm.Origin==""&&vm.Filename=="","Successful Quick Look clears per-dataset input and proposes next DSNO");
            check(!vm.IsRunning,"Run becomes available after Quick Look completion");
            check(File.ReadAllBytes(calibration).SequenceEqual(originalCalibration),"Quick Look keeps existing calibration FITS byte-identical");
            var registered=DatasetCsv.Load(path);check(registered.Rows.Count==3&&registered.Columns.Length==98,"GUI registration adds exactly one row preserving all 98 columns");
            var validProduct=Path.Combine(settings.FitsDirectory,"new.sp.w5wc.fits");
            var validBytes=File.ReadAllBytes(validProduct);
            var mock=Path.Combine(settings.ScriptDirectory,"mkFibSpec4d.py");
            File.AppendAllText(mock,"""

    import subprocess,sys,time
    child=subprocess.Popen([sys.executable,'-u','-c','import time; time.sleep(300)'])
    Path(cfg.original_path,'quick-child.pid').write_text(str(child.pid))
    Path(cfg.fits_path,row['FILENAME'].replace('.fits','.w5fsp.fits')).write_bytes(b'partial staged product')
    while True:
        print('Quick Look mock still running',flush=True)
        time.sleep(.05)
""");
            vm.Dsno="260914113";vm.Filename="cancel.sp.fits";vm.Origin="new_*.fits";
            Pump(vm.PreviewAsync());check(vm.Status.StartsWith("Review registration"),"Cancellation fixture passes Quick Look preflight");
            vm.Confirmed=true;viewerPath=null;
            var active=vm.RunAsync();var ready=Path.Combine(settings.RawDirectory,"quick-child.pid");
            var waiting=Stopwatch.StartNew();
            while(!File.Exists(ready)&&!active.IsCompleted)
            {
                Dispatcher.UIThread.RunJobs();Thread.Sleep(10);
                if(waiting.Elapsed.TotalSeconds>60)throw new TimeoutException("Quick Look child did not start.");
            }
            check(File.Exists(ready),"Quick Look mock starts a child process inside fiber extraction");
            var childId=int.Parse(File.ReadAllText(ready));
            var response=Stopwatch.StartNew();vm.Stop();
            check(response.ElapsedMilliseconds<250,"Quick Look Stop returns immediately on the GUI thread");
            Pump(active);
            check(vm.Status.StartsWith("Cancelled")&&!vm.IsRunning&&viewerPath==null,"Quick Look Stop prevents later steps and auto-open, then re-enables Run");
            bool childStopped;
            try{using var process=Process.GetProcessById(childId);childStopped=process.HasExited;}catch(ArgumentException){childStopped=true;}
            check(childStopped,"Quick Look terminates its Python child process tree");
            check(!File.Exists(Path.Combine(settings.FitsDirectory,"cancel.sp.w5fsp.fits")),"Cancelled Quick Look cannot publish partially written staged spectrum");
            check(File.ReadAllBytes(validProduct).SequenceEqual(validBytes)&&File.ReadAllBytes(calibration).SequenceEqual(originalCalibration),"Quick Look cancellation preserves previous science and calibration FITS");
            check(vm.Log.Contains("Retained run/recovery directory:"),"Quick Look cancellation reports recoverable staging path");

        }
        finally{display.CloseCube();SynchronizationContext.SetSynchronizationContext(context);}
    }
}
