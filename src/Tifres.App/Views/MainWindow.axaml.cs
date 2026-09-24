using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using System.Text.Json;
using Tifres.App.Services;
using Tifres.App.ViewModels;

namespace Tifres.App.Views;

public partial class MainWindow : Window
{
    private bool _closingAfterStop;
    public MainWindow()
    {
        InitializeComponent();
        Closing += async (_, e) =>
        {
            if (DataContext is not MainWindowViewModel vm) return;
            if (vm.Operations.IsRunning || vm.QuickLook.IsRunning)
            {
                e.Cancel = true;
                if (_closingAfterStop) return;
                _closingAfterStop = true;
                vm.Operations.Stop(); vm.QuickLook.Stop();
                while (vm.Operations.IsRunning || vm.QuickLook.IsRunning) await Task.Delay(50);
                Close();
            }
            else { vm.Display.CloseCube(); vm.Settings.Save(); }
        };
    }

    private async void OpenFits(object? sender,RoutedEventArgs e)
    {
        if(DataContext is not MainWindowViewModel vm)return;
        try
        {
            var files=await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions{Title="Open calibrated IFU FITS",AllowMultiple=false,
                FileTypeFilter=[new FilePickerFileType("FITS"){Patterns=["*.fits","*.fit","*.fts","*.FITS"]},FilePickerFileTypes.All]});
            if(files.Count>0 && files[0].TryGetLocalPath() is {} path)await vm.Display.LoadAsync(vm.Settings.PythonExecutable,path);
        }
        catch(Exception ex){vm.Display.ViewerStatus="Open failed: "+ex.Message;}
    }
    private async void OpenDatasetFits(object? sender,RoutedEventArgs e)
    {
        if(DataContext is not MainWindowViewModel vm)return;
        try
        {
            if(vm.Dataset.IsDirty)throw new InvalidOperationException("Save dataset edits before resolving its product.");
            var row=vm.Dataset.Selected??throw new InvalidOperationException("Select a dataset first, or use Open FITS.");
            var json=vm.Operations.Step=="mkWcalSpec4d"?vm.Operations.OptionsJson:vm.Settings.StepOptions.GetValueOrDefault("mkWcalSpec4d","{}");
            using var options=JsonDocument.Parse(json);
            int width=options.RootElement.TryGetProperty("fibintwid",out var value)?value.GetInt32():5;
            var paths=FitsCubeLoader.ResolveProducts(vm.Settings.FitsDirectory,row.Filename,width);
            if(paths.Length==0)throw new FileNotFoundException($"No calibrated wc/dcb FITS for DSNO {row.Dsno} with fibintwid={width}.");
            string? path=paths[0];
            if(paths.Length>1)
            {
                var list=new ListBox{ItemsSource=paths,SelectedIndex=0};
                var open=new Button{Content="Open selected",HorizontalAlignment=Avalonia.Layout.HorizontalAlignment.Right};
                var dialog=new Window{Title="Choose this DSNO's calibrated product",Width=620,Height=220,Content=new DockPanel()};
                var panel=(DockPanel)dialog.Content!;DockPanel.SetDock(open,Dock.Bottom);panel.Children.Add(open);panel.Children.Add(list);
                open.Click+=(_,_)=>dialog.Close(list.SelectedItem as string);
                path=await dialog.ShowDialog<string?>(this);
            }
            if(path!=null)await vm.Display.LoadAsync(vm.Settings.PythonExecutable,path);
        }
        catch(Exception ex){vm.Display.ViewerStatus="Dataset open failed: "+ex.Message;}
    }
    private async void ReloadFits(object? sender,RoutedEventArgs e)
    {if(DataContext is MainWindowViewModel vm && vm.Display.Cube!=null)await vm.Display.LoadAsync(vm.Settings.PythonExecutable,vm.Display.Filename);}
    private void CloseFits(object? sender,RoutedEventArgs e){if(DataContext is MainWindowViewModel vm)vm.Display.CloseCube();}
    private void ZoomIn(object? sender,RoutedEventArgs e){if(DataContext is MainWindowViewModel vm)vm.Display.Zoom(.8,.5);}
    private void ZoomOut(object? sender,RoutedEventArgs e){if(DataContext is MainWindowViewModel vm)vm.Display.Zoom(1.25,.5);}
    private void ResetZoom(object? sender,RoutedEventArgs e){if(DataContext is MainWindowViewModel vm)vm.Display.ResetZoom();}
}
