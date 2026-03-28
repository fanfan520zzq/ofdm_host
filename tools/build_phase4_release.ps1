param(
    [string]$PythonCmd = "python",
    [switch]$SkipPubGet,
    [switch]$SkipAnalyze,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$ToolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ToolsDir
$PreflightScript = Join-Path $ToolsDir "phase4_preflight.py"
$LocalFlutter = Join-Path $RepoRoot ".flutter-sdk\bin\flutter.bat"
$FlutterCmd = if (Test-Path $LocalFlutter) { $LocalFlutter } else { "flutter" }

Write-Host "[phase4] running preflight checks..."
& $PythonCmd $PreflightScript --repo-root $RepoRoot --python-cmd $PythonCmd --flutter-cmd $FlutterCmd
if ($LASTEXITCODE -ne 0) {
    throw "preflight failed (exit code: $LASTEXITCODE)"
}

Push-Location (Join-Path $RepoRoot "flutter_ui")
try {
    if (-not $SkipPubGet) {
        Write-Host "[phase4] flutter pub get"
        & $FlutterCmd pub get
        if ($LASTEXITCODE -ne 0) {
            throw "flutter pub get failed"
        }
    }

    if (-not $SkipAnalyze) {
        Write-Host "[phase4] flutter analyze"
        & $FlutterCmd analyze
        if ($LASTEXITCODE -ne 0) {
            throw "flutter analyze failed"
        }
    }

    if (-not $SkipTests) {
        Write-Host "[phase4] flutter test"
        & $FlutterCmd test
        if ($LASTEXITCODE -ne 0) {
            throw "flutter test failed"
        }
    }

    Write-Host "[phase4] flutter build windows --release"
    & $FlutterCmd build windows --release
    if ($LASTEXITCODE -ne 0) {
        throw "flutter build windows --release failed"
    }
}
finally {
    Pop-Location
}

$RunnerReleaseDir = Join-Path $RepoRoot "flutter_ui\build\windows\x64\runner\Release"
if (-not (Test-Path $RunnerReleaseDir)) {
    throw "release output missing: $RunnerReleaseDir"
}

$BundleRoot = Join-Path $RepoRoot "dist\phase4_bundle"
if (Test-Path $BundleRoot) {
    Remove-Item -Path $BundleRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $BundleRoot | Out-Null

Write-Host "[phase4] copying flutter runner output..."
Copy-Item -Path (Join-Path $RunnerReleaseDir "*") -Destination $BundleRoot -Recurse -Force

$PythonCoreDir = Join-Path $BundleRoot "python_core"
New-Item -ItemType Directory -Path $PythonCoreDir | Out-Null

$PythonCoreFiles = @(
    "core_service.py",
    "process_data.py",
    "serial_reader.py",
    "fix_data_format.py",
    "simulate_input.txt",
    "requirements.txt"
)

foreach ($file in $PythonCoreFiles) {
    $source = Join-Path $RepoRoot $file
    if (Test-Path $source) {
        Copy-Item -Path $source -Destination $PythonCoreDir -Force
    }
}

$GuideSource = Join-Path $RepoRoot "doc\phase4_release_guide.md"
if (Test-Path $GuideSource) {
    Copy-Item -Path $GuideSource -Destination (Join-Path $BundleRoot "PHASE4_RELEASE_GUIDE.md") -Force
}

$ExeCandidate = Get-ChildItem -Path $BundleRoot -Filter "ofdm_flutter_ui.exe" | Select-Object -First 1
if ($null -eq $ExeCandidate) {
    $ExeCandidate = Get-ChildItem -Path $BundleRoot -Filter "*.exe" |
        Where-Object { $_.Name -ne "vcredist_x64.exe" } |
        Select-Object -First 1
}
if ($null -eq $ExeCandidate) {
    throw "no executable found in bundle root: $BundleRoot"
}

$LauncherPath = Join-Path $BundleRoot "start_ofdm_flutter.bat"
$LauncherContent = @(
    "@echo off",
    "setlocal",
    "cd /d %~dp0",
    "echo [phase4] launching $($ExeCandidate.Name)",
    "echo [phase4] first-run default paths:",
    "echo   python command: python",
    "echo   core script : .\\python_core\\core_service.py",
    "echo   simulate file: .\\python_core\\simulate_input.txt",
    ('start "" ".\{0}"' -f $ExeCandidate.Name),
    "endlocal"
)
Set-Content -Path $LauncherPath -Value $LauncherContent -Encoding ASCII

$ManifestPath = Join-Path $BundleRoot "phase4_bundle_manifest.txt"
Get-ChildItem -Path $BundleRoot -Recurse |
    Sort-Object FullName |
    ForEach-Object {
        $_.FullName.Substring($BundleRoot.Length + 1)
    } |
    Set-Content -Path $ManifestPath -Encoding ASCII

Write-Host "[phase4] release bundle ready: $BundleRoot"
Write-Host "[phase4] launcher: $LauncherPath"
Write-Host "[phase4] manifest: $ManifestPath"
