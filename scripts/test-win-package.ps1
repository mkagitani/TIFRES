#Requires -Version 7.0
param([string]$Python = 'python')
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$zip=Join-Path $repo 'artifacts/windows/TIFRES-win-x64.zip'
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('TIFRES distribution test '+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
if ([IO.Path]::GetFullPath($temporary).StartsWith($repo+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {throw 'Smoke directory must be outside checkout.'}
Expand-Archive -LiteralPath $zip -DestinationPath $temporary
$package=Join-Path $temporary 'TIFRES-win-x64'
$pythonPath=(Get-Command $Python -ErrorAction Stop).Source
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'deployment-smoke.py') -Destination (Join-Path $temporary 'deployment-smoke.py')
Push-Location $temporary
try {
    & $pythonPath -B (Join-Path $temporary 'deployment-smoke.py') $package $temporary
    if($LASTEXITCODE -ne 0){throw 'Python distribution smoke failed.'}
    $report=Join-Path $temporary 'smoke-report.json'
    $start=[Diagnostics.ProcessStartInfo]::new((Join-Path $package 'Tifres.App.exe'))
    $start.WorkingDirectory=$temporary
    $start.UseShellExecute=$false
    $start.WindowStyle=[Diagnostics.ProcessWindowStyle]::Hidden
    $start.CreateNoWindow=$true
    $start.Environment['DOTNET_ROOT']=Join-Path $temporary 'no-installed-dotnet'
    $start.Environment['PYTHONPATH']=''
    foreach($arg in @('--deployment-smoke-test',$report,$pythonPath,(Join-Path $temporary 'synthetic.w5wc.fits'))){$start.ArgumentList.Add($arg)}
    $process=[Diagnostics.Process]::Start($start)
    try {
        if(!$process.WaitForExit(90000)){$process.Kill($true);throw 'Application smoke timed out.'}
        if($process.ExitCode -ne 0){if(Test-Path $report){Get-Content $report};throw "Application exit $($process.ExitCode)"}
    } finally {$process.Dispose()}
    $result=Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if(!$result.Success){throw 'Application smoke unsuccessful.'}
    Copy-Item -LiteralPath $report -Destination (Join-Path $repo 'artifacts/windows/smoke-report.json') -Force
    Write-Host "PASS: relocated self-contained application, configured Python, cached viewer, status and isolated settings"
    Write-Host "Smoke directory retained: $temporary"
    Get-Content -LiteralPath $report
} finally {Pop-Location}
