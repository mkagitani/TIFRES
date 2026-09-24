
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Threading;
using Avalonia.Headless;
using Avalonia.Input;
using Avalonia.VisualTree;
using Tifres.App.ViewModels;
using Tifres.App.Views;

internal static class IfuDisplayRegression
{
    public static void Run(string directory, Action<bool,string> check)
    {
        var path = Path.Combine(directory,"display-tests","display-settings.json");
        var vm = new IfuDisplayViewModel(path);
        var original = vm.IfuValues.ToArray(); var spectra = vm.SpectralValues.ToArray();
        check(vm.Applied.EllipseEnabled, "IFU ellipse enabled by default");
        vm.Width="4"; vm.Height="2"; vm.CenterX="3"; vm.CenterY="4";
        var a = IfuCoordinates.EllipsePoint(vm.Applied,0);
        var b = IfuCoordinates.EllipsePoint(vm.Applied,Math.PI/2);
        check(Near(a,new(5,4)) && Near(b,new(3,5)), "Ellipse uses full axis lengths and physical center");
        vm.Angle="90";
        check(Near(IfuCoordinates.EllipsePoint(vm.Applied,0),new(3,6)), "Positive position angle rotates counterclockwise in physical coordinates");
        vm.Angle="37.5"; vm.LineColor="Blue";
        foreach (var x in new[]{false,true}) foreach(var y in new[]{false,true})
        {
            vm.InvertX=x; vm.InvertY=y;
            foreach (var size in new[]{new Size(100,120),new Size(250,300)})
            {
                check(Enumerable.Range(0,120).All(id => IfuCoordinates.FiberAt(IfuCoordinates.ToScreen(new(id%10,id/10),size,vm.Applied),size,vm.Applied)==id),
                    $"All original fiber IDs survive X={x},Y={y},size={size}");
                var point = IfuCoordinates.EllipsePoint(vm.Applied,.7);
                var unflipped = IfuCoordinates.ToScreen(point,size,vm.Applied with {InvertX=false,InvertY=false});
                check(Near(IfuCoordinates.ToScreen(point,size,vm.Applied),new(x?size.Width-unflipped.X:unflipped.X,y?size.Height-unflipped.Y:unflipped.Y)),
                    $"Ellipse shares image inversion and resize transform X={x},Y={y},size={size}");
            }
        }
        check(IfuCoordinates.FiberAt(new(-1,1),new(100,120),vm.Applied)==null && IfuCoordinates.FiberAt(new(100,120),new(100,120),vm.Applied)==null,"Outside-image clicks cannot select fibers");
        vm.IfuMin="-10.25"; vm.IfuMax="30.5";
        check(vm.Applied.IfuMin==-10.25 && vm.Applied.IfuMax==30.5 && vm.Applied.SpectralMin==-1 && vm.Applied.SpectralMax==1,"IFU range accepts negative fractions independently");
        vm.SpectralMin="-2.5"; vm.SpectralMax="4.75";
        check(vm.Applied.IfuMin==-10.25 && vm.Applied.IfuMax==30.5 && vm.Applied.SpectralMax==4.75,"Spectral range does not change IFU range");
        var valid = vm.Applied;
        vm.IfuMin="30.5"; vm.SpectralMax="-3";
        check(vm.Applied==valid && vm.IfuRangeError.Length>0 && vm.SpectralRangeError.Length>0,"Equal and reversed ranges rejected; last valid ranges retained");
        vm.IfuMin="NaN"; vm.SpectralMax="Infinity"; vm.Width="-1";
        check(vm.Applied==valid && vm.EllipseError.Length>0,"Nonfinite ranges and negative axes rejected");
        check(new IfuDisplayViewModel(path).Applied==valid,"All valid ellipse, inversion and independent ranges persist across sessions");
        check(original.SequenceEqual(vm.IfuValues) && spectra.SequenceEqual(vm.SpectralValues),"Display edits never mutate underlying arrays");
        check(DisplayLayer.IntensityColor(0,-1,1)!=DisplayLayer.IntensityColor(0,-1,3),"Display range changes rendered intensity");

        var settings = new SettingsViewModel(Path.Combine(directory,"ui-display","settings.json"));
        var main = new MainWindowViewModel(settings);
        main.Display.SetCube(CubeViewerRegression.Synthetic());
        var window = new MainWindow {DataContext=main};
        window.Show();
        try
        {
            var tabs = window.FindControl<TabControl>("ControlTabs")!;
            tabs.SelectedIndex=2;
            Layout(window);
            var overlay = window.FindControl<IfuOverlayLayer>("IfuOverlay")!;
            var image = window.FindControl<IfuImageLayer>("IfuImage")!;
            check(overlay.Parent==image.Parent && !ReferenceEquals(overlay,image) && overlay.Bounds==image.Bounds,"Ellipse is a separate, exactly aligned overlay layer");
            foreach(var x in new[]{false,true}) foreach(var y in new[]{false,true})
            {
                window.FindControl<CheckBox>("InvertXControl")!.IsChecked=x;
                window.FindControl<CheckBox>("InvertYControl")!.IsChecked=y;
                var local = IfuCoordinates.ToScreen(new(7,9),overlay.Bounds.Size,main.Display.Applied);
                var click = overlay.TranslatePoint(local,window)!.Value;
                window.MouseDown(click,MouseButton.Left);
                window.MouseUp(click,MouseButton.Left);
                check(main.Display.InvertX==x && main.Display.InvertY==y && main.Display.SelectedFiber==97,$"UI inversion bindings and overlay selection preserve fiber 97: {x},{y}");
            }
            window.FindControl<TextBox>("EllipseWidthControl")!.Text="3.25";
            window.FindControl<TextBox>("IfuMinControl")!.Text="-2.25";
            window.FindControl<TextBox>("SpectralMinControl")!.Text="-3.5";
            check(main.Display.Applied.Width==3.25 && main.Display.Applied.IfuMin==-2.25 && main.Display.Applied.SpectralMin==-3.5,"Compiled display controls update distinct properties");
            window.FindControl<CheckBox>("EllipseEnabledControl")!.IsChecked=false;
            check(!main.Display.Applied.EllipseEnabled,"Ellipse enabled binding controls overlay visibility");
            var op = (OperationsView)((TabItem)tabs.Items[2]!).Content!;
            var selected = op.FindControl<CheckBox>("UseSelectedCheckBox")!;
            var overwrite = op.FindControl<CheckBox>("OverwriteCheckBox")!;
            check(selected.Parent==op.FindControl<Grid>("DsnoRow") && Grid.GetColumn(selected)==2,"DSNO checkbox follows the DSNO value in the same row");
            check(overwrite.Parent==op.FindControl<Grid>("RunRow") && Grid.GetColumn(overwrite)==2 && overwrite.IsChecked==true,"Overwrite defaults ON after Run and Stop in their row");
            selected.IsChecked=false; overwrite.IsChecked=false;
            check(!main.Operations.UseSelected && !main.Operations.Overwrite && main.Operations.EffectiveOverwriteState.Contains("OFF"),"Operations checkboxes retain two-way bindings and effective authority");
            foreach(var size in new[]{new Size(900,650),new Size(1100,760),new Size(1440,960)})
            {
                window.Width=size.Width; window.Height=size.Height; Layout(window);
                var scroll=window.FindControl<ScrollViewer>("InformationScroll")!;
                check(scroll.HorizontalScrollBarVisibility==ScrollBarVisibility.Disabled && scroll.Extent.Height>scroll.Viewport.Height,$"{size}: compact persistent controls scroll vertically");
                var inputs=scroll.GetVisualDescendants().OfType<TextBox>().Where(c=>c.IsEffectivelyVisible).ToArray();
                check(inputs.All(c=>c.Bounds.Width>0 && c.TranslatePoint(default,scroll) is Point p && p.X>=0 && p.X+c.Bounds.Width<=scroll.Bounds.Width+1),$"{size}: display inputs fit narrow panel without horizontal clipping");
                scroll.Offset=new Vector(0,scroll.Extent.Height); Layout(window);
                var last=window.FindControl<TextBox>("SpectralMaxControl")!;
                var pos=last.TranslatePoint(default,scroll)!.Value;
                check(pos.Y>=0 && pos.Y+last.Bounds.Height<=scroll.Bounds.Height+1,$"{size}: bottom display controls remain reachable");
                check(!overwrite.GetVisualAncestors().Contains(op.FindControl<ScrollViewer>("OptionsScroll")!),"Overwrite stays accessible with Run and Stop");
            }
        }
        finally {window.Close();}
    }
    private static bool Near(Point a,Point b)=>Math.Abs(a.X-b.X)<1e-7 && Math.Abs(a.Y-b.Y)<1e-7;
    private static void Layout(Window w) {Dispatcher.UIThread.RunJobs();w.UpdateLayout();}
}
