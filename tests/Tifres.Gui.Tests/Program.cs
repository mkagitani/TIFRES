using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.LogicalTree;
using Avalonia.Themes.Fluent;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Tifres.App.Services;
using Tifres.App.ViewModels;
using Tifres.App.Views;

AppBuilder.Configure<TestApplication>().UseSkia().UseHeadless(new AvaloniaHeadlessPlatformOptions { UseHeadlessDrawing = false }).SetupWithoutStarting();
var directory = Path.Combine(Path.GetTempPath(), "tifres-gui-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(directory);
int count = 0;
void Check(bool condition, string message) { if (!condition) throw new Exception(message); count++; Console.WriteLine("PASS " + message); }
void Reject(Action action, string message)
{
    try { action(); } catch (InvalidOperationException) { Check(true, message); return; }
    throw new Exception("Expected rejection: " + message);
}
try
{
    LogFormattingRegression.Run(directory, Check);
    QuickLookRegression.Run(directory, Check);
    var csv = Path.Combine(directory, "dataset.csv");
    const string content = "DSNO,DATATYPE,FILENAME\n1,A,A\n260914010,SKY,night/sky.fits\n900719925474099312345,VENUS,night/venus.fits\n";
    File.WriteAllText(csv, content);
    var settings = new SettingsViewModel(Path.Combine(directory, "settings.json")) { CsvPath = csv };
    var dataset = new DatasetViewModel();
    var operations = new OperationsViewModel(settings, dataset);
    Check(operations.Overwrite && operations.EffectiveOverwriteState.Contains("ON"), "Overwrite defaults ON");
    operations.Step = "mkFibFit4c";
    Check(JsonDocument.Parse(operations.OptionsJson).RootElement.GetProperty("finterval").GetInt32() == 8, "GUI finterval starts at 8 (options-section requirement)");
    Check(!JsonDocument.Parse(operations.OptionsJson).RootElement.GetProperty("flgPause").GetBoolean(), "Fiber fitting starts without pauses");
    foreach (var interval in new[] { 1, 16, 8 })
    {
        operations.OptionsJson = "{\"flgPause\":false,\"finterval\":" + interval + "}";
        operations.Step = "mkSpFrames4f"; operations.Step = "mkFibFit4c";
        Check(JsonDocument.Parse(operations.OptionsJson).RootElement.GetProperty("finterval").GetInt32() == interval, $"finterval {interval} retained across step changes");
    }
    operations.OptionsJson = "{\"flgPause\":false,\"finterval\":16}";
    settings.PngDirectory = Path.Combine(directory, "custom PNG");
    settings.Save();
    var restoredSettings = new SettingsViewModel(settings.StoragePath);
    var restoredOperations = new OperationsViewModel(restoredSettings, new DatasetViewModel()) { Step = "mkFibFit4c" };
    Check(JsonDocument.Parse(restoredOperations.OptionsJson).RootElement.GetProperty("finterval").GetInt32() == 16, "Last-used finterval 16 persists across restart");
    Check(restoredSettings.PngDirectory == settings.PngDirectory, "PNG directory persists across restart");
    operations.Step = "mkWcalSpec4d";
    Check(!JsonDocument.Parse(operations.OptionsJson).RootElement.GetProperty("flgPlot").GetBoolean(), "Wavelength calibration defaults flgPlot=false");
    operations.OptionsJson = "{\"flgPlot\":true}";
    operations.Step = "mkFibFit4c"; operations.Step = "mkWcalSpec4d";
    Check(JsonDocument.Parse(operations.OptionsJson).RootElement.GetProperty("flgPlot").GetBoolean(), "Diagnostic plotting can be enabled explicitly");
    operations.Step = "mkSpFrames4f";
    dataset.Open(csv);
    Check(dataset.Selected == null && operations.SelectedDsno == "No dataset selected", "Opening CSV does not select sample DSNO 1");
    Reject(() => operations.CreateRequest(), "Run rejected without explicit dataset selection");
    dataset.Selected = dataset.FilteredRows[0];
    Reject(() => operations.CreateRequest(), "Placeholder dataset with invalid FILENAME cannot run");
    dataset.Selected = dataset.FilteredRows[1];
    Check(operations.SelectedDsno == "260914010" && operations.CreateRequest().Dsno == "260914010", "Displayed and requested DSNO follow selected dataset");
    dataset.Selected = dataset.FilteredRows[2];
    Check(operations.SelectedDsno == "900719925474099312345" && operations.CreateRequest().Dsno == operations.SelectedDsno, "Selection changes preserve every DSNO digit");
    var lateOperations = new OperationsViewModel(settings, dataset);
    Check(lateOperations.SelectedDsno == dataset.Selected.Dsno, "Operations initialized after selection displays current DSNO");
    dataset.Groups.SelectMany(g => g.Fields).Single(f => f.Name == "DSNO").Value = "900719925474099312346";
    Check(operations.SelectedDsno == "900719925474099312346", "Selected row edits notify Operations immediately");
    Reject(() => operations.CreateRequest(), "Unsaved DSNO cannot be processed");
    dataset.Save();
    Check(operations.CreateRequest().Dsno == "900719925474099312346", "Saved edited DSNO used in request");
    dataset.Search = "260914010";
    Check(dataset.Selected == null && operations.SelectedDsno == "No dataset selected", "Filtering out selection never substitutes another DSNO");
    Reject(() => operations.CreateRequest(), "Filtered-out selection cannot run");
    dataset.Selected = dataset.FilteredRows.Single();
    dataset.Search = "";
    Check(dataset.Selected?.Dsno == "260914010", "Clearing search retains an explicit matching selection");
    File.AppendAllText(csv, "999,SKY,new.fits\n");
    File.WriteAllText(csv, File.ReadAllText(csv).Replace("night/sky.fits", "night/changed.fits"));
    Reject(() => operations.CreateRequest(), "Stale dataset values cannot run after external CSV edit");
    File.WriteAllText(csv, content);
    dataset.Open(csv); dataset.Selected = dataset.FilteredRows[1];
    settings.CsvPath = Path.Combine(directory, "other.csv");
    Reject(() => operations.CreateRequest(), "Selection from a different CSV rejected");
    settings.CsvPath = csv;
    operations.UseSelected = false; operations.Dsno = "123456";
    Reject(() => operations.CreateRequest(), "Unknown manual DSNO rejected");
    operations.UseSelected = true;
    foreach (var step in operations.Steps)
    {
        operations.Step = step;
        Check(!JsonDocument.Parse(operations.OptionsJson).RootElement.TryGetProperty("overwrite", out _), $"{step}: editable defaults have no competing overwrite flag");
        foreach (var allow in new[] { false, true })
        {
            operations.Overwrite = allow;
            operations.OptionsJson = allow ? "{\"overwrite\":false}" : "{\"overwrite\":true}";
            var request = operations.CreateRequest();
            var json = JsonDocument.Parse(request.OptionsJson).RootElement;
            var hasOption = json.TryGetProperty("overwrite", out var effective);
            Check(request.Overwrite == allow && (hasOption ? effective.GetBoolean() == allow : step is "mkFibFit4c" or "mkWavMap4d"), $"{step}: checkbox {allow} wins over contradictory JSON");
            Check(operations.EffectiveOverwriteState.Contains(allow ? "ON" : "OFF"), "Visible effective overwrite matches checkbox");
            // Exercise the actual argument boundary without launching Python or reductions.
            var launcher = Path.Combine(directory, "launcher.py"); File.WriteAllText(launcher, "# mock");
            File.WriteAllText(Path.Combine(directory, "cfg.py"), "# mock");
            File.WriteAllText(Path.Combine(directory, step + ".py"), "# mock");
            var start = (request with { Python = Environment.ProcessPath!, Launcher = launcher, ScriptDirectory = directory, RawDirectory = directory, FitsDirectory = directory }).StartInfo();
            var argumentJson = JsonDocument.Parse(start.ArgumentList[start.ArgumentList.IndexOf("--options-json") + 1]).RootElement;
            Check(start.ArgumentList.Contains("--overwrite") == allow && (!hasOption || argumentJson.GetProperty("overwrite").GetBoolean() == allow), "Python JSON and overwrite switch agree");
        }
    }
    var window = new MainWindow();
    var tabs = window.GetLogicalDescendants().OfType<TabControl>().Single();
    tabs.SelectedIndex = 2;
    var view = ((TabItem)tabs.Items[2]!).Content as OperationsView ?? throw new Exception("Operations tab missing");
    view.DataContext = operations;
    window.Show();
    foreach (var size in new[] { new Size(900,650), new Size(1100,760), new Size(1440,960) })
    {
        window.Width = size.Width; window.Height = size.Height;
        Dispatcher.UIThread.RunJobs(); window.UpdateLayout();
        var scroll = view.FindControl<ScrollViewer>("OptionsScroll")!;
        Check(scroll.Viewport.Height >= 45 && scroll.Viewport.Height <= 190, $"{size}: options have a bounded scroll viewport");
        foreach (var name in new[] { "RunButton", "StopButton", "StatusText", "OverwriteStateText", "LogScroll" })
        {
            var control = view.FindControl<Control>(name)!;
            var origin = control.TranslatePoint(default, view)!.Value;
            Check(control.Bounds.Height > 0 && origin.Y >= 0 && origin.Y + control.Bounds.Height <= view.Bounds.Height + 1,
                $"{size}: {name} remains inside visible Operations panel");
            Check(!control.GetVisualAncestors().Contains(scroll), $"{name} stays outside the options scroller");
        }
        var run = view.FindControl<Button>("RunButton")!;
        var before = run.TranslatePoint(default, view);
        scroll.Offset = new Vector(0, scroll.Extent.Height); Dispatcher.UIThread.RunJobs(); window.UpdateLayout();
        Check(run.TranslatePoint(default, view) == before, "Scrolling options leaves run controls fixed");
    }
    dataset.Selected = dataset.FilteredRows[2]; Dispatcher.UIThread.RunJobs();
    Check(view.FindControl<TextBlock>("SelectedDsnoText")!.Text == dataset.Selected.Dsno, "Compiled Operations binding displays actual selected DSNO");
    tabs.SelectedIndex = 0;
    var datasetView = (DatasetView)((TabItem)tabs.Items[0]!).Content!;
    datasetView.DataContext = dataset;
    Dispatcher.UIThread.RunJobs(); window.UpdateLayout();
    var table = datasetView.GetVisualDescendants().OfType<ListBox>().Single();
    table.SelectedItem = dataset.FilteredRows[1];
    Dispatcher.UIThread.RunJobs();
    Check(dataset.Selected?.Dsno == "260914010", "Dataset table selection updates the shared view model");
    tabs.SelectedIndex = 2; Dispatcher.UIThread.RunJobs(); window.UpdateLayout();
    Check(view.FindControl<TextBlock>("SelectedDsnoText")!.Text == "260914010" && operations.CreateRequest().Dsno == "260914010",
        "Switching tabs preserves the table-selected DSNO in display and request");
    window.Close();
    CompactLayoutRegression.Run(directory, Check);
    IfuDisplayRegression.Run(directory, Check);
    CubeViewerRegression.Run(directory, Check);
    GuiCancellationRegression.Run(directory, Check);
    Console.WriteLine($"SUCCESS: {count} GUI regression checks passed.");
}
finally { Directory.Delete(directory, true); }

public sealed class TestApplication : Application
{
    public override void Initialize()
    {
        RequestedThemeVariant = Avalonia.Styling.ThemeVariant.Light;
        Styles.Add(new FluentTheme());
        Styles.Add(new Avalonia.Markup.Xaml.Styling.StyleInclude(new Uri("avares://Tifres.App/"))
        { Source = new Uri("avares://Tifres.App/Styles/Compact.axaml") });
    }
}
