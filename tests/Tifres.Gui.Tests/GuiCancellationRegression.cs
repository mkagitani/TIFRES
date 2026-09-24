using System.Diagnostics;
using Avalonia.Controls;
using Avalonia.Threading;
using Tifres.App.ViewModels;
using Tifres.App.Views;

internal static class GuiCancellationRegression
{
    private static void PumpUntil(Func<bool> condition, TimeSpan timeout)
    {
        var clock = Stopwatch.StartNew();
        while (!condition())
        {
            if (clock.Elapsed > timeout) throw new TimeoutException("Headless GUI condition timed out.");
            Dispatcher.UIThread.RunJobs();
            Thread.Sleep(10);
        }
        Dispatcher.UIThread.RunJobs();
    }

    public static void Run(string directory, Action<bool, string> check)
    {
        var root = Path.Combine(directory, "gui-stop");
        Directory.CreateDirectory(root);
        var csv = Path.Combine(root, "dataset.csv");
        File.WriteAllText(csv, "DSNO,DATATYPE,FILENAME,DARKFRAME,FIBX0,FIBX1,FIBXWID,NFIBXY,IFIBIACT\n260914111,SKY,sky.fits,dark.fits,2,5,6,,\n");
        File.WriteAllText(Path.Combine(root, "cfg.py"), "# mock configuration");
        File.WriteAllText(Path.Combine(root, "sky.fits"), "mock input");
        File.WriteAllText(Path.Combine(root, "dark.fits"), "mock input");
        File.WriteAllText(Path.Combine(root, "sky.fib.fits"), "previous valid FITS");
        File.WriteAllText(Path.Combine(root, "mkFibFit4c.py"), """
import cfg, sys
from pathlib import Path
def mkFibFit4c(dsno,flgPause=False,finterval=1):
    with open(Path(cfg.fits_path) / 'sky.fib.fits', 'wb') as stream:
        stream.write(b'partial staged file'); stream.flush()
        Path(cfg.original_path, 'ready').touch()
        while True:
            print('GUI mock fitting progress ' + 'x' * 1000, flush=True)
            print('GUI mock stderr ' + 'y' * 1000, file=sys.stderr, flush=True)
""");
        var settings = new SettingsViewModel(Path.Combine(root, "settings.json"))
        { ScriptDirectory = root, RawDirectory = root, FitsDirectory = root, CsvPath = csv };
        var dataset = new DatasetViewModel(); dataset.Open(csv); dataset.Selected = dataset.FilteredRows.Single();
        var operations = new OperationsViewModel(settings, dataset) { Step = "mkFibFit4c" };
        var view = new OperationsView { DataContext = operations };
        var window = new Window { Content = view, Width = 550, Height = 500 };
        var previousContext = SynchronizationContext.Current;
        SynchronizationContext.SetSynchronizationContext(new AvaloniaSynchronizationContext());
        window.Show();
        Task? task = null;
        try
        {
            task = operations.RunAsync();
            PumpUntil(() => File.Exists(Path.Combine(root, "ready")) || task.IsCompleted, TimeSpan.FromSeconds(30));
            check(!task.IsCompleted && operations.IsRunning, "GUI starts long-running mock fiber fit");
            bool responded = false;
            Dispatcher.UIThread.Post(() => responded = true, DispatcherPriority.Input);
            PumpUntil(() => responded, TimeSpan.FromSeconds(2));
            check(responded, "GUI remains responsive during stdout/stderr flood");
            var stop = view.FindControl<Button>("StopButton")!;
            var clock = Stopwatch.StartNew(); stop.Command!.Execute(null); clock.Stop();
            check(clock.Elapsed < TimeSpan.FromMilliseconds(200) && operations.Status.StartsWith("Stopping"), "Stop command responds immediately in GUI");
            PumpUntil(() => task.IsCompleted, TimeSpan.FromSeconds(15));
            task.GetAwaiter().GetResult();
            check(operations.Status == "Cancelled" && !operations.IsRunning, "Cancelled run cannot report Completed");
            check(view.FindControl<Button>("RunButton")!.IsEnabled && !stop.IsEnabled, "Run re-enabled and Stop disabled after cancellation");
            check(File.ReadAllText(Path.Combine(root, "sky.fib.fits")) == "previous valid FITS", "GUI Stop preserves previously valid FITS");
            check(operations.Log.Contains("recovery manifest"), "GUI reports retained recovery directory");
            check(operations.ProductStatuses.Count == 5, "Cancelled run automatically refreshes all five product statuses");
            check(operations.ProductStatuses.All(n => n.Dsno == "260914111"), "Status response remains bound to selected DSNO");
            check(operations.ProductStatuses.All(n => n.Status != "Complete"), "Mock invalid and incomplete products cannot appear Complete");
            check(view.FindControl<ItemsControl>("ProductStatusList")!.ItemCount == 5, "Compiled status list binding displays all stages");
            var before = Directory.GetFiles(root, "*", SearchOption.AllDirectories).ToDictionary(p => p, p => Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(p))));
            var refresh = operations.RefreshProductStatusAsync();
            check(operations.IsInspecting && !refresh.IsCompleted, "Refresh Status runs asynchronously");
            PumpUntil(() => refresh.IsCompleted, TimeSpan.FromSeconds(15));
            refresh.GetAwaiter().GetResult();
            var after = Directory.GetFiles(root, "*", SearchOption.AllDirectories).ToDictionary(p => p, p => Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(p))));
            check(before.Count == after.Count && before.All(p => after.GetValueOrDefault(p.Key) == p.Value), "GUI status inspection is read-only");
            check(operations.ProductStatusMessage.Contains("5 steps inspected") && operations.ProductStatusMessage.Contains("Warnings:") && !operations.ProductStatusMessage.Contains("recovery.json"), "Main status message is concise with counts");
            check(operations.StatusDiagnostics.Contains("DSNO 260914111"), "Detailed inspection diagnostics remain available separately");
            dataset.Selected = null;
            check(operations.ProductStatuses.Count == 0, "Changing dataset clears stale status");
            var noSelection = operations.RefreshProductStatusAsync();
            PumpUntil(() => noSelection.IsCompleted, TimeSpan.FromSeconds(2));
            check(operations.ProductStatusMessage.Contains("Select a dataset"), "Status inspection rejects missing selection without starting reduction");

        }
        finally
        {
            operations.Stop();
            if (task != null) PumpUntil(() => task.IsCompleted, TimeSpan.FromSeconds(15));
            window.Close();
            SynchronizationContext.SetSynchronizationContext(previousContext);
        }
    }
}
