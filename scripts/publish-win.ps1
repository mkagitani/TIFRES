#Requires -Version 7.0
[CmdletBinding()]
param([switch]$Force)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (!(Test-Path -LiteralPath (Join-Path $repo 'TIFRES.sln'))) { throw 'TIFRES.sln not found.' }
if (![OperatingSystem]::IsWindows()) { throw 'Use PowerShell 7 on Windows.' }
$root = Join-Path $repo 'artifacts/windows'
$publish = Join-Path $root 'TIFRES-win-x64'
$zip = Join-Path $root 'TIFRES-win-x64.zip'
if (!$Force -and ((Test-Path -LiteralPath $publish) -or (Test-Path -LiteralPath $zip))) { throw 'Distribution exists. Use -Force to replace it.' }
function Remove-Artifact([string]$Path) {
    $resolved = [IO.Path]::GetFullPath($Path)
    $boundary = [IO.Path]::GetFullPath($root) + [IO.Path]::DirectorySeparatorChar
    if (!$resolved.StartsWith($boundary,[StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe removal: $resolved" }
    if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}
New-Item -ItemType Directory -Path $root -Force | Out-Null
$stage = Join-Path $root ('.stage-' + [Guid]::NewGuid().ToString('N'))
$stagedZip = "$stage.zip"
$project = Join-Path $repo 'src/Tifres.App/Tifres.App.csproj'
$lock = Join-Path $repo 'packaging/packages.win-x64.lock.json'
Push-Location $repo
try {
    & dotnet restore $project --runtime win-x64 --locked-mode "-p:NuGetLockFilePath=$lock" "-p:SelfContained=true"
    if ($LASTEXITCODE -ne 0) { throw 'Locked restore failed.' }
    $publishArgs = @('publish',$project,'--configuration','Release','--runtime','win-x64','--self-contained','true','--no-restore','--output',$stage,
        "-p:NuGetLockFilePath=$lock",'-p:PublishSingleFile=false','-p:PublishTrimmed=false','-p:DebugType=None','-p:DebugSymbols=false',
        '-p:ContinuousIntegrationBuild=true','-p:Deterministic=true',"-p:PathMap=$repo=/_/TIFRES",'-p:TifresDistribution=true')
    & dotnet @publishArgs
    if ($LASTEXITCODE -ne 0) { throw 'Publish failed.' }
    $required = @('Tifres.App.exe','coreclr.dll','hostfxr.dll','requirements.txt','README-Windows.md',
        'python/tifres_quicklook.py','python/tifres_launcher.py','python/tifres_viewer.py','python/tifres_status.py','python/tifres_dependencies.py',
        'python/tifres_provenance.py','python/tifres_publication.py','python/legacy/cfg.py')
    foreach ($name in $required) { if (!(Test-Path -LiteralPath (Join-Path $stage $name))) { throw "Missing: $name" } }
    foreach ($file in Get-ChildItem -LiteralPath $stage -Recurse -File) {
        if ($file.Extension -in @('.fits','.fit','.fts','.csv','.png','.pyc','.pdb') -or $file.FullName -match '[\\/](?:__pycache__|\.tifres-runs|anaconda3|miniconda3|testdata|raw)[\\/]') { throw "Forbidden distribution content: $($file.FullName)" }
    }
    $manifest = [ordered]@{ Format = 1; Runtime = 'win-x64'; Configuration = 'Release'; SelfContained = $true; Sdk = (& dotnet --version).Trim(); Files = [ordered]@{} }
    $names = [string[]]@(Get-ChildItem -LiteralPath $stage -Recurse -File | ForEach-Object { [IO.Path]::GetRelativePath($stage,$_.FullName).Replace('\','/') })
    [Array]::Sort($names,[StringComparer]::Ordinal)
    foreach ($name in $names) { $manifest.Files[$name] = (Get-FileHash -LiteralPath (Join-Path $stage $name) -Algorithm SHA256).Hash.ToLowerInvariant() }
    [IO.File]::WriteAllText((Join-Path $stage 'manifest.json'),($manifest | ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
    $names += 'manifest.json'; [Array]::Sort($names,[StringComparer]::Ordinal)
    $archive = [IO.Compression.ZipFile]::Open($stagedZip,[IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($name in $names) {
            $entry = $archive.CreateEntry("TIFRES-win-x64/$name",[IO.Compression.CompressionLevel]::Optimal)
            $entry.LastWriteTime = [DateTimeOffset]::new(2000,1,1,0,0,0,[TimeSpan]::Zero)
            $inputFile = [IO.File]::OpenRead((Join-Path $stage $name)); $outputFile = $entry.Open()
            try { $inputFile.CopyTo($outputFile) } finally { $inputFile.Dispose(); $outputFile.Dispose() }
        }
    } finally { $archive.Dispose() }
    Remove-Artifact $publish; Remove-Artifact $zip
    Move-Item -LiteralPath $stage -Destination $publish
    Move-Item -LiteralPath $stagedZip -Destination $zip
    Write-Host "Publish directory: $publish"
    Write-Host "ZIP: $zip"
    Write-Host "ZIP SHA256: $((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash)"
} finally { Pop-Location; Remove-Artifact $stage; Remove-Artifact $stagedZip }
