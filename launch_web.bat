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

REM Any Python 3 can stop a Workbench or show the help.
:fast_help
call :find_python
if errorlevel 1 call :any_python
if not defined PYTHON_BIN goto :no_python
%PYTHON_BIN% "%LAUNCHER%" --help
exit /b %ERRORLEVEL%

:fast_stop
call :find_python
if errorlevel 1 call :any_python
if not defined PYTHON_BIN goto :no_python
%PYTHON_BIN% "%LAUNCHER%" --stop
exit /b %ERRORLEVEL%

REM Python 3.10 or newer. On 3.9 pip still installs reportlab 5.1 (the PDF
REM library SigProfilerAssignment uses), which then refuses to import: the
REM Workbench would open, and every run would fail with an ImportError.
REM The py launcher's default first, then python, then each version by name,
REM so a newer Python is found even when an older one is the default.
:find_python
set "PYTHON_BIN="
for %%P in ("py -3" "python" "py -3.14" "py -3.13" "py -3.12" "py -3.11" "py -3.10") do (
    if not defined PYTHON_BIN (
        %%~P -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
        if not errorlevel 1 set "PYTHON_BIN=%%~P"
    )
)
if defined PYTHON_BIN exit /b 0
exit /b 1

:any_python
set "PYTHON_BIN="
where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_BIN=py -3"
    exit /b 0
)
where python >nul 2>nul
if not errorlevel 1 set "PYTHON_BIN=python"
exit /b 0

REM No new enough Python: say so in words someone who never uses a terminal
REM can act on, and keep a double-clicked window open so it can be read.
:no_python
set "OLD_VERSION="
for /f "usebackq tokens=1,2" %%A in (`py -3 -c "import sys; print('PYVER', sys.version.split()[0])" 2^>nul`) do if "%%A"=="PYVER" set "OLD_VERSION=%%B"
if not defined OLD_VERSION for /f "usebackq tokens=1,2" %%A in (`python -c "import sys; print('PYVER', sys.version.split()[0])" 2^>nul`) do if "%%A"=="PYVER" set "OLD_VERSION=%%B"
echo. 1>&2
echo The SigProfilerExtractor Workbench needs Python 3.10 or newer. 1>&2
if defined OLD_VERSION (
    echo The Python on this computer is version %OLD_VERSION%, which is too old. 1>&2
) else (
    echo No Python was found on this computer. 1>&2
)
echo. 1>&2
echo Install the latest Python from https://www.python.org/downloads/ 1>&2
echo and tick "Add python.exe to PATH" in the installer, then open the Workbench again. 1>&2
echo. 1>&2
echo "%CMDCMDLINE%" | find /i "%~nx0" >nul && pause
exit /b 1

:main
call :find_python
if errorlevel 1 goto :no_python

set "VENV_DIR=%SCRIPT_DIR%.venv-dashboard"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
REM An environment made with an older Python (before the launcher asked for
REM 3.10) installs but cannot run an extraction, and one whose Python has been
REM removed cannot run at all: stop any Workbench running from it, then make
REM it again.
if exist "%VENV_DIR%" (
    "%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo The Workbench's environment was made with an older Python; setting it up again.
        %PYTHON_BIN% "%LAUNCHER%" --stop >nul 2>nul
        rmdir /s /q "%VENV_DIR%"
    )
)
if not exist "%VENV_DIR%" (
    %PYTHON_BIN% -m venv "%VENV_DIR%"
)

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
