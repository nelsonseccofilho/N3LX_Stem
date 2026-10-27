# N3LX_Stem: compact header re-extraction action + remove technical notice.
# Only edits static/css/daw.css and static/js/studioLayout.js, adds a JS module.
# Does not operate on tracks, stems, playlists, data/, backend or Git worktrees.
param([string]$Repo = 'D:\git\stemdeck')
$ErrorActionPreference = 'Stop'

$cssPath = Join-Path $Repo 'static\css\daw.css'
$layoutPath = Join-Path $Repo 'static\js\studioLayout.js'
$newJSPath = Join-Path $Repo 'static\js\headerReextract.js'
$branch = 'c1bab69f91274b3b6805d3719f3fdaf1589018f5'
$base = "https://raw.githubusercontent.com/nelsonseccofilho/N3LX_Stem/$branch"
$utf8 = [Text.UTF8Encoding]::new($false)
$cssMarker = 'Compact header: re-extract button'
$layoutMarker = 'initHeaderReextract();'
$startImport = 'import { initHeaderCompactV3 } from "./headerCompactV3.js";'
$startInit = '  initHeaderCompactV3();'

if (-not (Test-Path -LiteralPath $cssPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $layoutPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $Repo 'static\js\headerCompactV3.js') -PathType Leaf)) {
    throw 'Header v3 nao encontrado. Nenhuma alteracao aplicada.'
}

$oldCss = [IO.File]::ReadAllText($cssPath)
$oldLayout = [IO.File]::ReadAllText($layoutPath)

if ($oldCss.Contains($cssMarker) -or
    $oldLayout.Contains($layoutMarker) -or
    (Test-Path -LiteralPath $newJSPath -PathType Leaf)) {
    if ($oldCss.Contains($cssMarker) -and
        $oldLayout.Contains($layoutMarker) -and
        (Test-Path -LiteralPath $newJSPath -PathType Leaf)) {
        Write-Host 'FINAL_RESULT: REEXTRACT_UI_ALREADY_INSTALLED'
        return
    }
    throw 'Instalacao parcial detectada. Nenhuma alteracao aplicada.'
}

if (-not $oldCss.Contains('N3LX_Stem header v3') -or
    [regex]::Matches($oldLayout, [regex]::Escape($startImport)).Count -ne 1 -or
    [regex]::Matches($oldLayout, [regex]::Escape($startInit)).Count -ne 1) {
    throw 'A versao local divergiu do header v3. Nada foi modificado.'
}

# Download all artifacts before changing local source files.
$cssOverlay = (Invoke-WebRequest -Uri "$base/static/css/headerReextract.css" -UseBasicParsing).Content
$jsModule = (Invoke-WebRequest -Uri "$base/static/js/headerReextract.js" -UseBasicParsing).Content
if (-not $cssOverlay.Contains($cssMarker) -or
    -not $jsModule.Contains('export function initHeaderReextract()') -or
    -not $jsModule.Contains('form.requestSubmit(submit)')) {
    throw 'Fonte remota inesperada. Nenhuma alteracao aplicada.'
}

$crlf = [string][char]13 + [string][char]10
$nl = if ($oldLayout.Contains($crlf)) { $crlf } else { [string][char]10 }
$importNew = 'import { initHeaderReextract } from "./headerReextract.js";'
$updatedLayout = $oldLayout.Replace($startImport, $startImport + $nl + $importNew)
$updatedLayout = $updatedLayout.Replace($startInit, $startInit + $nl + '  ' + $layoutMarker)
$updatedCss = $oldCss + $nl + $nl + $cssOverlay + $nl

$backup = Join-Path (Split-Path $Repo -Parent) (
    'N3LX_REEXTRACT_UI_BACKUP_' + (Get-Date -Format 'yyyyMMdd-HHmmss')
)
$backupCss = Join-Path $backup 'static\css\daw.css'
$backupLayout = Join-Path $backup 'static\js\studioLayout.js'
New-Item -ItemType Directory -Force -Path (Split-Path $backupCss -Parent) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $backupLayout -Parent) | Out-Null
Copy-Item -LiteralPath $cssPath -Destination $backupCss -ErrorAction Stop
Copy-Item -LiteralPath $layoutPath -Destination $backupLayout -ErrorAction Stop

try {
    [IO.File]::WriteAllText($cssPath, $updatedCss, $utf8)
    [IO.File]::WriteAllText($newJSPath, $jsModule, $utf8)
    [IO.File]::WriteAllText($layoutPath, $updatedLayout, $utf8)

    if (-not ([IO.File]::ReadAllText($cssPath)).Contains($cssMarker) -or
        -not ([IO.File]::ReadAllText($layoutPath)).Contains($layoutMarker) -or
        -not ([IO.File]::ReadAllText($newJSPath)).Contains('initHeaderReextract')) {
        throw 'Verificacao apos escrita falhou.'
    }
} catch {
    Copy-Item -LiteralPath $backupCss -Destination $cssPath -Force
    Copy-Item -LiteralPath $backupLayout -Destination $layoutPath -Force
    if (Test-Path -LiteralPath $newJSPath) {
        Remove-Item -LiteralPath $newJSPath -Force
    }
    Write-Host 'ROLLBACK=ATTEMPTED'
    throw
}

Write-Host '=== FINAL SUMMARY ==='
Write-Host "BACKUP=$backup"
Write-Host 'TECHNICAL_NOTICE=HIDDEN'
Write-Host 'REEXTRACT_BUTTON=INSTALLED'
Write-Host 'REEXTRACT_ENGINE=EXISTING_RESPLIT'
Write-Host 'NO_AUDIO_JOB_STARTED=True'
Write-Host 'BACKEND_RESTART=False'
Write-Host 'LIBRARY_AND_STEMS_MODIFIED=False'
Write-Host 'FINAL_RESULT: REEXTRACT_UI_INSTALLED'
Write-Host 'Atualize ou reabra a interface para ver o botao Reextrair.'
