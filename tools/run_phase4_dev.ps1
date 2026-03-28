param(
    [string]$Device = "windows",
    [string]$PythonCmd = "python",
    [switch]$SkipPubGet
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

    Write-Host "[phase4] flutter run -d $Device"
    & $FlutterCmd run -d $Device
    if ($LASTEXITCODE -ne 0) {
        throw "flutter run failed"
    }
}
finally {
    Pop-Location
}
