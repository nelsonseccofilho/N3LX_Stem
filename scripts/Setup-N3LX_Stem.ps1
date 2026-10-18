param([switch]$DesktopOnly, [switch]$VerifyOnly, [switch]$SkipDependencies, [switch]$SkipModelDownload)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
function Install-Desktop {
    Get-Command npm.cmd -ErrorAction Stop | Out-Null
    Push-Location (Join-Path $repo 'desktop-app')
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Could not install the desktop dependencies.' }
        & node (Join-Path (Get-Location) 'node_modules\electron\install.js')
        if ($LASTEXITCODE -ne 0) { throw 'Could not download the Electron runtime.' }
    } finally { Pop-Location }
    & (Join-Path $PSScriptRoot 'Create-Shortcut.ps1')
}
if ($DesktopOnly) { Install-Desktop; exit 0 }
$python = Join-Path $repo '.venv\Scripts\python.exe'
$dmlPython = Join-Path $repo '.venv-directml\Scripts\python.exe'
$env:STEMDECK_DATA_DIR = Join-Path $repo 'data'
$env:TORCH_HOME = Join-Path $repo 'data\cache\torch'
$env:PYTHONIOENCODING = 'utf-8'
if (-not $SkipDependencies -and -not $VerifyOnly) {
    # Keep the installer separate from both runtime environments.
    $bootstrap = Join-Path $repo '.venv-bootstrap\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $bootstrap)) {
        & py -3.12 -m venv (Join-Path $repo '.venv-bootstrap')
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 (64-bit) with the py launcher first.' }
    }
    & $bootstrap -m pip install 'uv>=0.8,<1'
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the dependency manager.' }
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $repo '.venv'
    & $bootstrap -m uv sync --frozen --all-extras --python 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Could not install application dependencies.' }
    if (-not (Test-Path -LiteralPath $dmlPython)) {
        & py -3.12 -m venv (Join-Path $repo '.venv-directml')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the DirectML environment.' }
    }
    & $dmlPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-directml.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not install DirectML dependencies.' }
}
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $dmlPython)) {
    throw 'Missing Python environments. Run Setup-N3LX_Stem.cmd first.'
}
Get-Command ffmpeg.exe, ffprobe.exe -ErrorAction Stop | Out-Null
& $python -c 'import torch, torchaudio, audio_separator, fastapi, soundfile'
if ($LASTEXITCODE -ne 0) { throw 'Application dependency check failed.' }
$env:STEMDECK_DIRECTML_PYTHON = $dmlPython
$env:STEMDECK_DIRECTML_ADAPTER = 'RX 6600M'
& $dmlPython (Join-Path $repo 'app\core\amd_directml.py')
if ($LASTEXITCODE -ne 0) { throw 'DirectML probe failed.' }
if (-not $VerifyOnly -and -not $SkipModelDownload) {
    & $python (Join-Path $PSScriptRoot 'download-complete-models.py')
    if ($LASTEXITCODE -ne 0) { throw 'Could not download the detailed separation models.' }
}
if (-not $VerifyOnly) { Install-Desktop }
Write-Output 'N3LX_Stem ready. Open Start-N3LX_Stem.cmd.'
