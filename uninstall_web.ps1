# Remove what the SigProfilerExtractor Workbench installed on this Windows computer:
#   - its private Python environment, .venv-dashboard, next to this script (with any
#     reference genome installed through the Workbench, which lives inside it)
#   - its run records, in %LOCALAPPDATA%\SigProfilerExtractor
# Your results (wherever runs wrote them) and this SigProfilerExtractor folder are kept;
# delete them yourself if you no longer need them. Run it by double-clicking
# uninstall_web.bat, or: powershell -File uninstall_web.ps1 [--yes]

$ErrorActionPreference = 'Continue'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Here '.venv-dashboard'
$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME 'AppData\Local' }
$State = Join-Path $LocalAppData 'SigProfilerExtractor'
$Yes = ($args -contains '--yes') -or ($args -contains '-y')

function Test-InUse {
    # The Workbench, or one of its runs, still running?
    $pidfile = Join-Path $State 'dashboard.pid'
    if (Test-Path $pidfile) {
        $first = ((Get-Content $pidfile -Raw) -split ':')[0]
        $id = 0
        if ([int]::TryParse($first, [ref]$id) -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) { return $true }
    }
    $procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        if ($p.CommandLine -and $p.CommandLine.Contains('SigProfilerExtractor.web') -and
            (($p.ExecutablePath -and $p.ExecutablePath.StartsWith($Venv, 'OrdinalIgnoreCase')) -or
             $p.CommandLine.Contains($Venv))) { return $true }
    }
    return $false
}

Write-Host ""
Write-Host "  SigProfilerExtractor Workbench uninstaller"
Write-Host "  ------------------------------------------"

if (Test-InUse) {
    Write-Host "  The Workbench is still running. Click Quit in it (or run launch_web.bat --stop),"
    Write-Host "  then run this again."
    exit 1
}

$HasVenv = Test-Path (Join-Path $Venv 'pyvenv.cfg')
$Jobs = Join-Path $State 'jobs'
$HasState = (Test-Path $Jobs) -or (Test-Path (Join-Path $State 'dashboard.pid')) -or (Test-Path (Join-Path $State 'dashboard.lock'))
$Runs = if (Test-Path $Jobs) { @(Get-ChildItem -LiteralPath $Jobs -Directory -ErrorAction SilentlyContinue).Count } else { 0 }

if (-not $HasVenv -and -not $HasState) {
    Write-Host "  Nothing to remove: the Workbench's Python environment and run records are not here."
    exit 0
}

Write-Host "  This removes:"
if ($HasVenv) {
    $bytes = (Get-ChildItem -LiteralPath $Venv -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    $size = if ($bytes) { '{0:N1} GB' -f ($bytes / 1GB) } else { '?' }
    Write-Host "    - the Python environment $Venv ($size)"
    $tsb = Join-Path $Venv 'Lib\site-packages\SigProfilerMatrixGenerator\references\chromosomes\tsb'
    if (Test-Path $tsb) {
        $genomes = @(Get-ChildItem -LiteralPath $tsb -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }) -join ' '
        if ($genomes) { Write-Host "      including the reference genomes installed in it: $genomes" }
    }
}
if ($HasState) { Write-Host "    - the records of $Runs run(s) in $State (settings and logs, not results)" }
Write-Host ""
Write-Host "  It keeps your results (each run's output folder, such as $HOME\SigProfilerExtractor_results)"
Write-Host "  and this folder ($Here)."
Write-Host ""

if (-not $Yes) {
    $ans = Read-Host "  Remove them? Type y and press Enter"
    if ($ans -notmatch '^(y|yes)$') {
        Write-Host "  Nothing was removed."
        exit 0
    }
    Write-Host ""
}

$status = 0
if ($HasVenv) {
    Remove-Item -LiteralPath $Venv -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $Venv) {
        Write-Host "  Could not remove $Venv; delete that folder yourself (close anything using it first)."
        $status = 1
    } else {
        Write-Host "  Removed $Venv."
    }
}
if ($HasState) {
    # Only the Workbench's own files; the folder goes only if that empties it.
    Remove-Item -LiteralPath $Jobs -Recurse -Force -ErrorAction SilentlyContinue
    foreach ($f in @('dashboard.pid', 'dashboard.lock')) {
        Remove-Item -LiteralPath (Join-Path $State $f) -Force -ErrorAction SilentlyContinue
    }
    if ((Test-Path $State) -and -not (Get-ChildItem -LiteralPath $State -Force)) { Remove-Item -LiteralPath $State -Force }
    if (Test-Path $Jobs) {
        Write-Host "  Could not remove the run records in $State; delete them yourself."
        $status = 1
    } else {
        Write-Host "  Removed the run records."
    }
}

Write-Host ""
Write-Host "  Done. To start again later, double-click launch_web.bat: it sets everything up anew."
Write-Host "  To remove the rest, delete this folder and, if you no longer need them, your results."
exit $status
