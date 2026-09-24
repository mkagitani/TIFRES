using System.Diagnostics;
using Tifres.App.Services;

internal static class CancellationRegression
{
    public static async Task Run(string python, string directory, Action<bool, string> check)
    {
        var runner = new ReductionProcess();
        var start = ReductionProcess.CreateStartInfo(python);
        start.ArgumentList.Add("-u"); start.ArgumentList.Add("-c");
        start.ArgumentList.Add("import subprocess,sys,time; child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); print(child.pid,flush=True); time.sleep(.2)");
        using (var stop = new CancellationTokenSource())
        {
            var ready = new TaskCompletionSource<int>(TaskCreationOptions.RunContinuationsAsynchronously);
            var task = runner.RunAsync(start, text => { if (int.TryParse(text, out int pid)) ready.TrySetResult(pid); }, stop.Token);
            try
            {
                var child = await ready.Task.WaitAsync(TimeSpan.FromSeconds(10));
                await Task.Delay(500); // Immediate parent has exited; child still holds both pipes.
                var latency = Stopwatch.StartNew(); stop.Cancel(); latency.Stop();
                check(latency.Elapsed < TimeSpan.FromMilliseconds(200), "Stop signal returns immediately even after parent exit");
                var result = await task.WaitAsync(TimeSpan.FromSeconds(10));
                check(result.Cancelled, "Inherited stdout/stderr handles do not deadlock cancellation");
                check(Exited(child), "Containment kills child after Python parent has exited");
            }
            finally { stop.Cancel(); await task; }
        }

        var root = Path.Combine(directory, "staging-cancellation");
        var scripts = Path.Combine(root, "scripts"); var raw = Path.Combine(root, "raw"); var fits = Path.Combine(root, "fits");
        foreach (var path in new[] { scripts, raw, fits }) Directory.CreateDirectory(path);
        var csv = Path.Combine(root, "datasets.csv");
        File.WriteAllText(csv, "DSNO,DATATYPE,FILENAME,DARKFRAME,FIBX0,FIBX1,FIBXWID,NFIBXY,IFIBIACT\n260914111,SKY,sky.fits,dark.fits,2,5,6,,\n");
        var csvBefore = File.ReadAllBytes(csv);
        File.WriteAllText(Path.Combine(scripts, "cfg.py"), "# mock configuration\n");
        File.WriteAllText(Path.Combine(fits, "sky.fits"), "mock prerequisite");
        File.WriteAllText(Path.Combine(fits, "dark.fits"), "mock prerequisite");
        var existing = Path.Combine(fits, "sky.fib.fits");
        File.WriteAllText(existing, "previous valid observation product");
        File.WriteAllText(Path.Combine(scripts, "mkFibFit4c.py"), """
import cfg, subprocess, sys, time
from pathlib import Path
def mkFibFit4c(dsno,flgPause=False,finterval=1):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
    with open(Path(cfg.fits_path) / 'sky.fib.fits', 'wb') as stream:
        stream.write(b'INCOMPLETE STAGED FITS'); stream.flush()
        print('STAGED ' + str(child.pid), flush=True)
        while True:
            print('mock fit progress ' + 'x' * 2000, flush=True)
            print('mock plotting/write progress ' + 'y' * 2000, file=sys.stderr, flush=True)
            time.sleep(.001)
""");
        var request = new ReductionRequest(python, Path.Combine(AppContext.BaseDirectory, "python", "tifres_launcher.py"), scripts,
            csv, raw, fits, "mkFibFit4c", "260914111", "{\"finterval\":8}", true, Path.Combine(root, "png"), Guid.NewGuid().ToString("N"));
        using (var stop = new CancellationTokenSource())
        {
            var ready = new TaskCompletionSource<int>(TaskCreationOptions.RunContinuationsAsynchronously);
            var captured = new System.Text.StringBuilder();
            var pending = runner.RunWithOutputAsync(request.StartInfo(), chunk =>
            {
                if (chunk.IsError || ready.Task.IsCompleted) return;
                captured.Append(chunk.Text);
                var match = System.Text.RegularExpressions.Regex.Match(captured.ToString(), @"STAGED (\d+)[\r\n]");
                if (match.Success) ready.TrySetResult(int.Parse(match.Groups[1].Value));
            }, stop.Token);
            try
            {
                var child = await ready.Task.WaitAsync(TimeSpan.FromSeconds(30));
                await Task.Delay(250);
                var clock = Stopwatch.StartNew(); stop.Cancel();
                var result = await pending.WaitAsync(TimeSpan.FromSeconds(10));
                check(result.Cancelled && clock.Elapsed < TimeSpan.FromSeconds(10), "Stop cancels staged generation despite heavy stdout and stderr");
                check(Exited(child), "Stop kills mock fitting child process");
                check(File.ReadAllText(existing) == "previous valid observation product", "Cancelled staged write preserves existing FITS with overwrite ON");
                check(File.ReadAllBytes(csv).SequenceEqual(csvBefore), "Cancellation preserves original dataset CSV");
                check(File.ReadAllText(Path.Combine(request.RecoveryDirectory!, "sky.fib.fits")) == "INCOMPLETE STAGED FITS", "Incomplete product remains confined to recovery directory");
                check(File.Exists(Path.Combine(request.RecoveryDirectory!, "recovery.json")), "Cancellation retains recovery manifest");
            }
            finally { stop.Cancel(); await pending; }
        }
        var after = ReductionProcess.CreateStartInfo(python);
        after.ArgumentList.Add("-c"); after.ArgumentList.Add("print('available again')");
        check((await runner.RunAsync(after, _ => { }, CancellationToken.None)).ExitCode == 0, "Run available after staged cancellation");
    }

    private static bool Exited(int pid)
    {
        try { using var process = Process.GetProcessById(pid); return process.HasExited || process.WaitForExit(3000); }
        catch (ArgumentException) { return true; }
    }
}
