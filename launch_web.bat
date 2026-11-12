@echo off
REM Reusable Windows launcher for the SigProfilerExtractor Workbench.
REM Creates (or reuses) an isolated .venv-dashboard virtualenv next to this
REM script, installs the package into it only when its dependency fingerprint
REM changed, then starts the local Workbench server.
REM
REM Usage: launch_web.bat [--no-launch] [--reinstall] [--stop] [--volume PATH] [--help]
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
set "LAUNCHER=%SCRIPT_DIR%SigProfilerExtractor\web\launcher.py"

REM --help and --stop never need a dependency install, so run them straight
REM off the system interpreter without creating a venv first.
for %%A in (%*) do (
    if /I "%%~A"=="--help" goto :fast_help
    if /I "%%~A"=="-h" goto :fast_help
    if /I "%%~A"=="--stop" goto :fast_stop
)
goto :main

:fast_help
call :find_python
%PYTHON_BIN% "%LAUNCHER%" --help
exit /b %ERRORLEVEL%

:fast_stop
call :find_python
%PYTHON_BIN% "%LAUNCHER%" --stop
exit /b %ERRORLEVEL%

:find_python
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_BIN=py -3"
    exit /b 0
)
where python >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_BIN=python"
    exit /b 0
)
echo Python 3 was not found on PATH. Install Python 3.9+ and try again. 1>&2
exit /b 1

:main
call :find_python
if errorlevel 1 exit /b 1

set "VENV_DIR=%SCRIPT_DIR%.venv-dashboard"
if not exist "%VENV_DIR%" (
    %PYTHON_BIN% -m venv "%VENV_DIR%"
)
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

set "REINSTALL_FLAG="
for %%A in (%*) do (
    if /I "%%~A"=="--reinstall" set "REINSTALL_FLAG=--reinstall"
)

REM Run the fingerprint/install check by executing the file directly: the
REM package is not necessarily installed into a brand-new venv yet, so this
REM must work without `import SigProfilerExtractor` succeeding.
"%VENV_PY%" "%LAUNCHER%" --ensure-deps-only %REINSTALL_FLAG%
if errorlevel 1 exit /b 1

REM The package is now installed in the venv; run the real dashboard as a
REM proper module so its relative imports (server.py, jobs.py, ...) resolve.
"%VENV_PY%" -m SigProfilerExtractor.web.launcher %*
exit /b %ERRORLEVEL%
