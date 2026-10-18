@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Setup-N3LX_Stem.ps1" %*
if errorlevel 1 pause
