using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using Tifres.App.ViewModels;

namespace Tifres.App.Views;
public partial class SettingsView : UserControl
{
    public SettingsView() => InitializeComponent();
    private async void BrowseFile(object? sender, RoutedEventArgs e)
    {
        if (DataContext is not SettingsViewModel vm || sender is not Button button || TopLevel.GetTopLevel(this) is not { } top) return;
        try
        {
            var csv = button.Tag?.ToString() == "csv";
            var files = await top.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
            {
                Title = csv ? "Choose dataset CSV" : "Choose Python executable", AllowMultiple = false,
                FileTypeFilter = csv ? [new FilePickerFileType("CSV") { Patterns = ["*.csv"] }] : null
            });
            if (files.Count > 0 && files[0].TryGetLocalPath() is { } path)
            {
                if (csv) vm.CsvPath = path; else vm.PythonExecutable = path;
            }
        }
        catch (Exception ex) { vm.Message = ex.Message; }
    }
    private async void BrowseFolder(object? sender, RoutedEventArgs e)
    {
        if (DataContext is not SettingsViewModel vm || sender is not Button button || TopLevel.GetTopLevel(this) is not { } top) return;
        try
        {
            var folders = await top.StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions { Title = "Choose directory", AllowMultiple = false });
            if (folders.Count > 0 && folders[0].TryGetLocalPath() is { } path)
            {
                switch (button.Tag?.ToString())
                {
                    case "scripts": vm.ScriptDirectory = path; break;
                    case "raw": vm.RawDirectory = path; break;
                    case "fits": vm.FitsDirectory = path; break;
                    case "png": vm.PngDirectory = path; break;
                }
            }
        }
        catch (Exception ex) { vm.Message = ex.Message; }
    }
}
