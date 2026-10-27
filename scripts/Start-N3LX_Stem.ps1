param([switch]$NoBrowser, [switch]$Browser, [int]$Port = 8000, [string]$Adapter = 'RX 6600M', [string]$RuntimeRoot = '', [string]$DataDir = '')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
if (-not $RuntimeRoot) { $RuntimeRoot = $repo }
if (-not $DataDir) { $DataDir = Join-Path $RuntimeRoot 'data' }
$env:STEMDECK_DATA_DIR = $DataDir
$env:STEMDECK_DIRECTML_PYTHON = Join-Path $RuntimeRoot '.venv-directml\Scripts\python.exe'
$env:STEMDECK_DIRECTML_ADAPTER = $Adapter
$env:STEMDECK_DEMUCS_DEVICE = 'directml'
$env:STEMDECK_DEFAULT_JOBS_DIR = Join-Path $DataDir 'jobs'
$env:STEMDECK_CACHE_DIR = Join-Path $DataDir 'cache'
$env:STEMDECK_MODELS_DIR = Join-Path $DataDir 'models'
$env:STEMDECK_LOGS_DIR = Join-Path $DataDir 'logs'
$env:STEMDECK_DOWNLOADS_DIR = Join-Path $DataDir 'downloads'
$env:TORCH_HOME = Join-Path $DataDir 'cache\torch'
$env:PYTHONIOENCODING = 'utf-8'
$env:STEMDECK_SEPARATION_PROFILE = 'complete'
$env:STEMDECK_SEPARATION_QUALITY = 'best'
$env:STEMDECK_PERSIST_LIBRARY = '1'
if (-not $env:N3LX_WHISPER_CLI) {
    $env:N3LX_WHISPER_CLI = Join-Path $RuntimeRoot 'tools\whisper.cpp\whisper-cli.exe'
    if (-not (Test-Path -LiteralPath $env:N3LX_WHISPER_CLI)) { $env:N3LX_WHISPER_CLI = Join-Path $env:USERPROFILE 'whisper.cpp\build-vulkan\bin\Release\whisper-cli.exe' }
}
if (-not $env:N3LX_WHISPER_MODEL) {
    $env:N3LX_WHISPER_MODEL = Join-Path $RuntimeRoot 'tools\whisper.cpp\ggml-medium.bin'
    if (-not (Test-Path -LiteralPath $env:N3LX_WHISPER_MODEL)) { $env:N3LX_WHISPER_MODEL = Join-Path $env:USERPROFILE 'whisper.cpp\models\ggml-medium.bin' }
}
if (-not $env:STEMDECK_SAM_SOURCE) { $env:STEMDECK_SAM_SOURCE = Join-Path (Split-Path $RuntimeRoot -Parent) 'sam-audio-amd' }
$env:STEMDECK_FFMPEG = (Get-Command ffmpeg.exe -ErrorAction Stop).Source
$env:STEMDECK_FFPROBE = Join-Path (Split-Path $env:STEMDECK_FFMPEG) 'ffprobe.exe'
$python = Join-Path $RuntimeRoot '.venv\Scripts\python.exe'
$logDir = Join-Path $DataDir 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$url = "http://127.0.0.1:$Port"
$health = $null
try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2 } catch {}
if ($health -and $env:STEMDECK_INSTANCE_TOKEN -and $health.instance -ne $env:STEMDECK_INSTANCE_TOKEN) { throw "Outro servidor ocupa a porta $Port. Feche a outra instancia ou escolha outra porta." }
if (-not $health) {
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($connection) { throw "Porta $Port ocupada. Use -Port para escolher outra." }
    $proc = Start-Process -FilePath $python -WorkingDirectory $repo -WindowStyle Hidden -PassThru -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$Port",'--timeout-graceful-shutdown','5') -RedirectStandardOutput (Join-Path $logDir 'server.stdout.log') -RedirectStandardError (Join-Path $logDir 'server.stderr.log')
    Set-Content -LiteralPath (Join-Path $logDir 'server.pid') -Value $proc.Id
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Seconds 1
        try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2; break } catch {}
        if ($proc.HasExited) { throw "N3LX_Stem encerrou. Consulte data\logs\server.stderr.log." }
    }
    if (-not $health) { throw 'Inicializacao excedeu o tempo. Consulte data\logs.' }
}
if ($health.name -ne "StemDeck" -or $health.status -ne "ok") { throw "Outro aplicativo esta usando $url." }
$settings = Invoke-RestMethod "$url/api/settings" -TimeoutSec 60
if ($settings.demucs_devices_available -notcontains 'directml') { throw 'A RX6600M nao passou no teste DirectML. Consulte data\logs.' }
Invoke-RestMethod "$url/api/settings" -Method Post -ContentType 'application/json' -Body '{"demucs_device":"directml"}' | Out-Null
Write-Output "N3LX_Stem pronto: $url - AMD / DirectML"
if (-not $NoBrowser) {
    if ($Browser) { Start-Process $url }
    else {
        $desktopDir = Join-Path $repo 'desktop-app'
        $electron = Join-Path $desktopDir 'node_modules\electron\dist\electron.exe'
        if (-not (Test-Path -LiteralPath $electron)) { throw 'Execute Setup-N3LX_Stem.cmd -DesktopOnly para preparar o aplicativo.' }
        Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
        Start-Process -FilePath $electron -WorkingDirectory $repo -ArgumentList @(('"' + $desktopDir + '"'), "--port=$Port")
    }
}
