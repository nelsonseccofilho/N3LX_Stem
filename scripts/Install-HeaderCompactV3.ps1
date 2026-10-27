# Apply N3LX_Stem compact header v3 over the previously installed v2.
# Touches only static/css/daw.css and static/js/studioLayout.js; adds one JS module.
# No Git reset, no checkout, no backend restart, no music/data/stems changes.
param([string]$Repo = 'D:\git\stemdeck')
$ErrorActionPreference = 'Stop'

$cssPath = Join-Path $Repo 'static\css\daw.css'
$layoutPath = Join-Path $Repo 'static\js\studioLayout.js'
$newJSPath = Join-Path $Repo 'static\js\headerCompactV3.js'
$branch = 'feature/compact-header-v2-residual-pitch-20261026'
$base = "https://raw.githubusercontent.com/nelsonseccofilho/N3LX_Stem/$branch"
$utf8 = [Text.UTF8Encoding]::new($false)
$cssMarker = 'N3LX_Stem header v3'
$layoutMarker = 'initHeaderCompactV3();'

if (-not (Test-Path -LiteralPath $cssPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $layoutPath -PathType Leaf)) {
    throw 'Frontend local ausente. Nada foi modificado.'
}

$oldCss = [IO.File]::ReadAllText($cssPath)
$oldLayout = [IO.File]::ReadAllText($layoutPath)
$v2Marker = 'N3LX_Stem compact header v2: use the free width'
$startImport = 'import { initHeaderCompactV2 } from "./headerCompactV2.js";'
$startInit = '  initHeaderCompactV2();'

if ($oldCss.Contains($cssMarker) -or
    $oldLayout.Contains($layoutMarker) -or
    (Test-Path -LiteralPath $newJSPath)) {
    if ($oldCss.Contains($cssMarker) -and
        $oldLayout.Contains($layoutMarker) -and
        (Test-Path -LiteralPath $newJSPath)) {
        Write-Host 'FINAL_RESULT: HEADER_V3_ALREADY_INSTALLED'
        return
    }
    throw 'Instalacao v3 parcial detectada. Nada foi sobrescrito.'
}
if (-not $oldCss.Contains($v2Marker) -or
    -not (Test-Path -LiteralPath (Join-Path $Repo 'static\js\headerCompactV2.js')) -or
    [regex]::Matches($oldLayout, [regex]::Escape($startImport)).Count -ne 1 -or
    [regex]::Matches($oldLayout, [regex]::Escape($startInit)).Count -ne 1) {
    throw 'Header v2 instalado nao corresponde ao esperado. Nada foi modificado.'
}

# Acquire both sources before touching the checkout.
$v3CSS = (Invoke-WebRequest -Uri "$base/static/css/headerCompactV3.css" -UseBasicParsing).Content
$v3JS = (Invoke-WebRequest -Uri "$base/static/js/headerCompactV3.js" -UseBasicParsing).Content
if (-not $v3CSS.Contains($cssMarker) -or
    -not $v3JS.Contains('export function initHeaderCompactV3()') -or
    -not $v3CSS.Contains('display: block !important')) {
    throw 'Conteudo do GitHub inesperado. Nenhuma modificacao aplicada.'
}

$nl = if ($oldLayout.Contains([string][char]13 + [string][char]10)) {
    [string][char]13 + [string][char]10
} else {
    [string][char]10
}
$importV3 = 'import { initHeaderCompactV3 } from "./headerCompactV3.js";'
$newLayout = $oldLayout.Replace($startImport, $startImport + $nl + $importV3)
$newLayout = $newLayout.Replace($startInit, $startInit + $nl + $layoutMarker.Insert(0,'  '))
$newCss = $oldCss + $nl + $nl + $v3CSS + $nl

$backup = Join-Path (Split-Path $Repo -Parent) (
    'N3LX_HEADER_V3_BACKUP_' + (Get-Date -Format 'yyyyMMdd-HHmmss')
)
$backupCSS = Join-Path $backup 'static\css\daw.css'
$backupLayout = Join-Path $backup 'static\js\studioLayout.js'
New-Item -ItemType Directory -Force -Path (Split-Path $backupCSS -Parent) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $backupLayout -Parent) | Out-Null
Copy-Item -LiteralPath $cssPath -Destination $backupCSS -ErrorAction Stop
Copy-Item -LiteralPath $layoutPath -Destination $backupLayout -ErrorAction Stop

try {
    [IO.File]::WriteAllText($cssPath, $newCss, $utf8)
    [IO.File]::WriteAllText($newJSPath, $v3JS, $utf8)
    # Finally register the new module. Before this point v2 stays active.
    [IO.File]::WriteAllText($layoutPath, $newLayout, $utf8)
    if (-not ([IO.File]::ReadAllText($cssPath)).Contains($cssMarker) -or
        -not ([IO.File]::ReadAllText($layoutPath)).Contains($layoutMarker) -or
        -not ([IO.File]::ReadAllText($newJSPath)).Contains('initHeaderCompactV3')) {
        throw 'Verificacao de arquivos falhou.'
    }
} catch {
    Copy-Item -LiteralPath $backupCSS -Destination $cssPath -Force
    Copy-Item -LiteralPath $backupLayout -Destination $layoutPath -Force
    if (Test-Path -LiteralPath $newJSPath -PathType Leaf) {
        Remove-Item -LiteralPath $newJSPath -Force
    }
    Write-Host 'ROLLBACK=PASS'
    throw
}
Write-Host '=== FINAL SUMMARY ==='
Write-Host "BACKUP=$backup"
Write-Host 'TRANSPORT_LAYOUT=V3'
Write-Host 'SEEK_PROGRESS_FILL=VISIBLE'
Write-Host 'SIDEBAR_CHEVRON=STATE_AWARE'
Write-Host 'BACKEND_RESTART=False'
Write-Host 'LIBRARY_STEMS_PLAYLISTS_MODIFIED=False'
Write-Host 'FINAL_RESULT: HEADER_V3_LOCAL_INSTALLED'
Write-Host 'Atualize a janela do N3LX_Stem para carregar o novo frontend.'
