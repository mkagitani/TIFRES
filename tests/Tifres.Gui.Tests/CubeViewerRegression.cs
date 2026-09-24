using System.Diagnostics;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Input;
using Avalonia.Threading;
using Tifres.App.Services;
using Tifres.App.ViewModels;
using Tifres.App.Views;

internal static class CubeViewerRegression
{
    public static FitsCube Synthetic()
    {
        var wave=new[]{500.25,500.375,500.5,500.625,500.75,500.875,501.0};
        var data=Enumerable.Range(0,840).Select(i=>(double)i-12.5).ToArray();
        data[2*7+2]=double.NaN;for(int i=0;i<7;i++)data[5*7+i]=double.NaN;
        return new FitsCube(new CubeMetadata(1,[120,7],"float64","little","fiber,wavelength",
            Enumerable.Range(0,120).Where(i=>i!=6).ToArray(),"nm","counts","synthetic.fits",[]),wave,data);
    }
    public static void Run(string directory,Action<bool,string> check)
    {
        var root=Path.Combine(directory,"cube-viewer");Directory.CreateDirectory(root);
        var legacySettings=Path.Combine(root,"legacy-display.json");
        File.WriteAllText(legacySettings, """{"IfuMin":-5,"IfuMax":20,"SpectralMin":-10,"SpectralMax":30}""");
        var migrated=new IfuDisplayViewModel(legacySettings);migrated.SetCube(Synthetic());
        check(!migrated.AutoIfu&&!migrated.AutoSpectral&&migrated.Applied.IfuMin==-5&&migrated.Applied.SpectralMax==30,"Previous-version manual ranges survive loading a real cube");
        var vm=new IfuDisplayViewModel(Path.Combine(root,"display.json"));
        var cube=Synthetic();vm.SetCube(cube);
        check(vm.CubeInfo.Contains("7 × 12 × 10") && vm.IfuValues[97]==666.5,"Loaded cube maps original fiber 97 to X=7,Y=9");
        vm.WaveFirst="500.49";
        check(vm.SliderValue==500.5 && vm.WaveFirst=="500.5" && double.IsNaN(vm.IfuValues[2]),"Single numeric entry snaps to nearest wavelength and preserves invalid samples");
        vm.SliderValue=500.625;
        check(vm.WaveFirst=="500.625" && vm.IfuValues[0]==-9.5,"Slider and numeric wavelength stay synchronized");
        vm.IntegrationMode="Mean";vm.WaveFirst="500.375";vm.WaveLast="500.625";
        check(vm.IfuValues[0]==-10.5 && vm.IfuValues[2]==3.5,"Inclusive Mean ignores NaN samples");
        vm.IntegrationMode="Sum";
        check(vm.IfuValues[0]==-31.5 && vm.IfuValues[2]==7,"Sum is sample sum, not wavelength-weighted integration");
        vm.WaveFirst="800";vm.WaveLast="900";
        check(vm.IfuValues.All(double.IsNaN)&&vm.WaveError.Length>0,"Empty wavelength interval displays no data and an explicit message");
        vm.SelectFiber(1,false);vm.SelectFiber(2,true);
        check(vm.SelectedFibers.SetEquals(new[]{1,2}) && vm.SpectrumValues[2]==-3.5,"Shared multiple selection Mean ignores invalid fiber samples");
        vm.CombinationMode="Sum";
        check(vm.SpectrumValues[0]==-4 && vm.SpectrumValues[2]==-3.5,"Selected-fiber Sum displays only the requested combination");
        vm.SelectFiber(6,false);vm.SelectFiber(5,false);
        check(vm.SelectedFibers.SetEquals(new[]{1,2}),"Inactive and wholly invalid fibers cannot silently replace selection");
        vm.SelectFiber(2,true);
        check(vm.SelectedFibers.SetEquals(new[]{1}),"Ctrl toggle removes a selected fiber");
        vm.SelectRectangle(0,11,false);
        check(vm.SelectedFibers.SetEquals(new[]{0,1,10,11}),"Rectangular spatial selection preserves original IDs");
        vm.SelectFiberRange(4,8,false);
        check(vm.SelectedFibers.SetEquals(new[]{4,7,8}),"Spectral range selection excludes inactive/invalid fibers without renumbering");
        vm.AutoIfu=false;vm.IfuMin="-100";vm.IfuMax="100";
        vm.AutoSpectral=false;vm.SpectralMin="-200";vm.SpectralMax="500";
        vm.IntegrationMode="Single";vm.SliderValue=500.75;
        check(vm.Applied.IfuMin==-100 && vm.Applied.SpectralMin==-200,"Independent manual image limits survive wavelength changes");
        vm.SpectrumMin="-9.5";vm.SpectrumMax="100";
        check(!vm.AutoSpectrum && vm.SpectrumRange==(-9.5,100d),"Manual spectrum intensity range independent of image ranges");
        vm.Zoom(.5,.5);var left=vm.ZoomMin;vm.Pan(.1);
        check(vm.ZoomMin>left && vm.ZoomMax<501.01,"Wavelength zoom and pan use calibrated coordinates");
        vm.ResetZoom();check(vm.ZoomMin==500.25 && vm.ZoomMax==501,"Reset shows the full real wavelength range");
        var restored=new IfuDisplayViewModel(vm.StoragePath);
        check(restored.Applied==vm.Applied,"Viewer combination, auto/manual and display controls persist");
        var saved=cube.Value(1,2);
        for(int i=0;i<150;i++)vm.SliderValue=cube.Wavelengths[i%7];
        check(ReferenceEquals(cube,vm.Cube)&&cube.Value(1,2)==saved,"Repeated wavelength changes use the same immutable cached cube");

        var repo=new DirectoryInfo(AppContext.BaseDirectory);
        while(repo!=null&&!File.Exists(Path.Combine(repo.FullName,"TIFRES.sln")))repo=repo.Parent;
        var fixture=Path.Combine(root,"cube.fits");
        var start=new ProcessStartInfo(ReductionRequest.ResolvePython("python")){UseShellExecute=false,RedirectStandardError=true,CreateNoWindow=true};
        foreach(var arg in new[]{"-B","-c","import sys;sys.path.insert(0,sys.argv[1]);from test_viewer import fixture;fixture(sys.argv[2],n=17)",Path.Combine(repo!.FullName,"python","tests"),fixture})start.ArgumentList.Add(arg);
        using(var process=Process.Start(start)!){var errors=process.StandardError.ReadToEnd();process.WaitForExit();check(process.ExitCode==0,"Generate synthetic 3D FITS: "+errors);}
        var loaded=Task.Run(()=>FitsCubeLoader.LoadAsync("python",fixture)).GetAwaiter().GetResult();
        check(loaded.Samples==17 && loaded.Value(97,4)==97*17+4-12.5 && loaded.Wavelengths[16]==502.25,"Astropy binary transfer preserves double values, orientation and exact wavelength samples");
        var task=vm.LoadAsync("python",fixture);Pump(task);
        check(vm.ViewerStatus.StartsWith("Loaded")&&!vm.IsLoading,"Viewer asynchronously loads through configured Python");
        File.Delete(fixture);vm.SliderValue=501;
        check(vm.Cube!.Samples==17,"Viewing continues after source removal without another disk read");
        Pump(vm.LoadAsync("python",fixture));check(vm.ViewerStatus.Contains("not found")&&vm.Cube!=null,"Failed load is explicit and retains the previous cube");
        vm.CloseCube();check(vm.Cube==null&&vm.SelectedFibers.Count==0&&vm.SpectrumValues.Count==0,"Close releases cached cube and selections");
        var cancelledLoad=vm.LoadAsync("python",Path.Combine(root,"missing.fits"));vm.CloseCube();Pump(cancelledLoad);
        check(vm.Cube==null&&!vm.IsLoading,"Close during loading cancels and cannot install a late cube");
        try {Task.Run(()=>FitsCubeLoader.LoadAsync(Path.Combine(root,"missing-python"),Path.Combine(root,"settings.json"))).GetAwaiter().GetResult();check(false,"Missing executable rejected");}
        catch(Exception){check(true,"Missing Python executable/input rejected without replacing the cube");}
        var many=20000;
        var large=new FitsCube(new CubeMetadata(1,[120,many],"float64","little","fiber,wavelength",[0,1],"nm","counts","large-synthetic",[]),
            Enumerable.Range(0,many).Select(i=>500.0+i*.01).ToArray(),Enumerable.Range(0,120*many).Select(i=>(double)(i%many)).ToArray());
        vm.SetCube(large);vm.IntegrationMode="Mean";vm.WaveFirst="500";vm.WaveLast="600";
        vm.IntegrationMode="Sum";vm.WaveFirst="500";vm.WaveLast="500.02";
        var timeout=Stopwatch.StartNew();
        while(vm.IfuValues[0]!=3 && timeout.Elapsed<TimeSpan.FromSeconds(5)){Dispatcher.UIThread.RunJobs();Thread.Sleep(5);}
        check(vm.IfuValues[0]==3,"Latest large-cube integration wins after rapid changes, without blocking UI");
        vm.SelectFiber(0,false);vm.CombinationMode="Sum";vm.CloseCube();
        var until=Stopwatch.StartNew();while(until.ElapsedMilliseconds<80){Dispatcher.UIThread.RunJobs();Thread.Sleep(5);}
        check(vm.Cube==null&&vm.SpectrumValues.Count==0,"Closed cube cannot be repopulated by an old background calculation");
        var product=Path.Combine(root,"science.w9wc.fits");File.WriteAllText(product,"placeholder");
        check(FitsCubeLoader.ResolveProducts(root,"science.fits",9).Single()==product&&FitsCubeLoader.ResolveProducts(root,"science.fits",5).Length==0,"DSNO product resolution respects fibintwid without unrelated fallback");
        File.WriteAllText(Path.Combine(root,"science.w9dcb.fits"),"placeholder");
        check(FitsCubeLoader.ResolveProducts(root,"science.fits",9).Length==2,"Multiple matching products are offered for explicit selection");
        var real=Path.Combine(repo.FullName,"fits","20260914","veA01_clf590w.sp.w5wc.fits");
        if(File.Exists(real))
        {
            var copy=Path.Combine(root,"real.w5wc.fits");File.Copy(real,copy);
            var actual=Task.Run(()=>FitsCubeLoader.LoadAsync("python",copy)).GetAwaiter().GetResult();
            check(actual.Samples==2048&&actual.Metadata.Active.Length==113&&actual.Metadata.WavelengthUnit.Contains("unspecified"),"Read-only representative WC copy: 2048 wavelengths, 113 active fibers, missing units explicit");
            check(Math.Abs(actual.Wavelengths[^1]-(585.01337+2047*.00331))<1e-10,"Real WC uses sample centers, not exclusive WAVMAX");
        }
        var main=new MainWindowViewModel(new SettingsViewModel(Path.Combine(root,"settings.json")));main.Display.SetCube(Synthetic());
        var window=new MainWindow{DataContext=main};window.Show();Layout(window);
        try
        {
            var overlay=window.FindControl<IfuOverlayLayer>("IfuOverlay")!;
            var spectral=window.FindControl<SpectralImageLayer>("SpectralPreview")!;
            foreach(var x in new[]{false,true})foreach(var y in new[]{false,true})
            {
                main.Display.InvertX=x;main.Display.InvertY=y;
                var p=overlay.TranslatePoint(IfuCoordinates.ToScreen(new(7,9),overlay.Bounds.Size,main.Display.Applied),window)!.Value;
                window.MouseDown(p,MouseButton.Left);window.MouseUp(p,MouseButton.Left);
                check(main.Display.SelectedFibers.SetEquals(new[]{97}),$"Actual loaded IFU mouse mapping under inversions {x},{y}");
            }
            var click=spectral.TranslatePoint(new(spectral.Bounds.Width/2,(119-8+.5)*spectral.Bounds.Height/120),window)!.Value;
            window.MouseDown(click,MouseButton.Left);window.MouseUp(click,MouseButton.Left);
            check(main.Display.SelectedFibers.SetEquals(new[]{8}),"Spectral mouse selection updates the same state as IFU");
            var extra=spectral.TranslatePoint(new(spectral.Bounds.Width/2,(119-9+.5)*spectral.Bounds.Height/120),window)!.Value;
            window.MouseDown(extra,MouseButton.Left,RawInputModifiers.Control);window.MouseUp(extra,MouseButton.Left,RawInputModifiers.Control);
            check(main.Display.SelectedFibers.SetEquals(new[]{8,9}),"Actual Ctrl-click adds spectral fiber to shared selection");
            var begin=overlay.TranslatePoint(IfuCoordinates.ToScreen(new(0,0),overlay.Bounds.Size,main.Display.Applied),window)!.Value;
            var end=overlay.TranslatePoint(IfuCoordinates.ToScreen(new(1,1),overlay.Bounds.Size,main.Display.Applied),window)!.Value;
            window.MouseDown(begin,MouseButton.Left);window.MouseMove(end,RawInputModifiers.LeftMouseButton);window.MouseUp(end,MouseButton.Left);
            check(main.Display.SelectedFibers.SetEquals(new[]{0,1,10,11}),"Actual IFU drag selects a rectangular group after inversion");
            using(var frame=window.CaptureRenderedFrame()){check(frame!=null,"Skia renders the real cube image, ellipse and spectrum");frame?.Save(Path.Combine(repo.FullName,"docs","step6-synthetic-viewer.png"));}
            var builds=spectral.BitmapBuilds;
            main.Display.WaveFirst="500.625";main.Display.CenterX="4";main.Display.SelectFiber(20,false);
            using(var frame=window.CaptureRenderedFrame()){}
            check(spectral.BitmapBuilds==builds && builds>0,"Wavelength integration, selection and ellipse edits reuse the spectral bitmap");
            main.Display.SpectralMin="-123";
            using(var frame=window.CaptureRenderedFrame()){}
            check(spectral.BitmapBuilds==builds+1,"Spectral intensity change rebuilds the buffered image exactly once");
            var width=window.FindControl<TextBox>("EllipseWidthControl")!;
            var height=window.FindControl<TextBox>("EllipseHeightControl")!;
            check(width.Parent is Grid g&&Grid.GetColumn(width)==1&&g.Children.OfType<TextBlock>().Count()==1,"Compact parameter labels and values share a row");
            check(width.Bounds.Width>=50 && height.Bounds.Width>=50,"Compact values retain readable input width");
        }
        finally{window.Close();}
    }
    private static void Pump(Task task){while(!task.IsCompleted){Dispatcher.UIThread.RunJobs();Thread.Sleep(5);}task.GetAwaiter().GetResult();}
    private static void Layout(Window w){Dispatcher.UIThread.RunJobs();w.UpdateLayout();}
}
