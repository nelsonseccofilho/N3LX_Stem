# N3LX_Stem local bridge for a focused UI + residual pitch change.
# No backend, data, media, Git state, playlists or stem files are touched.
param([string]$Repo = 'D:\git\stemdeck')
$ErrorActionPreference = 'Stop'
$base = 'https://raw.githubusercontent.com/nelsonseccofilho/N3LX_Stem/feature/compact-header-v2-residual-pitch-20261026'
$cssFile = Join-Path $Repo 'static\css\daw.css'
$layoutFile = Join-Path $Repo 'static\js\studioLayout.js'
$constantsFile = Join-Path $Repo 'static\js\constants.js'
$newJsFile = Join-Path $Repo 'static\js\headerCompactV2.js'
$files = @($cssFile, $layoutFile, $constantsFile)
$utf8 = [Text.UTF8Encoding]::new($false)

foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Arquivo esperado ausente: $file"
    }
}
$cssBefore = [IO.File]::ReadAllText($cssFile)
$layoutBefore = [IO.File]::ReadAllText($layoutFile)
$constantsBefore = [IO.File]::ReadAllText($constantsFile)
if (-not $cssBefore.Contains('Compact persistent header') -or
    -not $layoutBefore.Contains('compact-header-v1') -or
    -not $constantsBefore.Contains('export function isPercussion(name)')) {
    throw 'Versao local inesperada: nenhuma alteracao aplicada.'
}
$cssMarker = 'N3LX_Stem compact header v2: use the free width'
$jsMarker = 'initHeaderCompactV2();'
$constantMarker = 'if (name === "residual_mix") return false;'
$alreadyCss = $cssBefore.Contains($cssMarker)
$alreadyJs = $layoutBefore.Contains($jsMarker)
$alreadyConstants = $constantsBefore.Contains($constantMarker)
if ($alreadyCss -or $alreadyJs -or $alreadyConstants) {
    if ($alreadyCss -and $alreadyJs -and $alreadyConstants -and
        (Test-Path -LiteralPath $newJsFile -PathType Leaf)) {
        Write-Host 'FINAL_RESULT: HEADER_V2_ALREADY_APPLIED'
        return
    }
    throw 'Atualizacao parcial detectada. Nada sera sobrescrito.'
}
if (Test-Path -LiteralPath $newJsFile) {
    throw 'Modulo headerCompactV2.js ja existe. Nenhuma alteracao aplicada.'
}

# Download before writing; remote/network errors leave local sources untouched.
$cssOverlay = (Invoke-WebRequest -Uri "$base/static/css/headerCompactV2.css" -UseBasicParsing).Content
$jsModule = (Invoke-WebRequest -Uri "$base/static/js/headerCompactV2.js" -UseBasicParsing).Content
if (-not $cssOverlay.Contains($cssMarker) -or
    -not $jsModule.Contains('export function initHeaderCompactV2()')) {
    throw 'Conteudo remoto inesperado. Nenhuma alteracao aplicada.'
}
$crlf = [string][char]13 + [string][char]10
$lf = [string][char]10
$nl = if ($layoutBefore.Contains($crlf)) { $crlf } else { $lf }
$importAnchor = 'import { t, onLanguageChange } from "./i18n.js";'
$finishAnchor = '  onLanguageChange(refresh);' + $nl + '  refresh();'
if (-not $layoutBefore.Contains($importAnchor) -or
    -not $layoutBefore.Contains($finishAnchor)) {
    throw 'Estrutura local do layout divergente. Nenhuma alteracao aplicada.'
}
$layoutAfter = $layoutBefore.Replace(
    $importAnchor,
    $importAnchor + $nl + 'import { initHeaderCompactV2 } from "./headerCompactV2.js";'
).Replace($finishAnchor, $finishAnchor + $nl + '  initHeaderCompactV2();')
$constAnchor = 'export function isPercussion(name) {'
if (-not $constantsBefore.Contains($constAnchor) -or
    -not $constantsBefore.Contains('name === "residual_mix"')) {
    throw 'Regra atual de percussion divergente. Nenhuma alteracao aplicada.'
}
$constantsAfter = $constantsBefore.Replace(
    $constAnchor,
    $constAnchor + ' if (name === "residual_mix") return false;'
)
$cssAfter = $cssBefore + $lf + $lf + $cssOverlay + $lf

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path (Split-Path $Repo -Parent) "N3LX_HEADER_V2_BACKUP_$stamp"
if (Test-Path -LiteralPath $backup) { throw 'Backup ja existe.' }
foreach ($file in $files) {
    $rel = [IO.Path]::GetRelativePath($Repo, $file)
    $dest = Join-Path $backup $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
    Copy-Item -LiteralPath $file -Destination $dest -ErrorAction Stop
}
$written = $false
try {
    $written = $true
    [IO.File]::WriteAllText($cssFile, $cssAfter, $utf8)
    [IO.File]::WriteAllText($layoutFile, $layoutAfter, $utf8)
    [IO.File]::WriteAllText($constantsFile, $constantsAfter, $utf8)
    [IO.File]::WriteAllText($newJsFile, $jsModule, $utf8)
    if (-not ([IO.File]::ReadAllText($constantsFile)).Contains($constantMarker) -or
        -not ([IO.File]::ReadAllText($layoutFile)).Contains($jsMarker) -or
        -not ([IO.File]::ReadAllText($cssFile)).Contains($cssMarker)) {
        throw 'Verificacao do patch falhou.'
    }
} catch {
    if ($written) {
        foreach ($file in $files) {
            $rel = [IO.Path]::GetRelativePath($Repo, $file)
            Copy-Item -LiteralPath (Join-Path $backup $rel) -Destination $file -Force
        }
        if (Test-Path -LiteralPath $newJsFile) {
            Remove-Item -LiteralPath $newJsFile -Force
        }
    }
    Write-Host 'ROLLBACK=ATTEMPTED'
    throw
}
Write-Host '=== FINAL SUMMARY ==='
Write-Host "BACKUP=$backup"
Write-Host 'HEADER_LAYOUT_V2=APPLIED'
Write-Host 'RESIDUAL_MIX_PITCH=ENABLED'
Write-Host 'BACKEND_RESTART=False'
Write-Host 'STEMS_AND_LIBRARY_MODIFIED=False'
Write-Host 'FINAL_RESULT: HEADER_V2_AND_RESIDUAL_PITCH_INSTALLED'
Write-Host 'Reabra ou atualize a interface do aplicativo.'
