# N3LX_Stem 0.21.0-rc.4: guarded FLOAT hotfix + non-destructive re-extraction.
# Stage 1: -Mode Patch; restart the application; Stage 2: -Mode Reextract.
# Stage 3 (optional, after job finishes): -Mode Verify.
param(
    [ValidateSet('Patch', 'Reextract', 'Verify')] [string]$Mode = 'Patch',
    [string]$InstallRoot = 'D:\git\N3LX_Stem-Releases\0.21.0-rc.4\N3LX_Stem-Windows-Update-0.21.0-rc.4',
    [string]$Server = 'http://127.0.0.1:8140'
)
$ErrorActionPreference = 'Stop'
$jobId = '4e06a0bc7d91'
$target = Join-Path $InstallRoot 'resources\stemdeck\app\pipeline\complete_multitrack.py'
$work = Join-Path (Split-Path $InstallRoot -Parent) 'N3LX_Rastro_DrumFloat_Hotfix'
$marker = Join-Path $work 'submitted-rastro-job.json'
$utf8 = [Text.UTF8Encoding]::new($false)

if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
    throw "Backend instalado nao encontrado: $target. Nenhuma alteracao."
}
$source = [IO.File]::ReadAllText($target)
$begin = $source.IndexOf('def _aligned_copy(', [StringComparison]::Ordinal)
$end = $source.IndexOf('def _residual(', [StringComparison]::Ordinal)
if ($begin -lt 0 -or $end -le $begin) {
    throw 'Funcoes esperadas nao encontradas. Nada alterado.'
}
$method = $source.Substring($begin, $end - $begin)
$floatInstalled = ($method.Contains('subtype="FLOAT"') -and
    -not $method.Contains('Detailed stem would clip in PCM24') -and
    $method.Contains('Detailed stem contains non-finite samples'))

if ($Mode -eq 'Patch') {
    if ($floatInstalled) {
        Write-Host 'FINAL_RESULT: DRUM_FLOAT_HOTFIX_ALREADY_APPLIED'
        Write-Host 'Se ja reiniciou depois da instalacao, siga para -Mode Reextract.'
        return
    }
    $codec = 'subtype="PCM_24"'
    $errorText = 'Detailed stem would clip in PCM24'
    $guard = '(?m)^ {12}if np\.max\(np\.abs\(data\), initial=0\) >= 1:\r?\n {16}raise ValueError\("Detailed stem would clip in PCM24"\)\r?\n'
    if ([regex]::Matches($method, [regex]::Escape($codec)).Count -ne 1 -or
        [regex]::Matches($method, [regex]::Escape($errorText)).Count -ne 1 -or
        [regex]::Matches($method, $guard).Count -ne 1 -or
        -not $method.Contains('Detailed stem contains non-finite samples')) {
        throw 'A versao local divergiu do patch esperado. Nada alterado.'
    }
    $patched = $method.Replace($codec, 'subtype="FLOAT"')
    $patched = [regex]::Replace($patched, $guard, '')
    if ($patched.Contains($errorText) -or
        -not $patched.Contains('subtype="FLOAT"') -or
        -not $patched.Contains('Detailed stem contains non-finite samples')) {
        throw 'Falha na verificacao da substituicao. Nada alterado.'
    }
    $updated = $source.Substring(0, $begin) + $patched + $source.Substring($end)
    New-Item -ItemType Directory -Path $work -Force | Out-Null
    $backup = Join-Path $work ('complete_multitrack_' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.py.bak')
    $temp = "$target.rastro.tmp"
    Copy-Item -LiteralPath $target -Destination $backup -ErrorAction Stop
    try {
        [IO.File]::WriteAllText($temp, $updated, $utf8)
        if ([IO.File]::ReadAllText($temp) -ne $updated) {
            throw 'Arquivo temporario incompleto.'
        }
        Move-Item -LiteralPath $temp -Destination $target -Force
        if ([IO.File]::ReadAllText($target) -ne $updated) {
            throw 'Arquivo instalado nao confere.'
        }
    } catch {
        Copy-Item -LiteralPath $backup -Destination $target -Force
        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
        Write-Host 'ROLLBACK=APPLIED'
        throw
    }
    Write-Host "BACKUP=$backup"
    Write-Host 'FILES_MODIFIED=1 (only installed backend complete_multitrack.py)'
    Write-Host 'TRACKS_PLAYLISTS_STEMS_MODIFIED=False'
    Write-Host 'APP_RESTART_REQUIRED=True'
    Write-Host 'FINAL_RESULT: DRUM_FLOAT_RC4_PATCH_APPLIED'
    Write-Host 'Feche/reabra N3LX_Stem. Depois rode -Mode Reextract.'
    return
}
if (-not $floatInstalled) {
    throw 'O patch FLOAT nao esta instalado. Execute -Mode Patch.'
}
if ($Mode -eq 'Verify') {
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
        throw 'Ainda nao existe registro de nova reextracao submetida por este script.'
    }
    $submitted = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
    $state = Invoke-RestMethod -Uri "$Server/api/jobs/$($submitted.new_job_id)" -Method Get
    $parts = @($state.stems | Where-Object { $_.name -in @(
        'drum_kick','drum_snare','drum_toms','drum_hh','drum_ride','drum_crash'
    ) })
    Write-Host "NEW_JOB_ID=$($submitted.new_job_id)"
    Write-Host "STATUS=$($state.status)"
    Write-Host "DRUM_PARTS=$($parts.Count)/6"
    Write-Host "WARNINGS=$(@($state.separation_warnings) -join ' | ')"
    if ($state.status -eq 'done' -and $parts.Count -eq 6) {
        Write-Host 'FINAL_RESULT: RASTRO_DRUMS_RECOVERED_6_OF_6'
    } elseif ($state.status -eq 'done') {
        Write-Host 'FINAL_RESULT: RASTRO_REEXTRACTION_FINISHED_WITHOUT_SIX_DRUMS'
    } else {
        Write-Host 'FINAL_RESULT: RASTRO_REEXTRACTION_NOT_FINISHED'
    }
    return
}
if (Test-Path -LiteralPath $marker -PathType Leaf) {
    $already = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
    Write-Host "NEW_JOB_ID=$($already.new_job_id)"
    Write-Host 'FINAL_RESULT: RASTRO_REEXTRACTION_ALREADY_SUBMITTED'
    return
}
$port = [uri]$Server
if ($port.Host -notin @('127.0.0.1','localhost') -or $port.Port -ne 8140) {
    throw 'Apenas a porta local confirmada 8140 e permitida.'
}
$listener = @(Get-NetTCPConnection -State Listen -LocalPort $port.Port -ErrorAction SilentlyContinue |
    Where-Object LocalAddress -eq '127.0.0.1')
if ($listener.Count -ne 1) { throw 'Abra o N3LX_Stem na porta 8140.' }
$backendProcess = Get-Process -Id $listener[0].OwningProcess -ErrorAction Stop
$backendInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener[0].OwningProcess)"
if (-not $backendInfo -or [string]$backendInfo.CommandLine -notlike "*$InstallRoot*") {
    throw 'A porta 8140 nao pertence ao backend instalado que foi corrigido. Nada enviado.'
}
if ($backendProcess.StartTime -le (Get-Item -LiteralPath $target).LastWriteTime) {
    throw 'O backend nao foi reiniciado apos o patch. Feche/reabra o aplicativo.'
}
$job = Invoke-RestMethod -Uri "$Server/api/jobs/$jobId" -Method Get
$config = Invoke-RestMethod -Uri "$Server/api/config" -Method Get
if ($job.job_id -ne $jobId -or $job.status -ne 'done') {
    throw 'A faixa original nao esta concluida. Nada enviado.'
}
if ($job.separation_profile -ne 'complete' -or $config.separation_profile -ne 'complete') {
    throw 'Selecione o perfil Completo antes de reextrair. Nada enviado.'
}
if (-not ([string]$job.source_url).StartsWith('local:')) {
    throw 'Fonte URL detectada. Evitando reimportacao que pode substituir a linha da Biblioteca.'
}
# Never start a duplicate if the user already pressed Reextrair in the app.
$since = [DateTimeOffset]::new((Get-Item -LiteralPath $target).LastWriteTimeUtc).ToUnixTimeSeconds()
$existing = @(Invoke-RestMethod -Uri "$Server/api/jobs?trashed=include" -Method Get |
    Where-Object {
        $_.job_id -ne $jobId -and
        $_.created_at -ge $since -and
        ([string]$_.source_url).StartsWith("$($job.source_url) (")
    })
if ($existing.Count -gt 0) {
    Write-Host "EXISTING_REEXTRACTION_JOB=$($existing[0].job_id)"
    Write-Host 'FINAL_RESULT: RASTRO_REEXTRACTION_ALREADY_IN_LIBRARY'
    return
}
$drumParts = @($job.stems | Where-Object { $_.name -in @('drum_kick','drum_snare','drum_toms','drum_hh','drum_ride','drum_crash') })
if ($drumParts.Count -eq 6) {
    Write-Host 'FINAL_RESULT: ORIGINAL_ALREADY_HAS_SIX_DRUM_PARTS'
    return
}
if ($drumParts.Count -ne 0) {
    throw "Estado inesperado da bateria ($($drumParts.Count)/6). Nada enviado."
}
$payload = @{ stems = @('vocals','drums','bass','guitar','piano','other') } | ConvertTo-Json -Compress
try {
    $new = Invoke-RestMethod -Uri "$Server/api/jobs/$jobId/resplit" -Method Post -ContentType 'application/json' -Body $payload
} catch {
    throw "Reextracao nao aceita pelo backend. Original preservada. $($_.Exception.Message)"
}
if (-not ([string]$new.job_id -match '^[a-f0-9]{12}$') -or
    $new.job_id -eq $jobId -or
    [string]$new.source_url -eq [string]$job.source_url) {
    throw 'Resposta de reextracao inesperada. Consulte a fila antes de repetir.'
}
New-Item -ItemType Directory -Path $work -Force | Out-Null
@{
    original_job_id = $jobId
    new_job_id = $new.job_id
    source_url = $new.source_url
    submitted_at = (Get-Date).ToString('o')
} | ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding utf8
Write-Host "ORIGINAL_JOB_ID=$jobId"
Write-Host "NEW_JOB_ID=$($new.job_id)"
Write-Host 'ORIGINAL_STEMS_REMOVED=False'
Write-Host 'NEW_EXTRACTION_QUEUED=True'
Write-Host 'FINAL_RESULT: RASTRO_REEXTRACTION_SUBMITTED'
Write-Host 'Confirme DRUM_PARTS=6/6 na nova extracao quando concluir.'
