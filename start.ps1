# Start backend + frontend dev servers in separate windows.
# First run on a fresh machine: installs the venv, node_modules and demo data.
# Automatically picks the next free port if the default backend port is taken.
$root = $PSScriptRoot

function Find-FreePort([int]$start) {
    $port = $start
    while ($port -lt $start + 50) {
        $inUse = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if (-not $inUse) { return $port }
        $port++
    }
    throw "No free port found in range $start-$($start + 49)"
}

# Locate a real Python 3.11+. On fresh Windows machines `python` is often the
# Microsoft Store stub, which exits with an error instead of running.
function Find-Python {
    foreach ($candidate in @(
        @{ exe = 'py';     args = @('-3') },
        @{ exe = 'python'; args = @() },
        @{ exe = 'python3'; args = @() }
    )) {
        $cmd = Get-Command $candidate.exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if ($cmd.Source -like '*WindowsApps*') { continue }   # Store stub
        $ver = & $candidate.exe @($candidate.args) --version 2>$null
        if ($ver -match 'Python 3\.(\d+)' -and [int]$Matches[1] -ge 11) {
            return $candidate
        }
    }
    throw "Python 3.11+ not found. Install it from python.org ('Install for me only' needs no admin) or: winget install Python.Python.3.11"
}

if (-not (Test-Path "$root\backend\.venv")) {
    $py = Find-Python
    Write-Host "Creating backend venv + installing dependencies..."
    & $py.exe @($py.args) -m venv "$root\backend\.venv"
    # requirements.lock pins the exact versions this repo was built against,
    # so every machine gets an identical, known-good environment.
    $req = if (Test-Path "$root\backend\requirements.lock") { "$root\backend\requirements.lock" }
           else { "$root\backend\requirements.txt" }
    & "$root\backend\.venv\Scripts\python.exe" -m pip install -r $req
    if ($LASTEXITCODE -ne 0) { throw "pip install failed - see output above (proxy/TLS issues: DEPLOYMENT.md section 2)" }
}
if (-not (Test-Path "$root\frontend\node_modules")) {
    Write-Host "Installing frontend dependencies..."
    # npm ci installs exactly what package-lock.json specifies.
    Push-Location "$root\frontend"; npm ci; if ($LASTEXITCODE -ne 0) { npm install }; Pop-Location
}
if (-not (Test-Path "$root\data\app.sqlite")) {
    Write-Host "No data yet - generating demo portfolios (~10s)..."
    Push-Location "$root\backend"
    & ".\.venv\Scripts\python.exe" -m app.sample_data
    Pop-Location
}

$backendPort = Find-FreePort 8001
if ($backendPort -ne 8001) {
    Write-Host "Port 8001 is occupied - using $backendPort for the backend instead."
}

Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port $backendPort"
# BACKEND_PORT tells the Vite proxy where to reach the API (see vite.config.ts).
# Vite itself auto-increments 5173 -> 5174... if its port is taken.
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$root\frontend'; `$env:BACKEND_PORT='$backendPort'; npm run dev"

Write-Host "Backend  -> http://localhost:$backendPort/docs"
Write-Host "Frontend -> http://localhost:5173 (or next free port - see the vite window)"
