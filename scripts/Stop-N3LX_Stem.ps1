param([int]$Port = 8000, [string]$RuntimeRoot = '', [string]$DataDir = '')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $RuntimeRoot) { $RuntimeRoot = $repo }
if (-not $DataDir) { $DataDir = Join-Path $RuntimeRoot 'data' }
$python = Join-Path $RuntimeRoot '.venv\Scripts\python.exe'
& $python (Join-Path $PSScriptRoot 'backend_control.py') stop --port $Port --runtime $RuntimeRoot --data $DataDir
if ($LASTEXITCODE -ne 0) { throw 'Parada controlada recusada; nenhum encerramento forcado foi executado.' }
