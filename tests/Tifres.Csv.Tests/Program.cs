using Tifres.App.Models;
using Tifres.App.ViewModels;
using System.Security.Cryptography;

var sample = Path.GetFullPath(args.Length > 0 ? args[0] : "testdata/hmew202510MeBpy2.csv");
var originalHash = SHA256.HashData(File.ReadAllBytes(sample));
var directory = Path.Combine(Path.GetTempPath(), "tifres-tests-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(directory);
int checks = 0;
void Check(bool condition, string label)
{
    if (!condition) throw new Exception(label);
    checks++; Console.WriteLine("PASS " + label);
}
void Reject(Action action, string label)
{
    try { action(); } catch (InvalidDataException) { Check(true, label); return; }
    throw new Exception("Expected rejection: " + label);
}
try
{
    var copy = Path.Combine(directory, "sample.csv");
    File.Copy(sample, copy);
    var doc = DatasetCsv.Load(copy);
    Console.WriteLine($"Loaded {doc.Rows.Count} datasets, {doc.Columns.Length} columns");
    var baseline = doc.Rows.Select(r => r.ToArray()).ToArray();
    var backup = doc.Save(copy);
    Check(File.ReadAllBytes(backup).SequenceEqual(File.ReadAllBytes(sample)), "Backup preserves original bytes");
    var roundtrip = DatasetCsv.Load(copy);
    Check(doc.Columns.SequenceEqual(roundtrip.Columns) && baseline.Zip(roundtrip.Rows).All(p => p.First.SequenceEqual(p.Second)), "Every header and cell survives round-trip exactly as text");
    int note = Array.IndexOf(doc.Columns, "NOTE"), dsno = Array.IndexOf(doc.Columns, "DSNO");
    doc.Rows[1][note] = "Comma, quote \" and\r\nnew line";
    doc.Rows[1][dsno] = "9007199254740993123456789";
    doc.Save(copy);
    roundtrip = DatasetCsv.Load(copy);
    Check(roundtrip.Rows[1][note] == doc.Rows[1][note] && roundtrip.Rows[1][dsno] == doc.Rows[1][dsno], "Quoted text and large DSNO preserved");
    Check(baseline.Select((r, i) => r.Select((v, j) => i == 1 && (j == note || j == dsno) || v == roundtrip.Rows[i][j]).All(v => v)).All(v => v), "All unedited cells preserved after editing");
    var beforeFailure = File.ReadAllBytes(copy);
    doc.Rows[1][dsno] = doc.Rows[0][dsno];
    Reject(() => doc.Save(copy), "Duplicate DSNO rejected");
    Check(beforeFailure.SequenceEqual(File.ReadAllBytes(copy)), "Failed validation leaves original unchanged");
    doc.Rows[1][dsno] = "000" + doc.Rows[0][dsno];
    Reject(doc.Validate, "Leading-zero duplicate rejected without floating point");
    doc.Rows[1][dsno] = "123456";
    doc.Rows[1][Array.IndexOf(doc.Columns, "FILENAME")] = "";
    Reject(doc.Validate, "Missing required field rejected");
    var vm = new DatasetViewModel(); vm.Open(copy);
    Check(vm.FilteredRows.Count == baseline.Count(r => r.Any(v => v.Length > 0)), "View model loads every dataset");
    vm.Search = "9007199254740993123456789";
    Check(vm.FilteredRows.Count == 1, "Search finds exact large DSNO");
    vm.Selected = vm.FilteredRows.Single();
    var template = vm.Selected!.Values.ToArray();
    vm.DuplicateCommand.Execute(null);
    Check(vm.Selected!.Dsno == "" && vm.IsDirty && vm.Selected.Values.Where((v, i) => i != dsno).SequenceEqual(template.Where((v, i) => i != dsno)), "Duplicate preserves template and requires new DSNO");
    vm.Groups.SelectMany(g => g.Fields).Single(f => f.Name == "DSNO").Value = "99999999999999999999999999";
    vm.Save(); Check(!vm.IsDirty, "Duplicated dataset saves and clears dirty flag");
    vm.AddCommand.Execute(null);
    Check(vm.Selected!.Values.All(string.IsNullOrEmpty) && vm.IsDirty, "Add creates blank dataset using original schema");
    vm.Save(); Check(vm.IsDirty && vm.Message.StartsWith("Save failed"), "Invalid new dataset remains unsaved");
    var extra = Path.Combine(directory, "extra.csv");
    File.WriteAllText(extra, "DSNO,DATATYPE,FILENAME,UNKNOWN\r\n00012,SKY  ,x,\"a,b\"\r\n");
    var unknown = DatasetCsv.Load(extra); unknown.Save(extra);
    Check(DatasetCsv.Load(extra).Rows[0].SequenceEqual(new[] { "00012", "SKY  ", "x", "a,b" }), "Unknown columns, padding and leading zeros preserved");
    File.WriteAllText(extra, "DSNO,DATATYPE,FILENAME\n1,SKY,\"unterminated");
    Reject(() => DatasetCsv.Load(extra), "Malformed CSV rejected");
    Check(!Directory.EnumerateFiles(directory, "*.tmp").Any(), "No temporary save files left behind");
    Check(originalHash.SequenceEqual(SHA256.HashData(File.ReadAllBytes(sample))), "Sample CSV remains unchanged");
    Console.WriteLine($"SUCCESS: {checks} checks passed.");
}
finally { Directory.Delete(directory, true); }
