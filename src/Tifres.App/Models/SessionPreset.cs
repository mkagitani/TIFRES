using System.Text.Json;
namespace Tifres.App.Models;

public sealed record SessionPreset(string Id, string Name, Dictionary<string,string> Fields,
    Dictionary<string,string> Options, string DefaultDataType = "", string Notes = "", string SourceDsno = "");
public sealed class SessionPresetStore(string path)
{
    public string Path { get; } = path;
    public List<SessionPreset> Load() => File.Exists(Path)
        ? JsonSerializer.Deserialize<List<SessionPreset>>(File.ReadAllText(Path)) ?? throw new InvalidDataException("Empty session preset file.")
        : [];
    public void Save(IEnumerable<SessionPreset> presets)
    {
        var items = presets.ToArray();
        if (items.Any(p => string.IsNullOrWhiteSpace(p.Name)) || items.Select(p=>p.Id).Distinct().Count()!=items.Length)
            throw new InvalidDataException("Presets require names and unique IDs.");
        Directory.CreateDirectory(System.IO.Path.GetDirectoryName(Path)!);
        var temp = Path+"."+Guid.NewGuid().ToString("N")+".tmp";
        try { File.WriteAllText(temp,JsonSerializer.Serialize(items,new JsonSerializerOptions{WriteIndented=true})); File.Move(temp,Path,true); }
        finally { if(File.Exists(temp)) File.Delete(temp); }
    }
    public void Delete(List<SessionPreset> presets, string id, bool confirmed)
    {
        if (!confirmed) throw new InvalidOperationException("Confirm before deleting a session preset.");
        var updated=presets.Where(p=>p.Id!=id).ToList(); Save(updated); presets.RemoveAll(p=>p.Id==id);
    }
}
