using System.ComponentModel;
using Avalonia.Controls;
using Avalonia.Threading;
using Tifres.App.ViewModels;

namespace Tifres.App.Views;
public partial class OperationsView : UserControl
{
    private OperationsViewModel? _observed;
    public OperationsView()
    {
        InitializeComponent();
        DataContextChanged += (_, _) =>
        {
            if (_observed != null) _observed.PropertyChanged -= ModelChanged;
            _observed = DataContext as OperationsViewModel;
            if (_observed != null) _observed.PropertyChanged += ModelChanged;
            FollowLog();
        };
    }
    private void ModelChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (args.PropertyName == nameof(OperationsViewModel.Log)) FollowLog();
    }
    private void FollowLog() => Dispatcher.UIThread.Post(() => LogScroll.ScrollToEnd(), DispatcherPriority.Background);
}
