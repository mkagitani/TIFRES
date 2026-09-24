using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using Tifres.App.ViewModels;
namespace Tifres.App.Views;
public partial class DatasetView : UserControl
{
    public DatasetView() => InitializeComponent();
    private async void OpenCsv(object? sender, RoutedEventArgs args)
    {
        if (DataContext is not DatasetViewModel vm) return;
        if (vm.IsDirty) { vm.Message = "Save unsaved changes before opening another CSV."; return; }
        try
        {
            var top = TopLevel.GetTopLevel(this);
            if (top == null) return;
            var files = await top.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
            {
                Title = "Open dataset CSV", AllowMultiple = false,
                FileTypeFilter = [new FilePickerFileType("CSV") { Patterns = ["*.csv"] }]
            });
            if (files.Count > 0 && files[0].TryGetLocalPath() is { } path) vm.Open(path);
        }
        catch (Exception ex) { vm.Message = $"Open failed: {ex.Message}"; }
    }
}
