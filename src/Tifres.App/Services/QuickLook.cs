using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using Tifres.App.Models;
namespace Tifres.App.Services;

public sealed record QuickRaw(string Origin, string[] Files, bool Ambiguous, string ObservingDate,
    Dictionary<string,string> Metadata, string[] Notes, string Fingerprint);
public sealed record QuickStep(string Step, bool Reuse, string[] Outputs);
public sealed record QuickPlan(QuickStep[] Steps, string Viewer, string[] Calibrations);
public sealed record QuickViewer(string Path);
public sealed record QuickResult(bool Completed, bool Cancelled, string ViewerState);
public static class QuickLook
{
    public static readonly string[] Steps=["mkSpFrames4f","mkFibSpec4d","mkWcalSpec4d"];
    public static readonly string[] FixedFields=["DARKFRAME","WLFLAT","WLFLAT2","SKYFLAT","WAVMAP","FIBINTWID",
        "FIBX0","FIBX1","FIBXWID","YFIBRANGE","NFIBXY","IFIBIACT","WAVSHIFT"];
    public static Dictionary<string,string> Row(DatasetCsv csv, Dictionary<string,string> values) =>
        csv.Columns.ToDictionary(c=>c,c=>values.GetValueOrDefault(c,""),StringComparer.Ordinal);
    public static void ValidateRow(DatasetCsv csv, Dictionary<string,string> row)
    {
        if (!row.GetValueOrDefault("FILENAME","").EndsWith(".fits",StringComparison.Ordinal)) throw new InvalidDataException("FILENAME must end in .fits.");
        var filename=row["FILENAME"].Replace('\\','/');
        if(Path.IsPathRooted(filename)||filename.Split('/').Contains("..")||filename.Contains(':'))throw new InvalidDataException("FILENAME must stay relative to FITS directory.");
        var nameIndex=Array.IndexOf(csv.Columns,"FILENAME");
        if(csv.Rows.Any(r=>string.Equals(r[nameIndex].Replace('\\','/'),filename,StringComparison.OrdinalIgnoreCase)))
            throw new InvalidDataException("FILENAME already belongs to a dataset. Use the manual Operations tab for existing datasets.");
        // Conservative collision guard for calibration references anywhere in this CSV.
        // This is an ownership check, not a replacement for Python dependency resolution.
        static string Stem(string name) => Regex.Replace(name.Replace('\\','/'), @"(?:\.w[0-9]+(?:fsp|wmp|wc|img)|\.wmp|\.fib|\.m)?\.fits$", "", RegexOptions.IgnoreCase);
        var calibrationColumns=new[]{"DARKFRAME","WLFLAT","WLFLAT2","SKYFLAT","WAVMAP"}.Select(c=>Array.IndexOf(csv.Columns,c)).Where(i=>i>=0).ToArray();
        if(csv.Rows.Any(r=>calibrationColumns.Any(i=>!string.IsNullOrWhiteSpace(r[i])&&string.Equals(Stem(r[i]),Stem(filename),StringComparison.OrdinalIgnoreCase))))
            throw new InvalidDataException("FILENAME is reserved by an existing calibration reference; Quick Look cannot regenerate calibrations.");
        var check=new DatasetCsv(csv.Columns,[..csv.Rows,csv.Columns.Select(c=>row.GetValueOrDefault(c,"")).ToArray()]);
        check.Validate();
        if(string.IsNullOrWhiteSpace(row.GetValueOrDefault("ORIGIN")))throw new InvalidDataException("ORIGIN is required.");
    }
    public static string Register(string path, Dictionary<string,string> row, byte[] expectedCsv)
    {
        if(!File.ReadAllBytes(path).SequenceEqual(expectedCsv))throw new InvalidOperationException("CSV changed since preview; preview again.");
        // Respect the launcher's cross-process CSV lock for the full read/validate/replace.
        using var guard=new FileStream(path+".reduction.lock",FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);
        var csv=DatasetCsv.Load(path); ValidateRow(csv,row);
        if(!File.ReadAllBytes(path).SequenceEqual(expectedCsv))throw new InvalidOperationException("CSV changed since preview.");
        csv.Rows.Add(csv.Columns.Select(c=>row.GetValueOrDefault(c,"")).ToArray());
        return csv.Save(path);
    }
    public static string ProposeDsno(DatasetCsv csv, string observingDate, string datatype)
    {
        if(!DateOnly.TryParseExact(observingDate,"yyyy-MM-dd",CultureInfo.InvariantCulture,DateTimeStyles.None,out var date))return "";
        var prefix=date.ToString("yyMMdd",CultureInfo.InvariantCulture);
        var di=Array.IndexOf(csv.Columns,"DSNO"); var ti=Array.IndexOf(csv.Columns,"DATATYPE");
        var all=csv.Rows.Select(r=>r[di]).ToHashSet(StringComparer.Ordinal);
        // Only extend an observed same-date, same-type nine-digit series. No invented type ranges.
        var ids=csv.Rows.Where(r=>r[ti].Trim()==datatype.Trim() && Regex.IsMatch(r[di],@"^\d{9}$") && r[di].StartsWith(prefix,StringComparison.Ordinal)).Select(r=>r[di]).ToArray();
        if(ids.Length==0)return "";
        var next=ids.Max(id=>int.Parse(id[6..],CultureInfo.InvariantCulture))+1;
        if(next>999)return "";
        var candidate=prefix+next.ToString("D3",CultureInfo.InvariantCulture);
        return all.Any(id=>id.TrimStart('0')==candidate.TrimStart('0'))?"":candidate;
    }
    public static string ProposeFilename(DatasetCsv csv,string origin)
    {
        // This proposal is offered only when this transformation is evidenced in the loaded CSV.
        var oi=Array.IndexOf(csv.Columns,"ORIGIN"); var fi=Array.IndexOf(csv.Columns,"FILENAME");
        if(oi<0||!origin.EndsWith("_*.fits",StringComparison.Ordinal))return "";
        var evidenced=csv.Rows.Any(r=>r[oi].EndsWith("_*.fits",StringComparison.Ordinal)&&r[fi]==r[oi][..^7]+".sp.fits");
        return evidenced ? origin[..^7]+".sp.fits":"";
    }
    public static async Task<T> InspectAsync<T>(string python,object request,CancellationToken token)
    {
        var start=ReductionProcess.CreateStartInfo(ReductionRequest.ResolvePython(python));
        foreach(var arg in new[]{"-u",Path.Combine(AppContext.BaseDirectory,"python","tifres_quicklook.py"),"--request-json",JsonSerializer.Serialize(request)})start.ArgumentList.Add(arg);
        var output=new System.Text.StringBuilder();var errors=new System.Text.StringBuilder();
        var result=await new ReductionProcess().RunWithOutputAsync(start,p=>{lock(output){(p.IsError?errors:output).Append(p.Text);}},token);
        token.ThrowIfCancellationRequested();
        if(result.Cancelled)throw new OperationCanceledException(token);
        if(result.ExitCode!=0)throw new InvalidOperationException(errors.ToString());
        return JsonSerializer.Deserialize<T>(output.ToString(),new JsonSerializerOptions{PropertyNameCaseInsensitive=true})??throw new InvalidDataException("Empty Quick Look inspection.");
    }
    public static async Task<QuickResult> ExecuteAsync(QuickPlan plan, Func<QuickStep,CancellationToken,Task<ProcessResult>> run,
        Func<string,CancellationToken,Task<bool>> open, Action<string,string> progress,CancellationToken token)
    {
        if(!plan.Steps.Select(p=>p.Step).SequenceEqual(Steps))throw new InvalidDataException("Invalid Quick Look sequence.");
        string current="";
        try
        {
            foreach(var step in plan.Steps)
            {
                current=step.Step;token.ThrowIfCancellationRequested();
                if(step.Reuse){progress(current,"Skipped (valid products)");continue;}
                progress(current,"Running");
                var result=await run(step,token);
                if(result.Cancelled||token.IsCancellationRequested||result.ExitCode==130)throw new OperationCanceledException(token);
                if(result.ExitCode!=0){progress(current,"Failed");return new(false,false,"Waiting");}
                progress(current,"OK");
            }
            token.ThrowIfCancellationRequested(); current="Viewer";progress(current,"Opening");
            bool opened;
            try{opened=await open(plan.Viewer,token);}
            catch(OperationCanceledException){throw;}
            catch{opened=false;}
            token.ThrowIfCancellationRequested();
            progress(current,opened?"Opened":"Load failed (reduction completed)");
            return new(true,false,opened?"Opened":"Load failed");
        }
        catch(OperationCanceledException){progress(current,"Cancelled");return new(false,true,"Waiting");}
        catch{progress(current,"Failed");throw;}
    }
}
