using System.Collections.ObjectModel;
using System.Windows.Input;
using Tifres.App.Models;
namespace Tifres.App.ViewModels;

public sealed class ActionCommand(Action action) : ICommand
{
    public bool CanExecute(object? parameter) => true;
    public void Execute(object? parameter) => action();
    public event EventHandler? CanExecuteChanged { add { } remove { } }
}
public sealed class DatasetField(string name, string[] row, int index, Action changed) : ViewModelBase
{
    public string Name { get; } = name;
    public string Value { get => row[index]; set { value ??= ""; if (SetProperty(ref row[index], value)) changed(); } }
}
public sealed record ParameterGroup(string Name, IReadOnlyList<DatasetField> Fields)
{
    public IReadOnlyList<ParameterEditorRow> Rows { get; } = ParameterEditorRow.Create(Fields);
}
public sealed class DatasetRow : ViewModelBase
{
    private string _dsno = "", _type = "", _file = "";
    public string[] Values { get; }
    public string Dsno { get => _dsno; private set => SetProperty(ref _dsno, value); }
    public string DataType { get => _type; private set => SetProperty(ref _type, value); }
    public string Filename { get => _file; private set => SetProperty(ref _file, value); }
    public DatasetRow(string[] values, string[] columns) { Values = values; Refresh(columns); }
    public void Refresh(string[] columns)
    {
        Dsno = Values[Array.IndexOf(columns, "DSNO")];
        DataType = Values[Array.IndexOf(columns, "DATATYPE")];
        Filename = Values[Array.IndexOf(columns, "FILENAME")];
    }
}
public sealed class DatasetViewModel : ViewModelBase
{
    private DatasetCsv? _document;
    private string _path = "No CSV opened", _search = "", _message = "Required: DSNO, DATATYPE, FILENAME. Other fields may be empty.";
    private bool _dirty;
    private DatasetRow? _selected;
    private IReadOnlyList<ParameterGroup> _groups = [];
    private readonly List<DatasetRow> _rows = [];
    public ObservableCollection<DatasetRow> FilteredRows { get; } = [];
    public string FilePath { get => _path; private set => SetProperty(ref _path, value); }
    public string Message { get => _message; set => SetProperty(ref _message, value); }
    public bool IsDirty { get => _dirty; private set => SetProperty(ref _dirty, value); }
    public string Search { get => _search; set { if (SetProperty(ref _search, value)) Filter(); } }
    public IReadOnlyList<ParameterGroup> Groups { get => _groups; private set => SetProperty(ref _groups, value); }
    public DatasetRow? Selected
    {
        get => _selected;
        set
        {
            if (!SetProperty(ref _selected, value)) return;
            Groups = value == null || _document == null ? [] : _document.Columns
                .Select((name, index) => new DatasetField(name, value.Values, index, () => { IsDirty = true; value.Refresh(_document.Columns); }))
                .GroupBy(f => Category(f.Name)).Select(g => new ParameterGroup(g.Key, g.ToList())).ToList();
        }
    }
    public ICommand SaveCommand { get; }
    public ICommand AddCommand { get; }
    public ICommand DuplicateCommand { get; }
    public DatasetViewModel()
    {
        SaveCommand = new ActionCommand(Save);
        AddCommand = new ActionCommand(() => Add(false));
        DuplicateCommand = new ActionCommand(() => Add(true));
    }
    public void Open(string path)
    {
        if (IsDirty) { Message = "Save unsaved changes before opening another CSV."; return; }
        try
        {
            var loaded = DatasetCsv.Load(path);
            _document = loaded; FilePath = path; Selected = null;
            _rows.Clear(); _rows.AddRange(loaded.Rows.Where(r => !loaded.IsSeparator(r)).Select(r => new DatasetRow(r, loaded.Columns)));
            Search = ""; Filter(); Selected = null; IsDirty = false;
            Message = $"Loaded {_rows.Count} datasets. Required: DSNO, DATATYPE, FILENAME.";
        }
        catch (Exception ex) { Message = $"Open failed: {ex.Message}"; }
    }
    private void Filter()
    {
        var selected = Selected;
        FilteredRows.Clear();
        foreach (var row in _rows.Where(r => r.Dsno.Contains(Search ?? "", StringComparison.OrdinalIgnoreCase))) FilteredRows.Add(row);
        Selected = selected != null && FilteredRows.Contains(selected) ? selected : null;
    }
    private void Add(bool duplicate)
    {
        if (_document == null) { Message = "Open a CSV first to use its schema."; return; }
        if (duplicate && Selected == null) { Message = "Select a dataset to duplicate."; return; }
        var values = duplicate ? (string[])Selected!.Values.Clone() : Enumerable.Repeat("", _document.Columns.Length).ToArray();
        values[Array.IndexOf(_document.Columns, "DSNO")] = "";
        _document.Rows.Add(values);
        var row = new DatasetRow(values, _document.Columns);
        _rows.Add(row); Search = ""; Filter(); Selected = row; IsDirty = true;
        Message = "Enter a new unique DSNO and complete DATATYPE and FILENAME before saving.";
    }
    public void Save()
    {
        if (_document == null) { Message = "Open a CSV first."; return; }
        try { var backup = _document.Save(FilePath); IsDirty = false; Message = $"Saved. Backup: {backup}"; }
        catch (Exception ex) { Message = $"Save failed: {ex.Message}"; }
    }
    private static string Category(string name)
    {
        if (name.Contains("FLAT")) return "Flat";
        if (name.StartsWith("WAV") || name.StartsWith("WR") || name.StartsWith("WO") || name.Contains("WAV")) return "Wavelength";
        if (name.Contains("FIB") || name.Contains("IFU")) return "Fiber";
        if (name.Contains("CCD") || name.Contains("CDD") || name == "DARKFRAME") return "CCD";
        if (new[] { "DSNO", "DATATYPE", "NOTE", "FILENAME", "ORIGIN", "EXPMID", "EXPSTART", "EXPSTOP", "EXPTIME", "NFILES" }.Contains(name)) return "General";
        return "Other parameters";
    }
}
