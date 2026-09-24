using System.Runtime.InteropServices;
using System.Text.Json;
using Tifres.App.ViewModels;
using Tifres.App.Views;
namespace Tifres.App.Services;

// Opt-in packaging diagnostic. Uses only explicitly supplied temporary test inputs.
public static class DeploymentSmokeTest
{
    public static async Task<int> RunAsync(MainWindow window, MainWindowViewModel vm, string[] args)
    {
        var report=Path.GetFullPath(args[1]);
        try
        {
            window.Hide();
            var bundled=Path.Combine(AppContext.BaseDirectory,"python","legacy");
            if(vm.Settings.ScriptDirectory!=bundled)throw new InvalidOperationException("Script default is not installation-relative.");
            if(!typeof(object).Assembly.Location.StartsWith(AppContext.BaseDirectory,StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Application did not load its bundled .NET runtime.");
            vm.Settings.PythonExecutable=args[2];
            await vm.Display.LoadAsync(args[2],args[3]);
            if(vm.Display.Cube?.Samples!=7)throw new InvalidOperationException(vm.Display.ViewerStatus);
            vm.Display.SelectFiber(0,false);
            vm.Display.IntegrationMode="Sum";vm.Display.WaveFirst="500";vm.Display.WaveLast="501";
            if(vm.Display.IfuValues[0]!=21)throw new InvalidOperationException("Viewer integration mismatch.");
            var root=Path.GetDirectoryName(report)!;
            var status=await ReductionStatus.InspectAsync(new StatusRequest(args[2],bundled,Path.Combine(root,"dataset.csv"),root,root,"123",new()),CancellationToken.None);
            if(status.Steps.Length!=5)throw new InvalidOperationException("Status inspector did not load.");
            vm.Settings.Save();
            File.WriteAllText(report,JsonSerializer.Serialize(new { Success=true, BaseDirectory=AppContext.BaseDirectory,
                Runtime=RuntimeEnvironment.GetRuntimeDirectory(),ScriptDirectory=bundled,ViewerSamples=7,StatusSteps=status.Steps.Length,Settings=vm.Settings.StoragePath },new JsonSerializerOptions{WriteIndented=true}));
            return 0;
        }
        catch(Exception ex){File.WriteAllText(report,JsonSerializer.Serialize(new {Success=false,Error=ex.ToString()}));return 1;}
        finally{vm.Display.CloseCube();}
    }
}
