@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install\install-all.ps1" %*
exit /b %ERRORLEVEL%
