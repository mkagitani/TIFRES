using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Tifres.App.Services;

public sealed record ReductionRequest(string Python, string Launcher, string ScriptDirectory,
    string Csv, string RawDirectory, string FitsDirectory, string Step, string Dsno,
    string OptionsJson, bool Overwrite, string PngDirectory = "", string? RunId = null)
{
    public static readonly string[] Steps = ["mkSpFrames4f", "mkFibFit4c", "mkFibSpec4d", "mkWavMap4d", "mkWcalSpec4d"];
    public static string[] ParseDsno(string value)
    {
        var tokens = Regex.Split(value.Trim(), @"[,\s]+");
        if (tokens.Length == 0 || tokens.Any(t => !Regex.IsMatch(t, "^[0-9]+$")))
            throw new ArgumentException("DSNO must contain decimal integer identifiers separated by commas or spaces.");
        if (tokens.Select(t => t.TrimStart('0')).Distinct(StringComparer.Ordinal).Count() != tokens.Length)
            throw new ArgumentException("Duplicate DSNO arguments.");
        return tokens;
    }
    public static string SerializeOptions(string value)
    {
        using var json = JsonDocument.Parse(value);
        if (json.RootElement.ValueKind != JsonValueKind.Object) throw new ArgumentException("Options must be a JSON object.");
        var keys = new HashSet<string>(StringComparer.Ordinal);
        foreach (var property in json.RootElement.EnumerateObject())
            if (!keys.Add(property.Name)) throw new ArgumentException($"Duplicate option: {property.Name}");
        return JsonSerializer.Serialize(json.RootElement);
    }
    public static string EditableOptions(string value)
    {
        var options = System.Text.Json.Nodes.JsonNode.Parse(SerializeOptions(value))!.AsObject();
        options.Remove("overwrite"); // Reserved for the checkbox, never an independent editable option.
        return options.ToJsonString();
    }
    public string EffectiveOptionsJson()
    {
        var options = System.Text.Json.Nodes.JsonNode.Parse(EditableOptions(OptionsJson))!.AsObject();
        if (Step is "mkSpFrames4f" or "mkFibSpec4d" or "mkWcalSpec4d")
            options["overwrite"] = Overwrite;
        return options.ToJsonString();
    }
    public void Validate()
    {
        if (!Steps.Contains(Step)) throw new ArgumentException("Unsupported reduction step.");
        ResolvePython(Python);
        foreach (var path in new[] { Launcher, Csv, Path.Combine(ScriptDirectory, "cfg.py"), Path.Combine(ScriptDirectory, Step + ".py") })
            if (!File.Exists(path)) throw new FileNotFoundException("Required file does not exist.", path);
        foreach (var path in new[] { ScriptDirectory, RawDirectory, FitsDirectory })
            if (!Directory.Exists(path)) throw new DirectoryNotFoundException($"Directory does not exist: {path}");
        ParseDsno(Dsno); SerializeOptions(OptionsJson);
    }
    public static string ResolvePython(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) throw new FileNotFoundException("Choose a Python executable in Settings.");
        if (Path.IsPathRooted(value) || value.Contains(Path.DirectorySeparatorChar) || value.Contains(Path.AltDirectorySeparatorChar))
        {
            if (File.Exists(value)) return Path.GetFullPath(value);
        }
        else
        {
            foreach (var directory in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
            {
                if (string.IsNullOrWhiteSpace(directory)) continue;
                var path = Path.Combine(directory.Trim('"'), value);
                if (File.Exists(path)) return path;
                if (OperatingSystem.IsWindows() && File.Exists(path + ".exe")) return path + ".exe";
            }
        }
        throw new FileNotFoundException($"Python executable not found: {value}");
    }
    public string? RecoveryDirectory => RunId == null ? null : Path.Combine(Path.GetFullPath(FitsDirectory), ".tifres-runs", RunId);
    public ProcessStartInfo StartInfo()
    {
        Validate();
        var start = ReductionProcess.CreateStartInfo(ResolvePython(Python));
        foreach (var arg in new[] { "-u", Path.GetFullPath(Launcher), "--script-dir", Path.GetFullPath(ScriptDirectory),
            "--csv", Path.GetFullPath(Csv), "--raw-dir", Path.GetFullPath(RawDirectory), "--fits-dir", Path.GetFullPath(FitsDirectory),
            "--step", Step, "--options-json", EffectiveOptionsJson(), "--dsno" }) start.ArgumentList.Add(arg);
        foreach (var id in ParseDsno(Dsno)) start.ArgumentList.Add(id);
        if (Overwrite) start.ArgumentList.Add("--overwrite");
        if (!string.IsNullOrWhiteSpace(PngDirectory))
        {
            start.ArgumentList.Add("--png-dir");
            start.ArgumentList.Add(Path.GetFullPath(PngDirectory));
        }
        if (RunId != null)
        {
            start.ArgumentList.Add("--run-id"); start.ArgumentList.Add(RunId);
            start.Environment["TIFRES_CANCEL_FILE"] = Path.Combine(RecoveryDirectory!, "cancel.request");
        }
        return start;
    }
}

public sealed record ProcessOutput(string Text, bool IsError = false);

public sealed record ProcessResult(int ExitCode, bool Cancelled);

public sealed class ReductionProcess
{
    private static readonly SemaphoreSlim Gate = new(1, 1);
    public static ProcessStartInfo CreateStartInfo(string executable) => new(executable)
    {
        UseShellExecute = false, CreateNoWindow = true,
        RedirectStandardOutput = true, RedirectStandardError = true, RedirectStandardInput = true,
        StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
        Environment = { ["PYTHONUTF8"] = "1", ["PYTHONUNBUFFERED"] = "1", ["PYTHONDONTWRITEBYTECODE"] = "1", ["MPLBACKEND"] = "Agg" }
    };

    public Task<ProcessResult> RunAsync(ProcessStartInfo start, Action<string> log, CancellationToken cancellation) =>
        RunWithOutputAsync(start, chunk => log((chunk.IsError ? "[stderr] " : "") + chunk.Text), cancellation);

    public Task<ProcessResult> RunWithOutputAsync(ProcessStartInfo start, Action<ProcessOutput> output, CancellationToken cancellation) =>
        Task.Run(() => RunWorkerAsync(start, output, cancellation), CancellationToken.None);

    private async Task<ProcessResult> RunWorkerAsync(ProcessStartInfo start, Action<ProcessOutput> output, CancellationToken cancellation)
    {
        if (!await Gate.WaitAsync(0, cancellation).ConfigureAwait(false))
            throw new InvalidOperationException("A reduction process is already running.");
        try
        {
            cancellation.ThrowIfCancellationRequested();
            ProcessTree.Prepare(start);
            using var tree = new ProcessTree();
            using var process = new Process { StartInfo = start };
            if (!process.Start()) throw new InvalidOperationException("Could not start Python.");
            using var drainCancellation = new CancellationTokenSource();
            Task streams = Task.CompletedTask;
            try
            {
                tree.Attach(process);
                process.StandardInput.Close();
                streams = Task.WhenAll(Pump(process.StandardOutput, false, output, drainCancellation.Token),
                                       Pump(process.StandardError, true, output, drainCancellation.Token));
                await process.WaitForExitAsync(cancellation).ConfigureAwait(false);
                // Parent exit is not pipe EOF: descendants can still own the handles.
                await streams.WaitAsync(TimeSpan.FromSeconds(5), cancellation).ConfigureAwait(false);
                return new ProcessResult(process.ExitCode, cancellation.IsCancellationRequested);
            }
            catch (OperationCanceledException) when (cancellation.IsCancellationRequested)
            {
                if (start.Environment.TryGetValue("TIFRES_CANCEL_FILE", out var marker) && marker != null && Directory.Exists(Path.GetDirectoryName(marker)))
                {
                    try { File.WriteAllText(marker, "Cancelled by TIFRES"); }
                    catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { output(new ProcessOutput("Cancellation marker could not be written: " + ex.Message + "\n", true)); }
                }
                tree.Terminate(process);
                await process.WaitForExitAsync(CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(10)).ConfigureAwait(false);
                await DrainAsync(streams, drainCancellation).ConfigureAwait(false);
                return new ProcessResult(process.ExitCode, true);
            }
            catch
            {
                tree.Terminate(process);
                await process.WaitForExitAsync(CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(10)).ConfigureAwait(false);
                await DrainAsync(streams, drainCancellation).ConfigureAwait(false);
                throw;
            }
        }
        finally { Gate.Release(); }
    }

    private static async Task DrainAsync(Task streams, CancellationTokenSource stop)
    {
        try { await streams.WaitAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false); }
        catch (TimeoutException)
        {
            stop.Cancel();
            try { await streams.WaitAsync(TimeSpan.FromSeconds(1)).ConfigureAwait(false); }
            catch (OperationCanceledException) { }
            catch (TimeoutException) { }
        }
    }

    private static async Task Pump(StreamReader reader, bool isError, Action<ProcessOutput> output, CancellationToken cancellation)
    {
        var buffer = new char[4096];
        int count;
        while ((count = await reader.ReadAsync(buffer.AsMemory(), cancellation).ConfigureAwait(false)) != 0)
        {
            // A read is a transport chunk, not a line. Preserve every character.
            output(new ProcessOutput(new string(buffer, 0, count), isError));
        }
    }
    public async Task VerifyPythonAsync(string executable, Action<string> log, CancellationToken cancellation)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        timeout.CancelAfter(TimeSpan.FromSeconds(15));
        var start = CreateStartInfo(ReductionRequest.ResolvePython(executable));
        start.ArgumentList.Add("-c");
        start.ArgumentList.Add("import sys; print('Python ' + sys.version); sys.exit(0 if sys.version_info >= (3,10) else 2)");
        var result = await RunAsync(start, log, timeout.Token);
        cancellation.ThrowIfCancellationRequested();
        if (result.Cancelled) throw new TimeoutException("Python validation timed out.");
        if (result.ExitCode != 0) throw new InvalidOperationException($"Python validation failed (exit {result.ExitCode}); Python 3.10+ is required.");
    }
}
