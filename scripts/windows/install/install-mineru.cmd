@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install\install-mineru.ps1" %*
exit /b %ERRORLEVEL%
