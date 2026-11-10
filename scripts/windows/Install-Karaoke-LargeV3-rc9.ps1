# Targeted, rollback-capable hotfix for an existing rc.9 Windows update.
# Never changes the source checkout, runtime venvs, model weights, or music library.
param(
    [string]$GitRoot = (Join-Path $env:USERPROFILE 'Git')
)
$ErrorActionPreference = 'Stop'
$sourceRevision = 'c61cf01d872c4d3f40cba453854abfc29917feab'
$releaseRevision = '97131ac814f5f47a9ec56c9edb645a9f1e7bfd13'
$package = Join-Path $GitRoot 'N3LX_Stem-Releases\0.21.0-rc.9-20261102-043836-6ed8e87c\Windows-package\N3LX_Stem-Windows-Update-0.21.0-rc.9'
$backend = Join-Path $package 'resources\stemdeck'
$runtime = Join-Path $GitRoot 'N3LX_Stem'
$metadata = Join-Path $package 'build-info.json'
if (-not (Test-Path -LiteralPath (Join-Path $package 'N3LX_Stem.exe'))) { throw 'Pacote rc.9 nao encontrado. Nada alterado.' }
if (-not (Test-Path -LiteralPath $metadata)) { throw 'Metadados do pacote ausentes. Nada alterado.' }
$info = Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json
if ($info.version -ne '0.21.0-rc.9' -or $info.source_revision -ne $releaseRevision) {
    throw 'Identidade do pacote nao corresponde ao build verificado. Nada alterado.'
}
if (Get-Process -Name 'N3LX_Stem' -ErrorAction SilentlyContinue) {
    throw 'Feche o aplicativo N3LX_Stem antes de aplicar o patch. Nada alterado.'
}
if (Get-NetTCPConnection -LocalPort 8140 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Backend ainda ativo na porta 8140. Feche-o antes de aplicar o patch. Nada alterado.'
}
$python = Join-Path $runtime '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python do runtime N3LX_Stem ausente. Nada alterado.' }
Get-Command git.exe, node.exe -ErrorAction Stop | Out-Null

$files = @(
    @{ path='scripts/Start-N3LX_Stem.ps1'; old='c16106d30010aaaaedfbfab2e864ce81056df89c'; new='2883bbba49597f2a06d409363b77ee7c0658e54e' },
    @{ path='app/api/karaoke.py'; old='f99bcfdafe811e9f2623b551a3dbcb8cb544c7f7'; new='ac7aa5d294682e344d76c80d696560ee9c1ba66c' },
    @{ path='app/pipeline/karaoke_timing.py'; old='507d54e66eca1985a48a90bf879b1e530d6dff9d'; new='efee84b15174575b825b73b999aa47a125f6afe8' },
    @{ path='static/index.html'; old='b3f1d45e7558283d83087ed652578b73512fbafd'; new='18db26883b82a0ed4d4ef91cabff28f3906b8487' },
    @{ path='static/js/lyrics.js'; old='3c6fd5d354d92db6329fe78c89584af44c083a45'; new='0eb3b28f669e0445c3573996620e9c81636539fb' },
    @{ path='static/js/i18n.js'; old='7e8bdfde0dff6938fd0dbec510828f91b0747a33'; new='667ae437c74ec9a26d9c887f6d9b1fbecab7b408' }
)
function GitBlob([string]$file) {
    $actual = (& git.exe hash-object -- "$file" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Falha verificando hash Git: $file" }
    return $actual
}
function NormalizedGitBlob([string]$file) {
    # A Windows clone may have CRLF while the GitHub blob uses LF.
    # Allow ONLY that line-ending difference; reject content changes.
    $bytes = [IO.File]::ReadAllBytes($file)
    $normalized = [Text.Encoding]::UTF8.GetBytes(
        ([Text.Encoding]::UTF8.GetString($bytes)).Replace("`r`n", "`n")
    )
    $header = [Text.Encoding]::ASCII.GetBytes("blob $($normalized.Length)`0")
    $payload = New-Object byte[] ($header.Length + $normalized.Length)
    [Array]::Copy($header, 0, $payload, 0, $header.Length)
    [Array]::Copy($normalized, 0, $payload, $header.Length, $normalized.Length)
    $sha = [Security.Cryptography.SHA1]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($payload))).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }
}
foreach ($f in $files) {
    $target = Join-Path $backend ($f.path.Replace('/', '\'))
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Arquivo do pacote ausente: $($f.path)" }
    $exact = GitBlob $target
    if ($exact -ne $f.old -and (NormalizedGitBlob $target) -ne $f.old) {
        throw "Arquivo do pacote alterado: $($f.path). Nao sobrescrever."
    }
}
$backup = Join-Path $GitRoot ('_workspace\qa\n3lx-karaoke-rc9-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$staging = Join-Path $backup 'staged'
$original = Join-Path $backup 'original'
New-Item -ItemType Directory -Path $staging,$original -Force | Out-Null
foreach ($f in $files) {
    $target = Join-Path $backend ($f.path.Replace('/', '\'))
    $stage = Join-Path $staging ($f.path.Replace('/', '\'))
    $saved = Join-Path $original ($f.path.Replace('/', '\'))
    New-Item -ItemType Directory -Path (Split-Path $stage -Parent),(Split-Path $saved -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $target -Destination $saved
    $uri = "https://raw.githubusercontent.com/nelsonseccofilho/N3LX_Stem/$sourceRevision/$($f.path)"
    Invoke-WebRequest -Uri $uri -OutFile $stage -UseBasicParsing
    if ((GitBlob $stage) -ne $f.new) { throw "Hash do download incorreto: $($f.path). Nada alterado." }
}

& $python -m py_compile (Join-Path $staging 'app\api\karaoke.py') (Join-Path $staging 'app\pipeline\karaoke_timing.py')
if ($LASTEXITCODE -ne 0) { throw 'Python syntax QA falhou. Nada alterado.' }
foreach ($js in @('static\js\lyrics.js','static\js\i18n.js')) {
    & node.exe --check (Join-Path $staging $js)
    if ($LASTEXITCODE -ne 0) { throw "JavaScript syntax QA falhou: $js. Nada alterado." }
}
$errors = $null
$tokens = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $staging 'scripts\Start-N3LX_Stem.ps1'), [ref]$tokens, [ref]$errors
) | Out-Null
if ($errors.Count -ne 0) { throw 'PowerShell syntax QA falhou. Nada alterado.' }

$modified = [System.Collections.Generic.List[string]]::new()
try {
    foreach ($f in $files) {
        $target = Join-Path $backend ($f.path.Replace('/', '\'))
        $stage = Join-Path $staging ($f.path.Replace('/', '\'))
        Copy-Item -LiteralPath $stage -Destination $target -Force
        $modified.Add($f.path)
        if ((GitBlob $target) -ne $f.new) { throw "Verificacao apos copia falhou: $($f.path)" }
    }
} catch {
    foreach ($rel in $modified) {
        Copy-Item -LiteralPath (Join-Path $original ($rel.Replace('/', '\'))) -Destination (Join-Path $backend ($rel.Replace('/', '\'))) -Force
    }
    throw
}
Write-Host "BACKUP=$backup"
Write-Host "FILES_MODIFIED=$($modified.Count)"
Write-Host "MUSIC_FILES_MODIFIED=False"
Write-Host "APP_RESTART_REQUIRED=True"
Write-Host 'FINAL_RESULT: RC9_KARAOKE_LARGE_V3_PATCH_APPLIED'
