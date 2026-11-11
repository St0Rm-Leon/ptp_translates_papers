@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install\install-hy.ps1" %*
exit /b %ERRORLEVEL%
