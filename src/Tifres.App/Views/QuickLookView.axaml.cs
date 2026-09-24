using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using Tifres.App.ViewModels;
namespace Tifres.App.Views;
public partial class QuickLookView : UserControl
{
    public QuickLookView()=>InitializeComponent();
    private async void SelectRaw(object? sender,RoutedEventArgs e)
    {
        if(DataContext is not QuickLookViewModel vm||TopLevel.GetTopLevel(this) is not {} top)return;
        try
        {
            var files=await top.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions{Title="Select raw FITS for one dataset",AllowMultiple=true,
                FileTypeFilter=[new FilePickerFileType("FITS"){Patterns=["*.fits","*.fit","*.fts","*.FITS"]}]});
            if(files.Count>0)await vm.SelectRawAsync(files.Select(f=>f.TryGetLocalPath()??throw new InvalidOperationException("Local files required.")).ToArray());
        }
        catch(Exception ex){vm.Status=ex.Message;}
    }
    private async void DeletePreset(object? sender,RoutedEventArgs e)
    {
        if(DataContext is not QuickLookViewModel vm||vm.SelectedPreset==null||TopLevel.GetTopLevel(this) is not Window owner)return;
        var id=vm.SelectedPreset.Id;
        var dialog=new Window{Title="Delete session preset?",Width=420,Height=165,CanResize=false,WindowStartupLocation=WindowStartupLocation.CenterOwner};
        var yes=new Button{Content="Delete preset"};var no=new Button{Content="Cancel"};
        dialog.Content=new StackPanel{Margin=new Avalonia.Thickness(15),Spacing=12,Children={new TextBlock{Text="Delete "+vm.SelectedPreset.Name+"? Observation CSV is unchanged.",TextWrapping=Avalonia.Media.TextWrapping.Wrap},new StackPanel{Orientation=Avalonia.Layout.Orientation.Horizontal,Spacing=10,Children={no,yes}}}};
        yes.Click+=(_,_)=>dialog.Close(true);no.Click+=(_,_)=>dialog.Close(false);
        if(await dialog.ShowDialog<bool>(owner)&&vm.SelectedPreset?.Id==id)
            try{vm.DeletePreset(true);}catch(Exception ex){vm.Status=ex.Message;}
    }
}
