using System.Text;
using System.Text.Json;

namespace Tifres.App.Services;

public sealed record ProductOutput(string Path, string Status);
public sealed record ProductDependency(string Role, string Path, string Status, string[] Producers, string Reason, string? Node);
public sealed record ProductNode(string Id, string Dsno, string Step, string Label, string Status,
    ProductOutput[] Outputs, ProductDependency[] Dependencies, string[] Reasons)
{
    public string Heading => $"{Label} · DSNO {Dsno} · {Status}";
    public string ExpectedFiles => Outputs.Length == 0 ? "Output contract unavailable" : string.Join("\n", Outputs.Select(p => $"{p.Path} ({p.Status})"));
    public string Explanation => string.Join("\n", Reasons);
    public string Relationships => string.Join("\n", Dependencies.Select(d =>
        $"DSNO {Dsno} → {d.Role} → {(d.Producers.Length == 0 ? "external / unresolved producer" : "DSNO " + string.Join(", ", d.Producers))}\n{d.Path} · {d.Status}" +
        (string.IsNullOrWhiteSpace(d.Reason) ? "" : "\n" + d.Reason)));
}
public sealed record ProductReport(int Version, string Dsno, ProductNode[] Steps, ProductNode[] Nodes, string[] Notes, int HistoricalRuns = 0, int WarningCount = 0);

public sealed record StatusRequest(string Python, string ScriptDirectory, string Csv, string RawDirectory,
    string FitsDirectory, string Dsno, Dictionary<string, string> Options);

public static class ReductionStatus
{
    public static async Task<ProductReport> InspectAsync(StatusRequest request, CancellationToken cancellation)
    {
        var start = ReductionProcess.CreateStartInfo(ReductionRequest.ResolvePython(request.Python));
        var script = Path.Combine(AppContext.BaseDirectory, "python", "tifres_status.py");
        if (!File.Exists(script)) throw new FileNotFoundException("Status inspector is missing.", script);
        foreach (var path in new[] { request.Csv, Path.Combine(request.ScriptDirectory, "cfg.py") })
            if (!File.Exists(path)) throw new FileNotFoundException("Required status input is missing.", path);
        if (new[] { request.RawDirectory, request.FitsDirectory }.Any(string.IsNullOrWhiteSpace))
            throw new ArgumentException("Set raw CCD and FITS output directories in Settings.");
        foreach (var arg in new[] { "-B", script, "--script-dir", Path.GetFullPath(request.ScriptDirectory), "--csv", Path.GetFullPath(request.Csv),
                     "--raw-dir", Path.GetFullPath(request.RawDirectory), "--fits-dir", Path.GetFullPath(request.FitsDirectory),
                     "--dsno", request.Dsno, "--options-json", JsonSerializer.Serialize(request.Options) }) start.ArgumentList.Add(arg);
        var stdout = new StringBuilder(); var stderr = new StringBuilder();
        var sync = new object();
        var result = await new ReductionProcess().RunWithOutputAsync(start, part =>
        {
            lock (sync)
            {
                var target = part.IsError ? stderr : stdout;
                if (target.Length > 16_000_000) throw new InvalidDataException("Status response exceeds size limit.");
                target.Append(part.Text);
            }
        }, cancellation).ConfigureAwait(false);
        cancellation.ThrowIfCancellationRequested();
        if (result.Cancelled) throw new OperationCanceledException(cancellation);
        if (result.ExitCode != 0) throw new InvalidOperationException($"Status inspection failed (exit {result.ExitCode}): {stderr}");
        return JsonSerializer.Deserialize<ProductReport>(stdout.ToString(), new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
            ?? throw new InvalidDataException("Empty status report.");
    }
}
