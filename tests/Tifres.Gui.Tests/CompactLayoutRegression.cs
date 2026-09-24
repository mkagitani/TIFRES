using Avalonia;
using Avalonia.Automation;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Input;
using Avalonia.Media;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Tifres.App.Services;
using Tifres.App.ViewModels;
using Tifres.App.Views;

internal static class CompactLayoutRegression
{
    public static void Run(string directory, Action<bool, string> check)
    {
        var csv = Path.Combine(directory, "compact.csv");
        // Read the supplied schema, but exercise editing/saving only on a temp copy.
        var repo = new DirectoryInfo(AppContext.BaseDirectory);
        while (repo != null && !File.Exists(Path.Combine(repo.FullName, "TIFRES.sln"))) repo = repo.Parent;
        File.Copy(Path.Combine(repo!.FullName, "testdata", "hmew202510MeBpy2.csv"), csv);
        var settingsPath = Path.Combine(directory, "compact-settings.json");
        var settings = new SettingsViewModel(settingsPath) { CsvPath = csv, PngDirectory = Path.Combine(directory, "PNG long path") };
        var vm = new MainWindowViewModel(settings);
        vm.Dataset.Selected = vm.Dataset.FilteredRows.First(r => r.Dsno == "260914111");
        var window = new MainWindow { DataContext = vm };
        window.Show(); Layout(window);
        try
        {
            var root = window.FindControl<Grid>("WorkspaceGrid")!;
            var display = window.FindControl<Grid>("DisplayGrid")!;
            var tabs = window.FindControl<TabControl>("ControlTabs")!;
            var right = window.FindControl<Border>("ControlPanel")!;
            check(root.ColumnDefinitions[0].Width == new GridLength(2, GridUnitType.Star) && root.ColumnDefinitions[2].Width == GridLength.Star,
                "Root columns default to 2:1, with a splitter column");
            check(root.RowDefinitions.Count == 0, "Old three-row root layout is removed");
            check(display.ColumnDefinitions[0].Width == GridLength.Star && display.ColumnDefinitions[2].Width == new GridLength(4, GridUnitType.Star), "Display columns default to 1:4");
            check(display.RowDefinitions[0].Height == new GridLength(4, GridUnitType.Star) && display.RowDefinitions[2].Height == new GridLength(2, GridUnitType.Star), "Display rows default to 4:2");
            foreach (var (name, row, column) in new[] { ("InformationPanel",0,0), ("SpectralImagePanel",0,2), ("IfuPanel",2,0), ("SpectrumPanel",2,2) })
            {
                var control = window.FindControl<Border>(name)!;
                check(control.Parent == display && Grid.GetRow(control) == row && Grid.GetColumn(control) == column, name + " occupies the requested quadrant");
            }
            check(Math.Abs(display.Bounds.Width / right.Bounds.Width - 2) < .02, "Rendered default root widths are approximately 2:1");
            var info = window.FindControl<Border>("InformationPanel")!;
            var image = window.FindControl<Border>("SpectralImagePanel")!;
            check(Math.Abs(image.Bounds.Width / info.Bounds.Width - 4) < .04, "Rendered default left widths are approximately 1:4");
            check(window.FindControl<TextBlock>("InformationDsno")!.Text!.Contains("260914111"), "Persistent information panel shows selected DSNO");
            window.FindControl<TextBox>("ObservationNotes")!.Text = "Persistent compact notes";
            check(vm.ObservationNotes == "Persistent compact notes", "Persistent notes retain two-way editing");
            check(window.FindControl<ScrollViewer>("InformationScroll") != null, "Narrow information panel scrolls independently");
            foreach (var name in new[] { "WorkspaceSplitter", "DisplayColumnSplitter", "DisplayRowSplitter" })
                check(window.FindControl<GridSplitter>(name) != null, name + " is available");

            var datasetView = (DatasetView)((TabItem)tabs.Items[0]!).Content!;
            var fields = vm.Dataset.Groups.SelectMany(g => g.Fields).ToArray();
            var presented = vm.Dataset.Groups.SelectMany(g => g.Rows).SelectMany(r => r.Second == null ? new[] { r.First } : new[] { r.First, r.Second }).ToArray();
            check(fields.Length == 98 && fields.Length == presented.Length && fields.All(presented.Contains), "Compact editor retains every one of the 98 CSV fields");
            check(vm.Dataset.Groups.SelectMany(g => g.Rows).Any(r => r.First.Name == "DSNO" && r.Second?.Name == "DATATYPE"), "DSNO and DATATYPE share a parameter row");
            check(vm.Dataset.Groups.SelectMany(g => g.Rows).Where(r => r.First.Name is "FILENAME" or "ORIGIN" or "CALWAVS" || r.First.Value.Contains(',')).All(r => !r.HasSecond), "Paths and comma-separated values use full-width rows");
            var table = datasetView.FindControl<ListBox>("DatasetTable")!;
            var listRow = table.GetVisualDescendants().OfType<ListBoxItem>().First();
            check(listRow.Bounds.Height <= 26 && table.FontSize <= 12, "Dataset table has compact rows and font");
            var nameBox = datasetView.GetVisualDescendants().OfType<TextBox>().Single(t => AutomationProperties.GetName(t) == "FILENAME");
            check(nameBox.Bounds.Height is >= 24 and <= 28, "Dataset parameter TextBox has compact readable height");
            var longValue = "night/" + new string('x', 180) + ".fits";
            nameBox.Text = longValue;
            check(fields.Single(f => f.Name == "FILENAME").Value == longValue && (string?)ToolTip.GetTip(nameBox) == longValue,
                "Long parameter edits are preserved internally with a full-value tooltip");
            vm.Dataset.Save();
            check(!vm.Dataset.IsDirty && File.ReadAllText(csv).Contains(longValue), "Compact editor still saves values and clears unsaved state");

            tabs.SelectedIndex = 1; Layout(window);
            var settingsView = (SettingsView)((TabItem)tabs.Items[1]!).Content!;
            var settingsGrid = settingsView.FindControl<Grid>("SettingsFields")!;
            check(settingsGrid.RowDefinitions.Count == 6 && settingsGrid.ColumnDefinitions.Count == 3, "Settings uses six Label | TextBox | Browse rows");
            for (var row = 0; row < 6; row++)
            {
                var cells = settingsGrid.Children.Where(c => Grid.GetRow(c) == row).ToArray();
                var box = cells.OfType<TextBox>().Single(); var button = cells.OfType<Button>().Single(); var label = cells.OfType<TextBlock>().Single();
                check(Grid.GetColumn(box) == 1 && Grid.GetColumn(button) == 2 && box.Bounds.Height is >= 24 and <= 28 && button.Bounds.Height <= 28 && Math.Abs(box.Bounds.Center.Y - label.Bounds.Center.Y) < 2,
                    $"Settings row {row + 1} aligns compact controls on one line");
            }
            settingsGrid.Children.OfType<TextBox>().Single(t => Grid.GetRow(t) == 5).Text = "PNG path kept exactly";
            settings.Save();
            check(new SettingsViewModel(settingsPath).PngDirectory == "PNG path kept exactly", "Compact Settings preserves existing JSON/path persistence");

            tabs.SelectedIndex = 2; Layout(window);
            var operations = (OperationsView)((TabItem)tabs.Items[2]!).Content!;
            for (var i = 0; i < 5; i++) vm.Operations.ProductStatuses.Add(new ProductNode(i.ToString(), "260914111", vm.Operations.Steps[i],
                new[] { "SpFrames", "Fiber Fit", "Fiber Spec", "Wavelength Map", "Wavelength Calibration" }[i], "Unknown", [new("night/output.fits", "Valid")], [], ["Historical product with no provenance."]));
            var statusList = operations.FindControl<ListBox>("ProductStatusList")!;
            statusList.SelectedItem = vm.Operations.ProductStatuses[2]; Layout(window);
            check(vm.Operations.SelectedProductStatus == vm.Operations.ProductStatuses[2], "Status table selects a separate details model");
            foreach (var size in new[] { new Size(900,650), new Size(1100,760), new Size(1440,960) })
            {
                window.Width = size.Width; window.Height = size.Height; Layout(window);
                check(Math.Abs(right.Bounds.Height - display.Bounds.Height) < 1 && tabs.Bounds.Height > root.Bounds.Height - 20, $"{size}: right tabs occupy full workspace height");
                check(Math.Abs(info.Bounds.Height / window.FindControl<Border>("IfuPanel")!.Bounds.Height - 2) < .02, $"{size}: measured left rows keep 2:1 heights");
                check(Math.Abs(window.FindControl<Border>("IfuPanel")!.Bounds.Height - window.FindControl<Border>("SpectrumPanel")!.Bounds.Height) < 1, $"{size}: bottom IFU and spectrum outer heights match");
                var aspect = window.FindControl<Viewbox>("IfuAspectBox")!;
                var geometry = window.FindControl<Grid>("IfuGeometry")!;
                var transform = geometry.TransformToVisual(aspect)!.Value;
                var top = transform.Transform(default); var bottom = transform.Transform(new Point(geometry.Bounds.Width, geometry.Bounds.Height));
                check(aspect.Stretch == Stretch.Uniform && Math.Abs((bottom.X-top.X)/(bottom.Y-top.Y) - 10.0/12) < .001,
                    $"{size}: IFU preserves its physical 10:12 aspect ratio");
                check(Math.Abs((top.X+bottom.X)/2 - aspect.Bounds.Width/2) < 1 && Math.Abs((top.Y+bottom.Y)/2 - aspect.Bounds.Height/2) < 1,
                    $"{size}: IFU image is centered in its available area");
                foreach (var name in new[] { "RunButton", "StopButton", "RefreshStatusButton", "ProductStatusList", "DetailsScroll", "LogScroll" })
                {
                    var control = operations.FindControl<Control>(name)!;
                    var point = control.TranslatePoint(default, operations)!.Value;
                    check(point.Y >= 0 && point.Y + control.Bounds.Height <= operations.Bounds.Height + 1 && control.Bounds.Height > 0, $"{size}: {name} remains visible after resizing");
                }
                check(statusList.GetVisualDescendants().OfType<ListBoxItem>().Count() == 5, $"{size}: compact status table shows all five stages");
                var statusRows = statusList.GetVisualDescendants().OfType<ListBoxItem>().ToArray();
                check(statusRows.All(r => r.Bounds.Height <= 24 && r.TranslatePoint(default, statusList)!.Value.Y + r.Bounds.Height <= statusList.Bounds.Height),
                    $"{size}: all five status rows fit without vertical clipping");
                var optionsScroll = operations.FindControl<ScrollViewer>("OptionsScroll")!;
                check(!operations.FindControl<ScrollViewer>("DetailsScroll")!.GetVisualAncestors().Contains(optionsScroll) &&
                      !operations.FindControl<ScrollViewer>("LogScroll")!.GetVisualAncestors().Contains(optionsScroll),
                    $"{size}: details and log scroll independently of options");

            }
            var rowSplitter = window.FindControl<GridSplitter>("DisplayRowSplitter")!;
            var oldHeight = info.Bounds.Height;
            rowSplitter.Focus();
            rowSplitter.RaiseEvent(new KeyEventArgs { RoutedEvent = InputElement.KeyDownEvent, Key = Key.Down }); Layout(window);
            check(Math.Abs(info.Bounds.Height - oldHeight) > 0, "Left row splitter changes panel proportions");
            var columnSplitter = window.FindControl<GridSplitter>("DisplayColumnSplitter")!;
            var oldWidth = info.Bounds.Width;
            columnSplitter.Focus();
            columnSplitter.RaiseEvent(new KeyEventArgs { RoutedEvent = InputElement.KeyDownEvent, Key = Key.Right }); Layout(window);
            check(Math.Abs(info.Bounds.Width - oldWidth) > 0, "Left column splitter changes panel proportions");
            var workspaceSplitter = window.FindControl<GridSplitter>("WorkspaceSplitter")!;
            var oldRight = right.Bounds.Width; workspaceSplitter.Focus();
            workspaceSplitter.RaiseEvent(new KeyEventArgs { RoutedEvent = InputElement.KeyDownEvent, Key = Key.Right }); Layout(window);
            check(Math.Abs(right.Bounds.Width-oldRight) > 0, "Workspace splitter resizes the full-height right panel");
        }
        finally { window.Close(); }
    }

    private static void Layout(Window window) { Dispatcher.UIThread.RunJobs(); window.UpdateLayout(); }
}
