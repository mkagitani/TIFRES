using System.Buffers.Binary;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
namespace Tifres.App.Services;

public sealed record CubeMetadata(int Version, int[] Shape, string Dtype,
    [property: JsonPropertyName("byte_order")] string ByteOrder, string Order, int[] Active,
    [property: JsonPropertyName("wavelength_unit")] string WavelengthUnit,
    [property: JsonPropertyName("intensity_unit")] string IntensityUnit, string Filename, string[] Warnings);

public sealed class FitsCube
{
    public CubeMetadata Metadata { get; }
    public double[] Wavelengths { get; }
    private readonly double[] _values;
    private readonly (double Min,double Max) _range;
    public int Samples => Wavelengths.Length;
    public bool[] Active { get; }
    public bool[] Selectable { get; }
    public FitsCube(CubeMetadata metadata, double[] wavelengths, double[] values)
    {
        if (metadata.Shape.Length != 2 || metadata.Shape[0] != 120 || metadata.Shape[1] != wavelengths.Length ||
            wavelengths.Length < 2 || values.Length != checked(120*wavelengths.Length) ||
            wavelengths.Any(v=>!double.IsFinite(v)) || wavelengths.Zip(wavelengths.Skip(1)).Any(p=>p.First>=p.Second) ||
            metadata.Active.Any(i=>i<0 || i>=120) || metadata.Active.Distinct().Count()!=metadata.Active.Length)
            throw new InvalidDataException("Invalid decoded cube dimensions, fiber IDs or wavelength axis.");
        Metadata=metadata; Wavelengths=wavelengths; _values=values;
        Active=new bool[120]; Selectable=new bool[120];
        foreach(var id in metadata.Active) {Active[id]=true; Selectable[id]=Enumerable.Range(0,Samples).Any(i=>double.IsFinite(Value(id,i)));}
        _range=ComputeRange();
    }
    public double Value(int fiber,int sample)=>_values[fiber*Samples+sample];
    public int Nearest(double wavelength)
    {
        var i=Array.BinarySearch(Wavelengths,wavelength);
        if(i>=0)return i; i=~i;
        if(i==0)return 0; if(i==Samples)return Samples-1;
        return wavelength-Wavelengths[i-1]<=Wavelengths[i]-wavelength?i-1:i;
    }
    public double[] Integrate(string mode,double first,double last,CancellationToken token=default)
    {
        var result=Enumerable.Repeat(double.NaN,120).ToArray();
        var begin=mode=="Single"?Nearest(first):Array.FindIndex(Wavelengths,w=>w>=first);
        var end=mode=="Single"?begin:Array.FindLastIndex(Wavelengths,w=>w<=last);
        if(begin<0 || end<begin)return result;
        for(var f=0;f<120;f++)
        {
            token.ThrowIfCancellationRequested();
            if(!Active[f])continue;
            double sum=0; int count=0;
            for(var i=begin;i<=end;i++){var v=Value(f,i);if(double.IsFinite(v)){sum+=v;count++;}}
            if(count>0)result[f]=mode=="Mean"?sum/count:sum;
        }
        return result;
    }
    public double[] Spectrum(IEnumerable<int> fibers,string mode,CancellationToken token=default)
    {
        var ids=fibers.Where(f=>f>=0 && f<120 && Selectable[f]).Distinct().ToArray();
        var result=Enumerable.Repeat(double.NaN,Samples).ToArray();
        for(var i=0;i<Samples;i++)
        {
            if(i%1024==0)token.ThrowIfCancellationRequested();
            double sum=0;int count=0;
            foreach(var f in ids){var v=Value(f,i);if(double.IsFinite(v)){sum+=v;count++;}}
            if(count>0)result[i]=mode=="Mean"?sum/count:sum;
        }
        return result;
    }
    public (double Min,double Max) Range()=>_range;
    private (double Min,double Max) ComputeRange()
    {
        double min=double.PositiveInfinity,max=double.NegativeInfinity;
        foreach(var f in Metadata.Active)for(var i=0;i<Samples;i++){var v=Value(f,i);if(double.IsFinite(v)){min=Math.Min(min,v);max=Math.Max(max,v);}}
        return Expand(min,max);
    }
    public static (double Min,double Max) Expand(double min,double max)
    {
        if(!double.IsFinite(min)||!double.IsFinite(max))return(0,1);
        if(min==max){var d=Math.Max(1,Math.Abs(min)*.01);return(double.IsFinite(min-d)?min-d:min,double.IsFinite(max+d)?max+d:max);}
        return(min,max);
    }
}

public static class FitsCubeLoader
{
    // A single short-lived reader transfers data once. All subsequent viewing is local.
    public static async Task<FitsCube> LoadAsync(string python,string path,CancellationToken token=default)
    {
        if(!File.Exists(path))throw new FileNotFoundException("FITS file not found.",path);
        var start=new ProcessStartInfo(ReductionRequest.ResolvePython(python)){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};
        foreach(var arg in new[]{"-B",Path.Combine(AppContext.BaseDirectory,"python","tifres_viewer.py"),Path.GetFullPath(path)})start.ArgumentList.Add(arg);
        using var process=new Process{StartInfo=start};
        process.Start();
        using var cancel=token.Register(()=>{try{if(!process.HasExited)process.Kill(entireProcessTree:true);}catch(InvalidOperationException){}});
        var error=process.StandardError.ReadToEndAsync();
        try
        {
            var stream=process.StandardOutput.BaseStream;
            var prefix=new byte[4];await stream.ReadExactlyAsync(prefix,token);
            var length=BinaryPrimitives.ReadInt32LittleEndian(prefix);
            if(length<=0 || length>1_000_000)throw new InvalidDataException("Invalid viewer metadata length.");
            var json=new byte[length];await stream.ReadExactlyAsync(json,token);
            var meta=JsonSerializer.Deserialize<CubeMetadata>(json,new JsonSerializerOptions{PropertyNameCaseInsensitive=true})??throw new InvalidDataException("Missing viewer metadata.");
            if(meta.Version!=1 || meta.Dtype!="float64" || meta.ByteOrder!="little" || meta.Order!="fiber,wavelength" ||
                meta.Shape.Length!=2 || meta.Shape[0]!=120 || meta.Shape[1]<2 || (long)meta.Shape[1]*120*8>1_000_000_000)
                throw new InvalidDataException("Unsupported viewer binary protocol.");
            var wave=await ReadDoubles(stream,meta.Shape[1],token);
            var data=await ReadDoubles(stream,checked(120*meta.Shape[1]),token);
            if(await stream.ReadAsync(new byte[1],token)!=0)throw new InvalidDataException("Unexpected viewer payload.");
            await process.WaitForExitAsync(token);
            if(process.ExitCode!=0)throw new InvalidDataException(await error);
            token.ThrowIfCancellationRequested();
            return new FitsCube(meta,wave,data);
        }
        catch(Exception ex)
        {
            try{if(!process.HasExited)process.Kill(entireProcessTree:true);}catch(InvalidOperationException){}
            await process.WaitForExitAsync();
            var detail=await error;
            token.ThrowIfCancellationRequested();
            throw new InvalidDataException(string.IsNullOrWhiteSpace(detail)?ex.Message:detail.Trim(),ex);
        }
    }
    private static async Task<double[]> ReadDoubles(Stream stream,int count,CancellationToken token)
    {
        var data=new double[count];
        // Bounded staging buffer, not an additional cube-sized byte array.
        var buffer=new byte[65536];var offset=0;
        while(offset<count)
        {
            int n=Math.Min(buffer.Length/8,count-offset);
            await stream.ReadExactlyAsync(buffer.AsMemory(0,n*8),token);
            for(int j=0;j<n;j++)data[offset+j]=BinaryPrimitives.ReadDoubleLittleEndian(buffer.AsSpan(j*8,8));
            offset+=n;
        }
        return data;
    }
    public static string[] ResolveProducts(string root,string filename,int width)
    {
        if(width<1 || string.IsNullOrWhiteSpace(root) || string.IsNullOrWhiteSpace(filename) || !filename.EndsWith(".fits",StringComparison.Ordinal))
            throw new InvalidOperationException("Set the FITS directory and select a dataset with a valid FILENAME and fibintwid.");
        var basePath=Path.GetFullPath(Path.Combine(root,filename.Replace('\\',Path.DirectorySeparatorChar).Replace('/',Path.DirectorySeparatorChar)));
        var relative=Path.GetRelativePath(Path.GetFullPath(root),basePath);
        if(Path.IsPathRooted(relative)||relative==".."||relative.StartsWith(".."+Path.DirectorySeparatorChar))throw new InvalidOperationException("Dataset product escapes the FITS directory.");
        return new[]{"wc","dcb"}.Select(s=>Path.GetFullPath(Path.Combine(root,filename.Replace(".fits",$".w{width}{s}.fits").Replace('\\',Path.DirectorySeparatorChar).Replace('/',Path.DirectorySeparatorChar)))).Where(File.Exists).ToArray();
    }
}
