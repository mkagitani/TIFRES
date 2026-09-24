using System.Text;

namespace Tifres.App.Models;

public sealed class DatasetCsv
{
    public string[] Columns { get; }
    public List<string[]> Rows { get; }
    private readonly HashSet<string[]> _separators;
    public DatasetCsv(string[] columns, List<string[]> rows)
    {
        (Columns, Rows) = (columns, rows);
        _separators = rows.Where(r => r.All(string.IsNullOrEmpty)).ToHashSet();
    }
    public bool IsSeparator(string[] row) => _separators.Contains(row) && row.All(string.IsNullOrEmpty);

    public static DatasetCsv Load(string path)
    {
        var records = Parse(File.ReadAllText(path, new UTF8Encoding(false, true)));
        if (records.Count == 0) throw new InvalidDataException("CSV is empty.");
        var columns = records[0];
        if (columns.Distinct(StringComparer.Ordinal).Count() != columns.Length || columns.Any(string.IsNullOrWhiteSpace))
            throw new InvalidDataException("Column names must be nonempty and unique.");
        foreach (var name in new[] { "DSNO", "DATATYPE", "FILENAME" })
            if (!columns.Contains(name)) throw new InvalidDataException($"Missing required column: {name}");
        var rows = records.Skip(1).ToList();
        if (rows.Any(r => r.Length != columns.Length)) throw new InvalidDataException("A CSV row has a different number of fields than the header.");
        return new DatasetCsv(columns, rows);
    }

    public void Validate()
    {
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (var row in Rows)
        {
            if (IsSeparator(row)) continue;
            if (row.Length != Columns.Length) throw new InvalidDataException("Invalid row width.");
            foreach (var name in new[] { "DSNO", "DATATYPE", "FILENAME" })
                if (string.IsNullOrWhiteSpace(row[Array.IndexOf(Columns, name)]))
                    throw new InvalidDataException($"{name} is required for every dataset.");
            var id = row[Array.IndexOf(Columns, "DSNO")];
            if (!id.All(c => c >= '0' && c <= '9')) throw new InvalidDataException($"DSNO '{id}' must contain digits only.");
            // Compare integer identities without converting through floating point.
            var key = id.TrimStart('0');
            if (!ids.Add(key)) throw new InvalidDataException($"Duplicate DSNO: {id}");
        }
    }

    public string Save(string path)
    {
        Validate();
        path = Path.GetFullPath(path);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        var backup = path + "." + DateTime.UtcNow.ToString("yyyyMMddTHHmmssfffffffZ") + ".bak";
        try
        {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write))
            {
                using (var writer = new StreamWriter(stream, new UTF8Encoding(false), leaveOpen: true))
                    foreach (var row in new[] { Columns }.Concat(Rows)) writer.WriteLine(string.Join(",", row.Select(Escape)));
                stream.Flush(true);
            }
            var verified = Load(temporary);
            verified.Validate();
            if (!Columns.SequenceEqual(verified.Columns) || !Rows.Zip(verified.Rows).All(p => p.First.SequenceEqual(p.Second)) || Rows.Count != verified.Rows.Count)
                throw new InvalidDataException("CSV verification failed.");
            if (File.Exists(path))
            {
                File.Copy(path, backup, false);
                File.Move(temporary, path, true);
            }
            else File.Move(temporary, path);
            return backup;
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private static string Escape(string value) => value.IndexOfAny([',', '"', '\r', '\n']) >= 0 ? "\"" + value.Replace("\"", "\"\"") + "\"" : value;

    private static List<string[]> Parse(string text)
    {
        var records = new List<string[]>();
        var row = new List<string>();
        var field = new StringBuilder();
        bool quoted = false, closed = false, started = false;
        for (int i = 0; i < text.Length; i++)
        {
            char c = text[i];
            started = true;
            if (quoted)
            {
                if (c == '"')
                {
                    if (i + 1 < text.Length && text[i + 1] == '"') { field.Append('"'); i++; }
                    else { quoted = false; closed = true; }
                }
                else field.Append(c);
            }
            else if (c == ',' || c == '\r' || c == '\n')
            {
                row.Add(field.ToString()); field.Clear(); closed = false;
                if (c != ',')
                {
                    records.Add(row.ToArray()); row.Clear(); started = false;
                    if (c == '\r' && i + 1 < text.Length && text[i + 1] == '\n') i++;
                }
            }
            else if (closed) throw new InvalidDataException("Unexpected character after a quoted field.");
            else if (c == '"')
            {
                if (field.Length != 0) throw new InvalidDataException("Unexpected quote in CSV field.");
                quoted = true;
            }
            else field.Append(c);
        }
        if (quoted) throw new InvalidDataException("Unterminated quoted field.");
        if (started) { row.Add(field.ToString()); records.Add(row.ToArray()); }
        return records;
    }
}

