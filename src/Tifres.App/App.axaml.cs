using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Tifres.App.ViewModels;
using Tifres.App.Views;
using Tifres.App.Services;

namespace Tifres.App;

public partial class App : Application
{
    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            var args=desktop.Args??[];
            var smoke=args.Length==4 && args[0]=="--deployment-smoke-test";
            var vm=smoke?new MainWindowViewModel(new SettingsViewModel(System.IO.Path.Combine(System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(args[1]))!,"isolated-settings.json"))):new MainWindowViewModel();
            var window=new MainWindow {DataContext=vm};
            desktop.MainWindow=window;
            if(smoke)
            {
                window.ShowInTaskbar=false;
                window.Opened+=async (_,_)=>desktop.Shutdown(await DeploymentSmokeTest.RunAsync(window,vm,args));
            }
        }

        base.OnFrameworkInitializationCompleted();
    }
}
