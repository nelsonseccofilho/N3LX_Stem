# Repair the currently running DEVELOPMENT backend on 127.0.0.1:8140.
# Patch (with backup), then restart the Uvicorn backend; then Reextract; then Verify.
param(
    [ValidateSet('Patch','Reextract','Verify')] [string]$Mode = 'Patch',
    [string]$Root = 'D:\git\stemdeck'
)
$ErrorActionPreference = 'Stop'
$jobId = '4e06a0bc7d91'
$target = Join-Path $Root 'app\pipeline\complete_multitrack.py'
$python = Join-Path $Root '.venv\Scripts\python.exe'
$backups = Join-Path $env:LOCALAPPDATA 'N3LX_Stem\Rastro-Backup'
$marker = Join-Path $backups 'new-job.json'
$server = 'http://127.0.0.1:8140'
if (!(Test-Path -LiteralPath $target) -or !(Test-Path -LiteralPath $python)) {
    throw 'A origem Python ou a venv do projeto D:\git\stemdeck nao existe.'
}
$port = @(Get-NetTCPConnection -LocalPort 8140 -State Listen -ErrorAction SilentlyContinue |
    Where-Object LocalAddress -eq '127.0.0.1')
if ($port.Count -ne 1) { throw 'Backend na porta 8140 nao encontrado.' }
$proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($port[0].OwningProcess)"
$parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.ParentProcessId)"
if (!$proc -or !$parent -or $parent.ExecutablePath -ne $python -or
    $proc.CommandLine -notmatch 'uvicorn app\.main:app') {
    throw 'O processo atual nao corresponde ao projeto de desenvolvimento esperado.'
}
Push-Location -LiteralPath $Root
try {
    $origin = @(& $python -c 'import importlib.util; print(importlib.util.find_spec("app.pipeline.complete_multitrack").origin)')
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel localizar o modulo Python.' }
} finally { Pop-Location }
if ([IO.Path]::GetFullPath([string]$origin[-1]) -ne [IO.Path]::GetFullPath($target)) {
    throw "O backend nao aponta para o arquivo esperado: $($origin[-1])."
}
$source = [IO.File]::ReadAllText($target)
$begin = $source.IndexOf('def _aligned_copy(',[StringComparison]::Ordinal)
$end = $source.IndexOf('def _residual(',[StringComparison]::Ordinal)
if ($begin -lt 0 -or $end -le $begin) { throw 'Funcoes esperadas nao encontradas.' }
$segment = $source.Substring($begin,$end-$begin)
$old = 'Detailed stem would clip in PCM24'
$floatReady = $segment.Contains('subtype="FLOAT"') -and
    !$segment.Contains($old) -and $segment.Contains('Detailed stem contains non-finite samples')
if ($Mode -eq 'Patch') {
    if ($floatReady) {
        Write-Host 'FINAL_RESULT: ACTIVE_DEV_SOURCE_ALREADY_FIXED'
        Write-Host 'Confira se o Uvicorn foi reiniciado apos a atualizacao deste arquivo.'
        return
    }
    $guard = '(?m)^ {12}if np\.max\(np\.abs\(data\), initial=0\) >= 1:\r?\n {16}raise ValueError\("Detailed stem would clip in PCM24"\)\r?\n'
    if ([regex]::Matches($segment,'subtype="PCM_24"').Count -ne 1 -or
        [regex]::Matches($segment,$guard).Count -ne 1 -or
        !$segment.Contains('Detailed stem contains non-finite samples')) {
        throw 'O codigo do backend divergiu do padrao conhecido. Nada alterado.'
    }
    $fixed = $segment.Replace('subtype="PCM_24"','subtype="FLOAT"')
    $fixed = [regex]::Replace($fixed,$guard,'')
    $updated = $source.Substring(0,$begin)+$fixed+$source.Substring($end)
    New-Item -ItemType Directory -Path $backups -Force | Out-Null
    $backup = Join-Path $backups ('complete_multitrack_'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.py.bak')
    Copy-Item -LiteralPath $target -Destination $backup -ErrorAction Stop
    $temp = "$target.rastro.tmp"
    try {
        $bytes = [IO.File]::ReadAllBytes($target)
        $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191
        [IO.File]::WriteAllText($temp,$updated,[Text.UTF8Encoding]::new($bom))
        & $python -c 'import ast,sys; ast.parse(open(sys.argv[1],encoding="utf-8-sig").read())' $temp
        if ($LASTEXITCODE -ne 0) { throw 'Sintaxe Python invalida.' }
        Move-Item -LiteralPath $temp -Destination $target -Force
        if ([IO.File]::ReadAllText($target) -ne $updated) { throw 'Integridade falhou.' }
    } catch {
        Copy-Item -LiteralPath $backup -Destination $target -Force
        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
        throw
    }
    Write-Host "BACKUP=$backup"
    Write-Host "PATCHED=$target"
    Write-Host 'MUSIC_FILES_MODIFIED=False'
    Write-Host 'FINAL_RESULT: ACTIVE_DEV_DRUM_FLOAT_PATCH_APPLIED'
    Write-Host 'Agora reinicie o PROCESSO UVICORN do projeto, nao apenas o .exe.'
    return
}
if (!$floatReady) { throw 'A correcao FLOAT nao esta presente neste backend.' }
if ($Mode -eq 'Verify') {
    if (!(Test-Path -LiteralPath $marker)) { throw 'Nova extracao nao registrada.' }
    $saved = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
    $job = Invoke-RestMethod "$server/api/jobs/$($saved.job_id)"
    $parts = @($job.stems | Where-Object { $_.name -in @('drum_kick','drum_snare','drum_toms','drum_hh','drum_ride','drum_crash') })
    Write-Host "NEW_JOB_ID=$($saved.job_id)"
    Write-Host "STATUS=$($job.status)"
    Write-Host "DRUM_PARTS=$($parts.Count)/6"
    Write-Host "WARNINGS=$(@($job.separation_warnings) -join ' | ')"
    if ($job.status -eq 'done' -and $parts.Count -eq 6) {
        Write-Host 'FINAL_RESULT: RASTRO_DRUMS_RECOVERED_6_OF_6'
    } else { Write-Host 'FINAL_RESULT: RASTRO_NOT_YET_RECOVERED' }
    return
}
if ([datetime]$proc.CreationDate -le (Get-Item -LiteralPath $target).LastWriteTime) {
    throw 'O processo Uvicorn ainda nao foi reiniciado desde a correcao.'
}
if (Test-Path -LiteralPath $marker) {
    $saved = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
    Write-Host "NEW_JOB_ID=$($saved.job_id)"
    Write-Host 'FINAL_RESULT: ALREADY_SUBMITTED'
    return
}
$original = Invoke-RestMethod "$server/api/jobs/$jobId"
$config = Invoke-RestMethod "$server/api/config"
if ($original.job_id -ne $jobId -or $original.status -ne 'done' -or
    $original.separation_profile -ne 'complete' -or $config.separation_profile -ne 'complete') {
    throw 'A musica original deve estar concluida, e o perfil atual deve ser Completo.'
}
if (-not ([string]$original.source_url) -or -not ([string]$original.source_url).StartsWith('local:')) {
    throw 'A musica veio de URL: este resplit automatico so suporta arquivo local retido.'
}
$all = @(Invoke-RestMethod "$server/api/jobs?trashed=include")
$existing = @($all | Where-Object { ([string]$_.source_url).StartsWith("$($original.source_url) (") })
if ($existing.Count -gt 0) {
    Write-Host "EXISTING_JOB_ID=$($existing[0].job_id)"
    Write-Host 'FINAL_RESULT: RASTRO_REEXTRACTION_ALREADY_EXISTS'
    return
}
$parts = @($original.stems | Where-Object { $_.name -in @(
    'drum_kick','drum_snare','drum_toms','drum_hh','drum_ride','drum_crash'
) })
if ($parts.Count -ne 0) {
    throw "O estado da musica mudou: ja existem $($parts.Count) pecas de bateria. Nada enviado."
}
$new = Invoke-RestMethod -Uri "$server/api/jobs/$jobId/resplit" -Method Post -ContentType 'application/json' -Body '{"stems":["vocals","drums","bass","guitar","piano","other"]}'
if ($new.job_id -notmatch '^[a-f0-9]{12}$' -or $new.job_id -eq $jobId) {
    throw 'Resposta inesperada. Consulte a fila antes de repetir a operacao.'
}
New-Item -ItemType Directory -Path $backups -Force | Out-Null
@{job_id=$new.job_id; source_url=$new.source_url} |
    ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding utf8
Write-Host "NEW_JOB_ID=$($new.job_id)"
Write-Host 'ORIGINAL_STEMS_PRESERVED=True'
Write-Host 'FINAL_RESULT: RASTRO_REEXTRACTION_SUBMITTED'
