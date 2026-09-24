using System.Text;
using Tifres.App.Services;

internal static class StreamFormattingRegression
{
    public static async Task Run(string python, Action<bool, string> check)
    {
        var start = ReductionProcess.CreateStartInfo(python);
        start.ArgumentList.Add("-u"); start.ArgumentList.Add("-c");
        start.ArgumentList.Add("""
import sys,time
sys.stdout.reconfigure(newline='')
sys.stderr.reconfigure(newline='')
for _ in range(5):
    print('.',end='',flush=True); time.sleep(.04)
print(' tail',end='',flush=True)
sys.stdout.write('\n\n10%\r20%\r100%\r\npartial'); sys.stdout.flush()
sys.stderr.write('error'); sys.stderr.flush(); time.sleep(.04)
sys.stderr.write(' details\n'); sys.stderr.flush()
""");
        var stdout = new StringBuilder(); var stderr = new StringBuilder();
        var sync = new object(); var chunks = 0;
        var runner = new ReductionProcess();
        var result = await runner.RunWithOutputAsync(start, chunk =>
        {
            lock (sync) { (chunk.IsError ? stderr : stdout).Append(chunk.Text); chunks++; }
        }, CancellationToken.None);
        check(result.ExitCode == 0 && !result.Cancelled, "Formatting mock exits successfully");
        check(stdout.ToString() == "..... tail\n\n10%\r20%\r100%\r\npartial", "Raw stdout preserves dots, end='', blank lines, CR, LF and partial lines");
        check(stderr.ToString() == "error details\n", "Raw stderr preserves fragments and newline without repeated prefixes");
        check(chunks > 1, "Regression exercises multiple asynchronous output chunks");
        var buffer = new ConsoleLogBuffer();
        foreach (var c in stdout.ToString()) buffer.Append(c.ToString());
        check(buffer.Text == "..... tail\n\n100%\npartial", "Display formatting is independent of chunk boundaries and updates CR progress");
        buffer.Append(new string('.', 80_000));
        check(buffer.Text.Length < 21_000 && buffer.Text.StartsWith("[Earlier log truncated]"), "Continuous partial output stays bounded without synthetic newlines");

        start = ReductionProcess.CreateStartInfo(python);
        start.ArgumentList.Add("-u"); start.ArgumentList.Add("-c");
        start.ArgumentList.Add("import sys,time\nwhile True:\n sys.stdout.write('.'*512); sys.stdout.flush(); time.sleep(.001)");
        using var stop = new CancellationTokenSource();
        var ready = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var observed = new StringBuilder();
        var pending = runner.RunWithOutputAsync(start, chunk =>
        {
            lock (observed) { if (observed.Length < 20_000) observed.Append(chunk.Text); }
            ready.TrySetResult();
        }, stop.Token);
        try
        {
            await ready.Task.WaitAsync(TimeSpan.FromSeconds(10));
            stop.Cancel();
            result = await pending.WaitAsync(TimeSpan.FromSeconds(10));
            check(result.Cancelled, "Cancellation terminates continuous stdout without line endings");
            check(observed.Length > 0 && observed.ToString().All(c => c == '.'), "Cancellation does not inject line endings into process output");
        }
        finally { stop.Cancel(); await pending; }
    }
}
