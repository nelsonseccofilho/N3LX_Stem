$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$electron = Join-Path $repo 'desktop-app\node_modules\electron\dist\electron.exe'
if (-not (Test-Path -LiteralPath $electron)) { throw 'Instale o aplicativo primeiro com Setup-N3LX_Stem.cmd -DesktopOnly.' }
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'N3LX_Stem.lnk'
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $electron
$shortcut.Arguments = '"' + (Join-Path $repo 'desktop-app') + '"'
$shortcut.WorkingDirectory = $repo
$shortcut.Description = 'N3LX_Stem - aplicativo de separacao de audio'
$shortcut.IconLocation = (Join-Path $repo 'desktop\src-tauri\icons\icon.ico') + ',0'
$shortcut.Save()
Write-Output $shortcutPath
