using System.Diagnostics;
using System.Text.Json;
using Tifres.App.Services;
using Tifres.App.ViewModels;

var python = ReductionRequest.ResolvePython(args.Length > 0 ? args[0] : "python");
var directory = Path.Combine(Path.GetTempPath(), "tifres-process-tests-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(directory);
var count = 0;
void Check(bool condition, string message) { if (!condition) throw new Exception(message); Console.WriteLine("PASS " + message); count++; }
void Reject<T>(Action action, string message) where T : Exception
{
    try { action(); } catch (T) { Check(true, message); return; }
    throw new Exception("Expected rejection: " + message);
}
ProcessStartInfo Mock(string code)
{
    var start = ReductionProcess.CreateStartInfo(python);
    start.ArgumentList.Add("-u"); start.ArgumentList.Add("-c"); start.ArgumentList.Add(code);
    return start;
}
try
{
    Check(ReductionRequest.ParseDsno("0001, 900719925474099312345").SequenceEqual(new[] { "0001", "900719925474099312345" }), "DSNO strings retain all digits");
    Reject<ArgumentException>(() => ReductionRequest.ParseDsno("1e3"), "Floating-point DSNO rejected");
    Reject<ArgumentException>(() => ReductionRequest.ParseDsno("01,1"), "Duplicate DSNO rejected");
    var options = ReductionRequest.SerializeOptions("{ \"flgPause\": false, \"fibintwid\": 5 }");
    Check(JsonDocument.Parse(options).RootElement.GetProperty("fibintwid").GetInt32() == 5, "JSON options serialize with native types");
    Reject<ArgumentException>(() => ReductionRequest.SerializeOptions("{\"a\":1,\"a\":2}"), "Duplicate option keys rejected");
    Reject<FileNotFoundException>(() => ReductionRequest.ResolvePython(Path.Combine(directory, "missing-python")), "Missing Python executable rejected");
    var request = new ReductionRequest(python, Path.Combine(directory, "missing.py"), directory, "missing.csv", directory, directory, "mkSpFrames4f", "1", "{}", false);
    Reject<FileNotFoundException>(request.Validate, "Missing launcher/input paths rejected");
    var settingsFile = Path.Combine(directory, "settings.json");
    var settings = new SettingsViewModel(settingsFile) { PythonExecutable = python, ScriptDirectory = directory, CsvPath = "CSV with spaces.csv", RawDirectory = directory, FitsDirectory = directory };
    settings.Save();
    var restored = new SettingsViewModel(settingsFile);
    Check(restored.CsvPath == settings.CsvPath && restored.PythonExecutable == python && restored.FitsDirectory == directory, "Settings persist and restore");
    var runner = new ReductionProcess();
    var messages = new System.Collections.Concurrent.ConcurrentQueue<string>();
    await runner.VerifyPythonAsync(python, messages.Enqueue, CancellationToken.None);
    Check(messages.Any(m => m.StartsWith("Python 3")), "Python executable/version validation");
    var result = await runner.RunAsync(Mock("import sys; print('out'); print('error',file=sys.stderr); sys.exit(7)"), messages.Enqueue, CancellationToken.None);
    Check(result.ExitCode == 7 && !result.Cancelled && messages.Any(m => m.TrimEnd() == "out") && messages.Any(m => m.TrimEnd() == "[stderr] error"), "Exit code and both output streams propagated");
    result = await runner.RunAsync(Mock("print('success')"), messages.Enqueue, CancellationToken.None);
    Check(result.ExitCode == 0 && !result.Cancelled, "Successful process exit");
    using var cancellation = new CancellationTokenSource();
    var childReady = new TaskCompletionSource<int>(TaskCreationOptions.RunContinuationsAsynchronously);
    var protectedFile = Path.Combine(directory, "existing.fits"); File.WriteAllText(protectedFile, "existing product");
    var pending = runner.RunAsync(Mock("import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); print(p.pid,flush=True); time.sleep(120)"),
        line => { if (int.TryParse(line, out var id)) childReady.TrySetResult(id); }, cancellation.Token);
    try
    {
        var childId = await childReady.Task.WaitAsync(TimeSpan.FromSeconds(15));
        try { await new ReductionProcess().RunAsync(Mock("print('conflict')"), messages.Enqueue, CancellationToken.None); throw new Exception("Conflicting process was allowed."); }
        catch (InvalidOperationException) { Check(true, "Conflicting reductions blocked"); }
        cancellation.Cancel();
        result = await pending.WaitAsync(TimeSpan.FromSeconds(15));
        Check(result.Cancelled, "Cancellation terminates process");
        bool childExited;
        try { using var child = Process.GetProcessById(childId); childExited = child.HasExited || child.WaitForExit(5000); }
        catch (ArgumentException) { childExited = true; }
        Check(childExited, "Cancellation terminates child process tree");
        Check(File.ReadAllText(protectedFile) == "existing product", "Cancellation leaves existing output files intact");
    }
    finally { cancellation.Cancel(); await pending; }
    result = await runner.RunAsync(Mock("print('after stop')"), messages.Enqueue, CancellationToken.None);
    Check(result.ExitCode == 0, "Process gate released after cancellation");
    await CancellationRegression.Run(python, directory, Check);
    await StreamFormattingRegression.Run(python, Check);
    Console.WriteLine($"SUCCESS: {count} checks passed.");
}
finally { Directory.Delete(directory, true); }
