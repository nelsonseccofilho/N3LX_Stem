# N3LX_Stem rc.10: preserve uncommitted SOURCE files outside the checkout.
# One shot, local-only; no checkout/reset/clean/stash/install/build/network/upload.
# Does NOT back up the music library, models, user projects or the whole machine.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InventoryFile,
    [string]$Repository = (Join-Path $env:USERPROFILE 'Git\N3LX_Stem'),
    [string]$ReportsRoot = (Join-Path $env:USERPROFILE 'Git\N3LX_Stem-Releases')
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Git([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE); no retry." }
}
function Git-Lines([string[]]$Args) {
    $value = @(& git -C $Repository @Args)
    Assert-Git ($Args -join ' ')
    return @($value | Where-Object { $_ -is [string] -and $_.Length -gt 0 })
}
function Names($items) {
    return @($items | Where-Object { $_ -is [string] -and $_.Length -gt 0 } | Sort-Object -Unique)
}
function Assert-SameNames($old, $now, [string]$label) {
    $delta = @(Compare-Object -ReferenceObject @(Names $old) -DifferenceObject @(Names $now))
    if ($delta.Count) {
        throw "$label changed since the inventory. Stop and inspect the checkout; no files were overwritten."
    }
}
function Assert-SafeSource([string]$relative, [string]$repoRoot) {
    if ([IO.Path]::IsPathRooted($relative) -or
        $relative -match '(^|[\\/])\.\.([\\/]|$)' -or
        $relative -match '(^|[\\/])(data|jobs|_workspace|node_modules|\.venv|\.venv-directml|models|weights)([\\/]|$)' -or
        $relative -match '(?i)\.(wav|flac|mp3|m4a|ogg|opus|onnx|safetensors|pt|pth|ckpt)$') {
        throw "Unsafe or private-data path; not copied: $relative"
    }
    $abs = [IO.Path]::GetFullPath((Join-Path $repoRoot $relative))
    $prefix = $repoRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $abs.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Source path leaves repository: $relative"
    }
    return $abs
}
function Assert-NoReparse([string]$full, [string]$repoRoot) {
    $next = $full
    while ($next.Length -ge $repoRoot.Length) {
        if (Test-Path -LiteralPath $next) {
            $item = Get-Item -LiteralPath $next -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Refusing symlink or junction in checkpoint path: $next"
            }
        }
        if ($next -eq $repoRoot) { break }
        $parent = [IO.Path]::GetDirectoryName($next)
        if (-not $parent -or $parent -eq $next) { break }
        $next = $parent
    }
}

$Repository = (Resolve-Path -LiteralPath $Repository -ErrorAction Stop).Path.TrimEnd('\', '/')
$InventoryFile = (Resolve-Path -LiteralPath $InventoryFile -ErrorAction Stop).Path
$inventory = Get-Content -LiteralPath $InventoryFile -Raw | ConvertFrom-Json
if (-not $inventory.local_head -or -not $inventory.candidate_sha) {
    throw 'Inventory is missing the original local and candidate commit identifiers.'
}
$local = (& git -C $Repository rev-parse HEAD).Trim()
Assert-Git 'Read HEAD'
if ($local -ne $inventory.local_head) {
    throw "Local HEAD changed ($local). Do not use a stale inventory."
}
$srcPaths = @(
    '.github', 'app', 'desktop', 'desktop-app', 'docs', 'packaging',
    'scripts', 'static', 'templates', 'tests',
    'README.md', 'README-UPSTREAM.md', 'ROADMAP.md',
    '.gitignore', '.gitattributes', '.dockerignore', '.trivyignore',
    'run.sh', 'playwright.config.mjs', 'build',
    'package.json', 'package-lock.json', 'pyproject.toml', 'uv.lock',
    'Setup-N3LX_Stem.cmd', 'Start-N3LX_Stem.cmd',
    'Start-StemDeck-AMD.cmd', 'Stop-N3LX_Stem.cmd', 'Stop-StemDeck.cmd'
)
$tracked = @(Names $inventory.dirty_tracked_source_files)
$untracked = @(Names $inventory.untracked_source_files_not_backed_up)
$nowTracked = @(Git-Lines (@('diff', '--name-only', 'HEAD', '--') + $srcPaths))
$nowUntracked = @(Git-Lines (@('ls-files', '--others', '--exclude-standard', '--') + $srcPaths))
Assert-SameNames $tracked $nowTracked 'Tracked source file list'
Assert-SameNames $untracked $nowUntracked 'Untracked source file list'

$reportBase = [IO.Path]::GetFullPath($ReportsRoot)
$repoPrefix = $Repository + [IO.Path]::DirectorySeparatorChar
if ($reportBase.Equals($Repository, [StringComparison]::OrdinalIgnoreCase) -or
    $reportBase.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Backup destination must be outside the repository checkout.'
}
if (-not (Test-Path -LiteralPath $reportBase -PathType Container)) {
    throw "Report root does not exist: $reportBase"
}
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$token = [guid]::NewGuid().ToString('N').Substring(0, 8)
$destination = Join-Path $reportBase "rc10-source-checkpoint-$stamp-$token"
New-Item -ItemType Directory -Path $destination -ErrorAction Stop | Out-Null
Set-Content -LiteralPath (Join-Path $destination 'STATUS.txt') -Value 'INCOMPLETE: do not treat this folder as a verified checkpoint.' -Encoding UTF8

$patch = Join-Path $destination 'tracked-working-tree.patch'
& git -C $Repository diff --binary HEAD "--output=$patch" -- @srcPaths
Assert-Git 'Save tracked source patch'

$entries = New-Object System.Collections.ArrayList
$missingTracked = New-Object System.Collections.ArrayList
foreach ($kind in @('tracked', 'untracked')) {
    $paths = if ($kind -eq 'tracked') { $tracked } else { $untracked }
    foreach ($relative in $paths) {
        $absolute = Assert-SafeSource $relative $Repository
        if (-not (Test-Path -LiteralPath $absolute -PathType Leaf)) {
            if ($kind -eq 'tracked' -and -not (Test-Path -LiteralPath $absolute)) {
                [void]$missingTracked.Add($relative)
                continue  # deletion is stored in the tracked patch
            }
            throw "Source file cannot be copied as a regular file: $relative"
        }
        Assert-NoReparse $absolute $Repository
        $before = (Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash.ToLowerInvariant()
        $target = Join-Path (Join-Path $destination 'source-files') $relative
        $parent = Split-Path -Parent $target
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $absolute -Destination $target -ErrorAction Stop
        $after = (Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash.ToLowerInvariant()
        $copyHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($before -ne $after -or $before -ne $copyHash) {
            throw "Source changed during checkpoint or copy mismatch: $relative"
        }
        [void]$entries.Add([ordered]@{
            path = $relative
            kind = $kind
            sha256 = $copyHash
            bytes = (Get-Item -LiteralPath $target).Length
        })
    }
}
Assert-SameNames $tracked @(Git-Lines (@('diff', '--name-only', 'HEAD', '--') + $srcPaths)) 'Tracked paths after copy'
Assert-SameNames $untracked @(Git-Lines (@('ls-files', '--others', '--exclude-standard', '--') + $srcPaths)) 'Untracked paths after copy'
$endHead = (& git -C $Repository rev-parse HEAD).Trim()
Assert-Git 'Read ending HEAD'
if ($endHead -ne $local) { throw 'HEAD changed during checkpoint.' }

$manifest = [ordered]@{
    type = 'private local source checkpoint (not a full library or machine backup)'
    original_inventory = $InventoryFile
    local_head = $local
    candidate_when_inventoried = $inventory.candidate_sha
    tracked_changed_paths = $tracked.Count
    untracked_paths = $untracked.Count
    tracked_deleted_paths_in_patch = @($missingTracked)
    saved_file_count = $entries.Count
    patch_sha256 = (Get-FileHash -LiteralPath $patch -Algorithm SHA256).Hash.ToLowerInvariant()
    files = @($entries)
    modifies_checkout = $false
    includes_music_library = $false
    uploaded_to_cloud = $false
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $destination 'manifest.json') -Encoding UTF8
Set-Content -LiteralPath (Join-Path $destination 'STATUS.txt') -Value 'CHECKPOINT_VERIFIED: local source copies and tracked patch saved with hashes. Not a full-machine backup.' -Encoding UTF8
Write-Host 'SOURCE_CHECKPOINT_VERIFIED'
Write-Host "LOCAL_HEAD: $local"
Write-Host "TRACKED_SOURCE: $($tracked.Count)"
Write-Host "UNTRACKED_SOURCE_SAVED: $($untracked.Count)"
Write-Host "SAVED_FILES: $($entries.Count)"
Write-Host "TRACKED_DELETIONS_IN_PATCH: $($missingTracked.Count)"
Write-Host "CHECKPOINT: $destination"
Write-Host 'STOP: keep this private local checkpoint and inspect its manifest; no merge, package build or cleanup was performed.'
