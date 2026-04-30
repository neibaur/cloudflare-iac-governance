$ErrorActionPreference = "Stop"

$venvPath = Join-Path $PSScriptRoot ".venv"

function Test-PythonCandidate {
    param([string]$Path)

    if (-not $Path -or -not (Test-Path $Path)) {
        return $false
    }

    try {
        & $Path --version *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

$pythonCandidates = @()
$pythonCandidates += (Get-Command python -ErrorAction SilentlyContinue).Source
$pythonCandidates += (Get-Command py -ErrorAction SilentlyContinue).Source
$pythonCandidates += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Recurse -Filter python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
$pythonCandidates += Get-ChildItem "C:\Python*" -Recurse -Filter python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName

$pythonPath = $pythonCandidates |
    Where-Object { Test-PythonCandidate $_ } |
    Select-Object -First 1

if (-not $pythonPath) {
    throw "No working Python interpreter was found. Install Python 3, then rerun this script."
}

if (-not (Test-Path $venvPath)) {
    & $pythonPath -m venv $venvPath
}

$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
. $activateScript

python -m pip install --upgrade pip
python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")

Write-Host "Environment ready. The virtual environment is active for this PowerShell session."
