# N3LX_Stem rc.9: one-shot non-destructive Windows package preflight.
# Does NOT launch the user library, install dependencies, or publish a release.
[CmdletBinding()]
param(
    [string]$Repository = (Join-Path $env:USERPROFILE 'Git\N3LX_Stem'),
    [string]$ReleasesRoot = (Join-Path $env:USERPROFILE 'Git\N3LX_Stem-Releases'),
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$version = '0.21.0-rc.10'
$branch = 'release/v0.21.0-rc.10'
$baseSha = '1ca88e17d37ecf72e932cecd0a0570ae5949ed98'
function Assert-Exit([string]$step) {
    if ($LASTEXITCODE -ne 0) { throw "$step failed (exit $LASTEXITCODE); no retry attempted." }
}
function Require-File([string]$path) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}
Require-File (Join-Path $Repository '.venv\Scripts\python.exe')
Require-File (Join-Path $Repository '.venv-directml\Scripts\python.exe')
$python = Join-Path $Repository '.venv\Scripts\python.exe'
$electronDist = Join-Path $Repository 'desktop-app\node_modules\electron\dist'
Require-File (Join-Path $electronDist 'electron.exe')
Require-File (Join-Path $electronDist 'version')
$electron = (Get-Content -LiteralPath (Join-Path $electronDist 'version') -Raw).Trim()
if ($electron -ne '44.3.0') { throw "Installed Electron is $electron; expected 44.3.0" }
$node = (Get-Command node.exe -ErrorAction Stop).Source

# Fetch only Git metadata. Preserve the current checkout and all user data.
& git -C $Repository fetch --no-tags origin "refs/heads/$branch"
Assert-Exit 'Fetch candidate'
$revision = (& git -C $Repository rev-parse FETCH_HEAD).Trim()
Assert-Exit 'Resolve candidate SHA'
if ($revision -notmatch '^[0-9a-f]{40}
& git -C $Repository merge-base --is-ancestor $baseSha $revision
Assert-Exit 'Confirm all merged fixes are ancestors'
# This candidate consolidates PR #21/#22/#23, so the old five-file
# allowlist is invalid. Pin the exact reviewed SHA and record its file list.
$changed = @(& git -C $Repository diff --name-only "$baseSha..$revision")
Assert-Exit 'Inspect candidate diff'
if ($changed.Count -eq 0) { throw 'Candidate has no changes' }
foreach ($name in $changed) {
    if ($name -match '(^|/)(data|jobs|\.venv|node_modules|_workspace)(/|$)' -or
        $name -match '\.(wav|mp3|flac|onnx|safetensors)$') {
        throw "Unexpected private data in candidate: $name"
    }
}

# Each run creates new directories. No reset, cleanup, overwrite, or package install.
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$token = [guid]::NewGuid().ToString('N').Substring(0, 8)
$runRoot = Join-Path $ReleasesRoot "$version-$stamp-$token"
$source = Join-Path $runRoot 'isolated-source'
$report = Join-Path $runRoot 'local-QA'
$output = Join-Path $runRoot 'Windows-package'
New-Item -ItemType Directory -Path $runRoot -ErrorAction Stop | Out-Null
& git -C $Repository worktree add --detach $source $revision
Assert-Exit 'Create isolated worktree'
$packageJson = Get-Content -LiteralPath (Join-Path $source 'desktop-app\package.json') -Raw | ConvertFrom-Json
if ($packageJson.version -ne $version) { throw 'Unexpected source version' }
if ($packageJson.devDependencies.electron -ne $electron) { throw 'Electron pin mismatch' }

# Official QA: isolated scratch paths and one bounded test pass; no real models.
& $python (Join-Path $source 'scripts\verify-local-release.py') --python $python --node $node --report-dir $report
Assert-Exit 'Local QA'
$qa = Get-Content -LiteralPath (Join-Path $report 'summary.json') -Raw | ConvertFrom-Json
if (-not $qa.passed -or $qa.revision -ne $revision) {
    throw 'Local QA evidence does not match the source SHA or PASS state'
}
$gateText = Get-Content -LiteralPath (Join-Path $source 'scripts\verify-local-release.py') -Raw
foreach ($test in @(
    'test_drum_float_alignment.py',
    'test_residue_export.py',
    'test_karaoke_workspace_large_v3.py',
    'test_stems_location.py',
    'desktop-storage-paths',
    'desktop-backend-lifecycle'
)) {
    if (-not $gateText.Contains($test)) { throw "Release regression gate missing $test" }
}

# Official packager uses the installed Electron binary and tracked sources only.
& $python (Join-Path $source 'scripts\build-windows-update.py') --source $source --installation $Repository --output $output
Assert-Exit 'Build Windows update'
$packageName = "N3LX_Stem-Windows-Update-$version"
$packageRoot = Join-Path $output $packageName
$zip = Join-Path $output "$packageName.zip"
$checksum = "$zip.sha256"
Require-File $zip
Require-File $checksum
Require-File (Join-Path $packageRoot 'N3LX_Stem.exe')
$buildInfo = Get-Content -LiteralPath (Join-Path $packageRoot 'build-info.json') -Raw | ConvertFrom-Json
if ($buildInfo.source_revision -ne $revision -or $buildInfo.version -ne $version) {
    throw 'Packaged build-info.json has the wrong version or SHA'
}
$sha = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
$expected = ((Get-Content -LiteralPath $checksum -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
if ($sha -ne $expected) { throw 'ZIP SHA-256 mismatch' }

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
try {
    $names = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
    foreach ($required in @(
        "$packageName/N3LX_Stem.exe",
        "$packageName/build-info.json",
        "$packageName/resources/app/package.json",
        "$packageName/resources/stemdeck/app/pipeline/complete_multitrack.py",
        "$packageName/resources/stemdeck/app/pipeline/residue_export.py",
        "$packageName/resources/stemdeck/app/pipeline/karaoke_timing.py",
        "$packageName/resources/stemdeck/app/core/stems_location.py",
        "$packageName/resources/stemdeck/static/js/storageSettings.js",
        "$packageName/resources/app/preload.cjs",
        "$packageName/resources/stemdeck/static/version.json",
        "$packageName/sha256-manifest.json"
    )) {
        if ($required -notin $names) { throw "Missing ZIP member: $required" }
    }
    foreach ($name in $names) {
        if ($name -match '(^|/)(data|jobs|weights|\.venv|\.venv-directml)(/|$)' -or
            $name -match '\.(wav|mp3|flac|ogg|m4a|opus)$') {
            throw "Unexpected runtime/private payload: $name"
        }
    }
} finally {
    $archive.Dispose()
}
$evidence = [ordered]@{
    status = 'LOCAL_QA_AND_PACKAGE_PASS_WINDOWS_RUNTIME_QA_PENDING'
    version = $version
    revision = $revision
    source_base = $baseSha
    expected_sha = $ExpectedSha
    changed_source_files = $changed
    local_qa_passed = $qa.passed
    electron_version = $electron
    zip_sha256 = $sha
    zip_path = $zip
    report_path = (Join-Path $report 'RESULT.md')
    tested_packaged_exe = $false
    tested_real_gpu_inference = $false
    tested_existing_music_library = $false
    migrated_existing_music_library = $false
    hosted_ci_claimed = $false
    github_release_published = $false
}
$evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runRoot 'release-preflight.json') -Encoding UTF8
Write-Host "PREFLIGHT_PASS_RUNTIME_QA_PENDING"
Write-Host "COMMIT: $revision"
Write-Host "ZIP: $zip"
Write-Host "SHA256: $sha"
Write-Host "QA: $report"
Write-Host "STOP: packed EXE/backend/Vulkan/CPU alignment/Settings/Downloads need real Windows QA before GitHub publication or cleanup."
)]
    [string]$ExpectedSha
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$version = '0.21.0-rc.9'
$branch = 'release/v0.21.0-rc.9'
$baseSha = '1ca88e17d37ecf72e932cecd0a0570ae5949ed98'
$allowedChanges = @(
    'desktop-app/package.json',
    'desktop-app/main.cjs',
    'scripts/verify-local-release.py',
    'tests/js/desktop-backend-lifecycle.test.mjs',
    'scripts/windows/Prepare-Windows-Release-rc9.ps1'
)
function Assert-Exit([string]$step) {
    if ($LASTEXITCODE -ne 0) { throw "$step failed (exit $LASTEXITCODE); no retry attempted." }
}
function Require-File([string]$path) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}
Require-File (Join-Path $Repository '.venv\Scripts\python.exe')
Require-File (Join-Path $Repository '.venv-directml\Scripts\python.exe')
$python = Join-Path $Repository '.venv\Scripts\python.exe'
$electronDist = Join-Path $Repository 'desktop-app\node_modules\electron\dist'
Require-File (Join-Path $electronDist 'electron.exe')
Require-File (Join-Path $electronDist 'version')
$electron = (Get-Content -LiteralPath (Join-Path $electronDist 'version') -Raw).Trim()
if ($electron -ne '44.3.0') { throw "Installed Electron is $electron; expected 44.3.0" }
$node = (Get-Command node.exe -ErrorAction Stop).Source

# Fetch only Git metadata. Preserve the current checkout and all user data.
& git -C $Repository fetch --no-tags origin "refs/heads/$branch"
Assert-Exit 'Fetch candidate'
$revision = (& git -C $Repository rev-parse FETCH_HEAD).Trim()
Assert-Exit 'Resolve candidate SHA'
if ($revision -notmatch '^[0-9a-f]{40}$') { throw 'Invalid candidate SHA' }
& git -C $Repository merge-base --is-ancestor $baseSha $revision
Assert-Exit 'Confirm all merged fixes are ancestors'
$changed = @(& git -C $Repository diff --name-only "$baseSha..$revision")
Assert-Exit 'Inspect candidate diff'
foreach ($name in $changed) {
    if ($name -notin $allowedChanges) { throw "Unexpected release branch change: $name" }
}

# Each run creates new directories. No reset, cleanup, overwrite, or package install.
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$token = [guid]::NewGuid().ToString('N').Substring(0, 8)
$runRoot = Join-Path $ReleasesRoot "$version-$stamp-$token"
$source = Join-Path $runRoot 'isolated-source'
$report = Join-Path $runRoot 'local-QA'
$output = Join-Path $runRoot 'Windows-package'
New-Item -ItemType Directory -Path $runRoot -ErrorAction Stop | Out-Null
& git -C $Repository worktree add --detach $source $revision
Assert-Exit 'Create isolated worktree'
$packageJson = Get-Content -LiteralPath (Join-Path $source 'desktop-app\package.json') -Raw | ConvertFrom-Json
if ($packageJson.version -ne $version) { throw 'Unexpected source version' }
if ($packageJson.devDependencies.electron -ne $electron) { throw 'Electron pin mismatch' }

# Official QA: isolated scratch paths and one bounded test pass; no real models.
& $python (Join-Path $source 'scripts\verify-local-release.py') --python $python --node $node --report-dir $report
Assert-Exit 'Local QA'
$qa = Get-Content -LiteralPath (Join-Path $report 'summary.json') -Raw | ConvertFrom-Json
if (-not $qa.passed -or $qa.revision -ne $revision) {
    throw 'Local QA evidence does not match the source SHA or PASS state'
}
$gateText = Get-Content -LiteralPath (Join-Path $source 'scripts\verify-local-release.py') -Raw
foreach ($test in @('test_drum_float_alignment.py', 'test_residue_export.py')) {
    if (-not $gateText.Contains($test)) { throw "Release regression gate missing $test" }
}

# Official packager uses the installed Electron binary and tracked sources only.
& $python (Join-Path $source 'scripts\build-windows-update.py') --source $source --installation $Repository --output $output
Assert-Exit 'Build Windows update'
$packageName = "N3LX_Stem-Windows-Update-$version"
$packageRoot = Join-Path $output $packageName
$zip = Join-Path $output "$packageName.zip"
$checksum = "$zip.sha256"
Require-File $zip
Require-File $checksum
Require-File (Join-Path $packageRoot 'N3LX_Stem.exe')
$buildInfo = Get-Content -LiteralPath (Join-Path $packageRoot 'build-info.json') -Raw | ConvertFrom-Json
if ($buildInfo.source_revision -ne $revision -or $buildInfo.version -ne $version) {
    throw 'Packaged build-info.json has the wrong version or SHA'
}
$sha = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
$expected = ((Get-Content -LiteralPath $checksum -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
if ($sha -ne $expected) { throw 'ZIP SHA-256 mismatch' }

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
try {
    $names = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
    foreach ($required in @(
        "$packageName/N3LX_Stem.exe",
        "$packageName/build-info.json",
        "$packageName/resources/app/package.json",
        "$packageName/resources/stemdeck/app/pipeline/complete_multitrack.py",
        "$packageName/resources/stemdeck/app/pipeline/residue_export.py",
        "$packageName/resources/stemdeck/static/version.json",
        "$packageName/sha256-manifest.json"
    )) {
        if ($required -notin $names) { throw "Missing ZIP member: $required" }
    }
    foreach ($name in $names) {
        if ($name -match '(^|/)(data|jobs|weights|\.venv|\.venv-directml)(/|$)' -or
            $name -match '\.(wav|mp3|flac|ogg|m4a|opus)$') {
            throw "Unexpected runtime/private payload: $name"
        }
    }
} finally {
    $archive.Dispose()
}
$evidence = [ordered]@{
    status = 'LOCAL_QA_AND_PACKAGE_PASS_WINDOWS_RUNTIME_QA_PENDING'
    version = $version
    revision = $revision
    source_base = $baseSha
    local_qa_passed = $qa.passed
    electron_version = $electron
    zip_sha256 = $sha
    zip_path = $zip
    report_path = (Join-Path $report 'RESULT.md')
    tested_packaged_exe = $false
    tested_real_gpu_inference = $false
    hosted_ci_claimed = $false
    github_release_published = $false
}
$evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runRoot 'release-preflight.json') -Encoding UTF8
Write-Host "PREFLIGHT_PASS_RUNTIME_QA_PENDING"
Write-Host "COMMIT: $revision"
Write-Host "ZIP: $zip"
Write-Host "SHA256: $sha"
Write-Host "QA: $report"
Write-Host "STOP: packed EXE/backend/DirectML/Vulkan/UI need real Windows QA before any GitHub publication."
) { throw 'Invalid candidate SHA' }
if ($revision -ne $ExpectedSha) { throw "Candidate SHA changed ($revision); expected $ExpectedSha. Refusing to build unreviewed content." }
& git -C $Repository merge-base --is-ancestor $baseSha $revision
Assert-Exit 'Confirm all merged fixes are ancestors'
$changed = @(& git -C $Repository diff --name-only "$baseSha..$revision")
Assert-Exit 'Inspect candidate diff'
foreach ($name in $changed) {
    if ($name -notin $allowedChanges) { throw "Unexpected release branch change: $name" }
}

# Each run creates new directories. No reset, cleanup, overwrite, or package install.
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$token = [guid]::NewGuid().ToString('N').Substring(0, 8)
$runRoot = Join-Path $ReleasesRoot "$version-$stamp-$token"
$source = Join-Path $runRoot 'isolated-source'
$report = Join-Path $runRoot 'local-QA'
$output = Join-Path $runRoot 'Windows-package'
New-Item -ItemType Directory -Path $runRoot -ErrorAction Stop | Out-Null
& git -C $Repository worktree add --detach $source $revision
Assert-Exit 'Create isolated worktree'
$packageJson = Get-Content -LiteralPath (Join-Path $source 'desktop-app\package.json') -Raw | ConvertFrom-Json
if ($packageJson.version -ne $version) { throw 'Unexpected source version' }
if ($packageJson.devDependencies.electron -ne $electron) { throw 'Electron pin mismatch' }

# Official QA: isolated scratch paths and one bounded test pass; no real models.
& $python (Join-Path $source 'scripts\verify-local-release.py') --python $python --node $node --report-dir $report
Assert-Exit 'Local QA'
$qa = Get-Content -LiteralPath (Join-Path $report 'summary.json') -Raw | ConvertFrom-Json
if (-not $qa.passed -or $qa.revision -ne $revision) {
    throw 'Local QA evidence does not match the source SHA or PASS state'
}
$gateText = Get-Content -LiteralPath (Join-Path $source 'scripts\verify-local-release.py') -Raw
foreach ($test in @('test_drum_float_alignment.py', 'test_residue_export.py')) {
    if (-not $gateText.Contains($test)) { throw "Release regression gate missing $test" }
}

# Official packager uses the installed Electron binary and tracked sources only.
& $python (Join-Path $source 'scripts\build-windows-update.py') --source $source --installation $Repository --output $output
Assert-Exit 'Build Windows update'
$packageName = "N3LX_Stem-Windows-Update-$version"
$packageRoot = Join-Path $output $packageName
$zip = Join-Path $output "$packageName.zip"
$checksum = "$zip.sha256"
Require-File $zip
Require-File $checksum
Require-File (Join-Path $packageRoot 'N3LX_Stem.exe')
$buildInfo = Get-Content -LiteralPath (Join-Path $packageRoot 'build-info.json') -Raw | ConvertFrom-Json
if ($buildInfo.source_revision -ne $revision -or $buildInfo.version -ne $version) {
    throw 'Packaged build-info.json has the wrong version or SHA'
}
$sha = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
$expected = ((Get-Content -LiteralPath $checksum -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
if ($sha -ne $expected) { throw 'ZIP SHA-256 mismatch' }

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
try {
    $names = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
    foreach ($required in @(
        "$packageName/N3LX_Stem.exe",
        "$packageName/build-info.json",
        "$packageName/resources/app/package.json",
        "$packageName/resources/stemdeck/app/pipeline/complete_multitrack.py",
        "$packageName/resources/stemdeck/app/pipeline/residue_export.py",
        "$packageName/resources/stemdeck/static/version.json",
        "$packageName/sha256-manifest.json"
    )) {
        if ($required -notin $names) { throw "Missing ZIP member: $required" }
    }
    foreach ($name in $names) {
        if ($name -match '(^|/)(data|jobs|weights|\.venv|\.venv-directml)(/|$)' -or
            $name -match '\.(wav|mp3|flac|ogg|m4a|opus)$') {
            throw "Unexpected runtime/private payload: $name"
        }
    }
} finally {
    $archive.Dispose()
}
$evidence = [ordered]@{
    status = 'LOCAL_QA_AND_PACKAGE_PASS_WINDOWS_RUNTIME_QA_PENDING'
    version = $version
    revision = $revision
    source_base = $baseSha
    local_qa_passed = $qa.passed
    electron_version = $electron
    zip_sha256 = $sha
    zip_path = $zip
    report_path = (Join-Path $report 'RESULT.md')
    tested_packaged_exe = $false
    tested_real_gpu_inference = $false
    hosted_ci_claimed = $false
    github_release_published = $false
}
$evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runRoot 'release-preflight.json') -Encoding UTF8
Write-Host "PREFLIGHT_PASS_RUNTIME_QA_PENDING"
Write-Host "COMMIT: $revision"
Write-Host "ZIP: $zip"
Write-Host "SHA256: $sha"
Write-Host "QA: $report"
Write-Host "STOP: packed EXE/backend/DirectML/Vulkan/UI need real Windows QA before any GitHub publication."
)]
    [string]$ExpectedSha
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$version = '0.21.0-rc.9'
$branch = 'release/v0.21.0-rc.9'
$baseSha = '1ca88e17d37ecf72e932cecd0a0570ae5949ed98'
$allowedChanges = @(
    'desktop-app/package.json',
    'desktop-app/main.cjs',
    'scripts/verify-local-release.py',
    'tests/js/desktop-backend-lifecycle.test.mjs',
    'scripts/windows/Prepare-Windows-Release-rc9.ps1'
)
function Assert-Exit([string]$step) {
    if ($LASTEXITCODE -ne 0) { throw "$step failed (exit $LASTEXITCODE); no retry attempted." }
}
function Require-File([string]$path) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}
Require-File (Join-Path $Repository '.venv\Scripts\python.exe')
Require-File (Join-Path $Repository '.venv-directml\Scripts\python.exe')
$python = Join-Path $Repository '.venv\Scripts\python.exe'
$electronDist = Join-Path $Repository 'desktop-app\node_modules\electron\dist'
Require-File (Join-Path $electronDist 'electron.exe')
Require-File (Join-Path $electronDist 'version')
$electron = (Get-Content -LiteralPath (Join-Path $electronDist 'version') -Raw).Trim()
if ($electron -ne '44.3.0') { throw "Installed Electron is $electron; expected 44.3.0" }
$node = (Get-Command node.exe -ErrorAction Stop).Source

# Fetch only Git metadata. Preserve the current checkout and all user data.
& git -C $Repository fetch --no-tags origin "refs/heads/$branch"
Assert-Exit 'Fetch candidate'
$revision = (& git -C $Repository rev-parse FETCH_HEAD).Trim()
Assert-Exit 'Resolve candidate SHA'
if ($revision -notmatch '^[0-9a-f]{40}$') { throw 'Invalid candidate SHA' }
& git -C $Repository merge-base --is-ancestor $baseSha $revision
Assert-Exit 'Confirm all merged fixes are ancestors'
$changed = @(& git -C $Repository diff --name-only "$baseSha..$revision")
Assert-Exit 'Inspect candidate diff'
foreach ($name in $changed) {
    if ($name -notin $allowedChanges) { throw "Unexpected release branch change: $name" }
}

# Each run creates new directories. No reset, cleanup, overwrite, or package install.
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$token = [guid]::NewGuid().ToString('N').Substring(0, 8)
$runRoot = Join-Path $ReleasesRoot "$version-$stamp-$token"
$source = Join-Path $runRoot 'isolated-source'
$report = Join-Path $runRoot 'local-QA'
$output = Join-Path $runRoot 'Windows-package'
New-Item -ItemType Directory -Path $runRoot -ErrorAction Stop | Out-Null
& git -C $Repository worktree add --detach $source $revision
Assert-Exit 'Create isolated worktree'
$packageJson = Get-Content -LiteralPath (Join-Path $source 'desktop-app\package.json') -Raw | ConvertFrom-Json
if ($packageJson.version -ne $version) { throw 'Unexpected source version' }
if ($packageJson.devDependencies.electron -ne $electron) { throw 'Electron pin mismatch' }

# Official QA: isolated scratch paths and one bounded test pass; no real models.
& $python (Join-Path $source 'scripts\verify-local-release.py') --python $python --node $node --report-dir $report
Assert-Exit 'Local QA'
$qa = Get-Content -LiteralPath (Join-Path $report 'summary.json') -Raw | ConvertFrom-Json
if (-not $qa.passed -or $qa.revision -ne $revision) {
    throw 'Local QA evidence does not match the source SHA or PASS state'
}
$gateText = Get-Content -LiteralPath (Join-Path $source 'scripts\verify-local-release.py') -Raw
foreach ($test in @('test_drum_float_alignment.py', 'test_residue_export.py')) {
    if (-not $gateText.Contains($test)) { throw "Release regression gate missing $test" }
}

# Official packager uses the installed Electron binary and tracked sources only.
& $python (Join-Path $source 'scripts\build-windows-update.py') --source $source --installation $Repository --output $output
Assert-Exit 'Build Windows update'
$packageName = "N3LX_Stem-Windows-Update-$version"
$packageRoot = Join-Path $output $packageName
$zip = Join-Path $output "$packageName.zip"
$checksum = "$zip.sha256"
Require-File $zip
Require-File $checksum
Require-File (Join-Path $packageRoot 'N3LX_Stem.exe')
$buildInfo = Get-Content -LiteralPath (Join-Path $packageRoot 'build-info.json') -Raw | ConvertFrom-Json
if ($buildInfo.source_revision -ne $revision -or $buildInfo.version -ne $version) {
    throw 'Packaged build-info.json has the wrong version or SHA'
}
$sha = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
$expected = ((Get-Content -LiteralPath $checksum -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
if ($sha -ne $expected) { throw 'ZIP SHA-256 mismatch' }

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
try {
    $names = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
    foreach ($required in @(
        "$packageName/N3LX_Stem.exe",
        "$packageName/build-info.json",
        "$packageName/resources/app/package.json",
        "$packageName/resources/stemdeck/app/pipeline/complete_multitrack.py",
        "$packageName/resources/stemdeck/app/pipeline/residue_export.py",
        "$packageName/resources/stemdeck/static/version.json",
        "$packageName/sha256-manifest.json"
    )) {
        if ($required -notin $names) { throw "Missing ZIP member: $required" }
    }
    foreach ($name in $names) {
        if ($name -match '(^|/)(data|jobs|weights|\.venv|\.venv-directml)(/|$)' -or
            $name -match '\.(wav|mp3|flac|ogg|m4a|opus)$') {
            throw "Unexpected runtime/private payload: $name"
        }
    }
} finally {
    $archive.Dispose()
}
$evidence = [ordered]@{
    status = 'LOCAL_QA_AND_PACKAGE_PASS_WINDOWS_RUNTIME_QA_PENDING'
    version = $version
    revision = $revision
    source_base = $baseSha
    local_qa_passed = $qa.passed
    electron_version = $electron
    zip_sha256 = $sha
    zip_path = $zip
    report_path = (Join-Path $report 'RESULT.md')
    tested_packaged_exe = $false
    tested_real_gpu_inference = $false
    hosted_ci_claimed = $false
    github_release_published = $false
}
$evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runRoot 'release-preflight.json') -Encoding UTF8
Write-Host "PREFLIGHT_PASS_RUNTIME_QA_PENDING"
Write-Host "COMMIT: $revision"
Write-Host "ZIP: $zip"
Write-Host "SHA256: $sha"
Write-Host "QA: $report"
Write-Host "STOP: packed EXE/backend/DirectML/Vulkan/UI need real Windows QA before any GitHub publication."
