# Inspect the local checkout before rc.10 QA. No checkout/reset/clean/stash.
# Produces a local-only source inventory and tracked diff checkpoint.
# Untracked files are LISTED but never copied, changed or uploaded.
[CmdletBinding()]
param(
    [string]$Repository = (Join-Path $env:USERPROFILE 'Git\N3LX_Stem'),
    [string]$ReportsRoot = (Join-Path $env:USERPROFILE 'Git\N3LX_Stem-Releases'),
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$ExpectedSha
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$branch = 'release/v0.21.0-rc.10'

function Assert-Git([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed (exit $LASTEXITCODE). No retry was attempted."
    }
}
function Git-Lines([string[]]$GitArgs) {
    $lines = @(& git -C $Repository @GitArgs)
    Assert-Git ($GitArgs -join ' ')
    return @($lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}
if (-not (Test-Path -LiteralPath $Repository -PathType Container)) {
    throw "Repository directory does not exist: $Repository"
}
$inside = (& git -C $Repository rev-parse --is-inside-work-tree).Trim()
Assert-Git 'Verify repository'
if ($inside -ne 'true') { throw 'Repository path is not a Git worktree' }

# Fetch Git metadata only. Never checkout, reset or clean the local worktree.
& git -C $Repository fetch --no-tags origin "refs/heads/$branch"
Assert-Git 'Fetch rc.10 candidate'
$candidateSha = (& git -C $Repository rev-parse FETCH_HEAD).Trim()
Assert-Git 'Resolve candidate'
if ($candidateSha -ne $ExpectedSha) {
    throw "Candidate changed: found $candidateSha, expected $ExpectedSha. Review the new SHA before continuing."
}
# The release-specific delta must be measured against its own remote main,
# NOT against the older local HEAD. Otherwise old main commits appear as
# candidate changes and inflate the apparent conflicts.
& git -C $Repository fetch --no-tags origin 'refs/heads/main'
Assert-Git 'Fetch remote main metadata'
$remoteMainSha = (& git -C $Repository rev-parse FETCH_HEAD).Trim()
Assert-Git 'Resolve remote main'
& git -C $Repository merge-base --is-ancestor $remoteMainSha $candidateSha
Assert-Git 'Ensure candidate is based on reviewed remote main'
$localSha = (& git -C $Repository rev-parse HEAD).Trim()
Assert-Git 'Read local HEAD'
$mergeBase = (& git -C $Repository merge-base $localSha $remoteMainSha).Trim()
Assert-Git 'Find local/remote-main common ancestor'
$localBranch = (& git -C $Repository branch --show-current).Trim()
Assert-Git 'Read local branch'

# Source-only pathspecs. Do not inspect data/, models, music, environments,
# _workspace/, private exports, backups, or generated releases.
$sourcePaths = @(
    '.github', 'app', 'desktop', 'desktop-app', 'docs', 'packaging',
    'scripts', 'static', 'templates', 'tests',
    'README.md', 'README-UPSTREAM.md', 'ROADMAP.md',
    'package.json', 'package-lock.json', 'pyproject.toml', 'uv.lock',
    'Setup-N3LX_Stem.cmd', 'Start-N3LX_Stem.cmd',
    'Start-StemDeck-AMD.cmd', 'Stop-N3LX_Stem.cmd', 'Stop-StemDeck.cmd'
)
$dirtyTracked = @(Git-Lines (@('diff', '--name-only', 'HEAD', '--') + $sourcePaths))
$untracked = @(Git-Lines (@('ls-files', '--others', '--exclude-standard', '--') + $sourcePaths))
$localCommitted = @(Git-Lines (@('diff', '--name-only', $mergeBase, 'HEAD', '--') + $sourcePaths))
# Candidate-only changes, excluding all commits that were already in main.
$candidateChanged = @(Git-Lines (@('diff', '--name-only', $remoteMainSha, $candidateSha, '--') + $sourcePaths))
$remoteMainUpdates = @(Git-Lines (@('diff', '--name-only', $mergeBase, $remoteMainSha, '--') + $sourcePaths))
$localAll = @(($dirtyTracked + $localCommitted + $untracked) | Sort-Object -Unique)
$candidateLookup = @{}
foreach ($name in $candidateChanged) { $candidateLookup[$name] = $true }
$overlap = @($localAll | Where-Object { $candidateLookup.ContainsKey($_) } | Sort-Object -Unique)
# Additional possible overlap with already-merged main updates is reported
# separately; it is not a PR #24/rc.10-specific conflict count.
$mainLookup = @{}
foreach ($name in $remoteMainUpdates) { $mainLookup[$name] = $true }
$mainOverlap = @($localAll | Where-Object { $mainLookup.ContainsKey($_) } | Sort-Object -Unique)

# This is a private local report, never a branch commit or cloud upload.
# --output asks Git to write raw patch bytes (no PowerShell re-encoding).
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$token = [guid]::NewGuid().ToString('N').Substring(0, 8)
$report = Join-Path $ReportsRoot "rc10-local-review-$stamp-$token"
if (Test-Path -LiteralPath $report) { throw 'Refusing to overwrite an existing report' }
New-Item -ItemType Directory -Path $report -ErrorAction Stop | Out-Null
$patch = Join-Path $report 'tracked-source-changes.patch'
& git -C $Repository diff --binary HEAD "--output=$patch" -- @sourcePaths
Assert-Git 'Write local tracked changes patch'
$summary = [ordered]@{
    purpose = 'Inventory and tracked-source-only patch; NOT a complete backup'
    candidate_branch = $branch
    candidate_sha = $candidateSha
    remote_main_sha = $remoteMainSha
    local_branch = $localBranch
    local_head = $localSha
    local_remote_main_merge_base = $mergeBase
    merge_base = $mergeBase
    dirty_tracked_source_files = $dirtyTracked
    untracked_source_files_not_backed_up = $untracked
    committed_local_source_files_since_merge_base = $localCommitted
    candidate_source_files_since_remote_main = $candidateChanged
    candidate_source_files_since_merge_base = $candidateChanged
    remote_main_updated_files_since_local_common_ancestor = $remoteMainUpdates
    overlapping_rc10_specific_source_files_requiring_review = $overlap
    overlapping_remote_main_history_source_files = $mainOverlap
    overlapping_source_files_requiring_review = $overlap
    tracked_patch_file = 'tracked-source-changes.patch'
    private_library_accessed = $false
    checkout_changed_by_script = $false
    tests_executed = $false
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $report 'inventory.json') -Encoding UTF8
$lines = @(
    '# rc.10 local checkout review'
    ''
    "Candidate: $candidateSha"
    "Remote main: $remoteMainSha"
    "Local HEAD: $localSha ($localBranch)"
    "Local/main common ancestor: $mergeBase"
    ''
    "Dirty tracked source files: $($dirtyTracked.Count)"
    "Untracked source files (not backed up): $($untracked.Count)"
    "Locally committed source files since common ancestor: $($localCommitted.Count)"
    "Candidate-specific source files vs remote main: $($candidateChanged.Count)"
    "POSSIBLE rc.10-specific overlapping paths: $($overlap.Count)"
    "Overlaps with older remote-main updates (separate): $($mainOverlap.Count)"
    ''
    'The tracked-source patch is local only. Untracked source files are NOT'
    'backed up by this tool. Do not reset/clean/stash or replace the checkout'
    'until ALL source changes have been inspected and separately preserved.'
    'No Windows QA, executable build or music migration was performed.'
)
$lines | Set-Content -LiteralPath (Join-Path $report 'RESULT.md') -Encoding UTF8
Write-Host "INVENTORY_COMPLETE_REVIEW_REQUIRED"
Write-Host "CANDIDATE: $candidateSha"
Write-Host "LOCAL_HEAD: $localSha"
Write-Host "DIRTY_TRACKED: $($dirtyTracked.Count)"
Write-Host "UNTRACKED_NOT_BACKED_UP: $($untracked.Count)"
Write-Host "REMOTE_MAIN: $remoteMainSha"
Write-Host "RC10_SPECIFIC_CHANGED: $($candidateChanged.Count)"
Write-Host "RC10_SPECIFIC_OVERLAP: $($overlap.Count)"
Write-Host "MAIN_HISTORY_OVERLAP: $($mainOverlap.Count)"
Write-Host "REPORT: $report"
Write-Host 'STOP: overlaps are possible same-path edits, not proven merge conflicts. Review local source and untracked files before package QA, merge, release, or cleanup.'
