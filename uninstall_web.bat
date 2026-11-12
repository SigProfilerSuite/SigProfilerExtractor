@echo off
rem Double-click to remove the SigProfilerExtractor Workbench's Python environment and run
rem records from this PC. Your results and this folder are kept. It asks before removing anything.
rem -ExecutionPolicy Bypass applies to this one script only.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall_web.ps1" %*
set "RC=%ERRORLEVEL%"
echo.
if /I not "%~1"=="--yes" pause
exit /b %RC%
