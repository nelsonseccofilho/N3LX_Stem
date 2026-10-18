$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repo 'data\logs\server.pid'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'N3LX_Stem ja esta parado.'; exit 0 }
$serverPid = [int](Get-Content -LiteralPath $pidFile)
$proc = Get-CimInstance Win32_Process -Filter "ProcessId = $serverPid"
if (-not $proc) { Write-Output 'N3LX_Stem ja esta parado.'; exit 0 }
if ($proc.CommandLine -notlike '*uvicorn app.main:app*' -or $proc.CommandLine -notlike '*127.0.0.1*' -or $proc.CommandLine -notlike ("*" + $repo + "*")) { throw 'PID nao corresponde ao N3LX_Stem; nenhum processo foi encerrado.' }
& taskkill.exe /PID $serverPid /T /F | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel encerrar o N3LX_Stem.' }
Remove-Item -LiteralPath $pidFile
Write-Output 'N3LX_Stem encerrado.'
