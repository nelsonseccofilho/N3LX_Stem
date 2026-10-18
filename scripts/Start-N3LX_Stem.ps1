param([switch]$NoBrowser, [switch]$Browser, [int]$Port = 8000, [string]$Adapter = 'RX 6600M')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
$env:STEMDECK_DATA_DIR = Join-Path $repo 'data'
$env:STEMDECK_DIRECTML_PYTHON = Join-Path $repo '.venv-directml\Scripts\python.exe'
$env:STEMDECK_DIRECTML_ADAPTER = $Adapter
$env:STEMDECK_DEMUCS_DEVICE = 'directml'
$env:TORCH_HOME = Join-Path $repo 'data\cache\torch'
$env:PYTHONIOENCODING = 'utf-8'
$env:STEMDECK_SEPARATION_PROFILE = 'complete'
$env:STEMDECK_SEPARATION_QUALITY = 'best'
$env:STEMDECK_PERSIST_LIBRARY = '1'
$env:STEMDECK_FFMPEG = (Get-Command ffmpeg.exe -ErrorAction Stop).Source
$env:STEMDECK_FFPROBE = Join-Path (Split-Path $env:STEMDECK_FFMPEG) 'ffprobe.exe'
$python = Join-Path $repo '.venv\Scripts\python.exe'
$logDir = Join-Path $repo 'data\logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$url = "http://127.0.0.1:$Port"
$health = $null
try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2 } catch {}
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
