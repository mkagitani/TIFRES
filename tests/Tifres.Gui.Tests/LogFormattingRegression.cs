using System.Reflection;
using Tifres.App.ViewModels;

internal static class LogFormattingRegression
{
    public static void Run(string directory, Action<bool, string> check)
    {
        var vm = new OperationsViewModel(new SettingsViewModel(Path.Combine(directory, "log-settings.json")), new DatasetViewModel());
        var queue = typeof(OperationsViewModel).GetMethod("QueueLog", BindingFlags.NonPublic | BindingFlags.Instance)!;
        var flush = typeof(OperationsViewModel).GetMethod("FlushLogs", BindingFlags.NonPublic | BindingFlags.Instance)!;
        void Feed(string text) { queue.Invoke(vm, [text]); flush.Invoke(vm, null); }
        Feed("."); Feed("."); Feed(".");
        check(vm.Log == "...", "GUI progress fragments do not acquire newlines (actual: " + System.Text.Json.JsonSerializer.Serialize(vm.Log) + ")");
        Feed(" done\n\nnext");
        check(vm.Log == "... done\n\nnext", "GUI preserves partial text and explicit blank lines");
        Feed("\r"); Feed("NEXT"); Feed("\r"); Feed("\n");
        check(vm.Log == "... done\n\nNEXT\n", "GUI carriage return updates current line and split CRLF produces one newline");
    }
}
