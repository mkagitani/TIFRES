namespace Tifres.App.ViewModels;

// Presentation grouping only: fields still reference the original CSV cells.
public sealed record ParameterEditorRow(DatasetField First, DatasetField? Second)
{
    public bool HasSecond => Second != null;
    public int FirstSpan => HasSecond ? 1 : 3;

    public static IReadOnlyList<ParameterEditorRow> Create(IReadOnlyList<DatasetField> fields)
    {
        var rows = new List<ParameterEditorRow>();
        DatasetField? pending = null;
        foreach (var field in fields)
        {
            var wide = field.Name is "FILENAME" or "ORIGIN" or "DARKFRAME" or "WAVMAP" or "NOTE"
                || field.Name.Contains("FLAT") || field.Name.Contains("PATH") || field.Name.Contains("WAVS")
                || field.Name is "NFIBXY" or "IFIBIACT" || field.Value.Contains(',') || field.Value.Length > 24;
            if (wide)
            {
                if (pending != null) { rows.Add(new(pending, null)); pending = null; }
                rows.Add(new(field, null));
            }
            else if (pending == null) pending = field;
            else { rows.Add(new(pending, field)); pending = null; }
        }
        if (pending != null) rows.Add(new(pending, null));
        return rows;
    }
}
