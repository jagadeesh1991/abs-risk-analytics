# Start backend + frontend dev servers in separate windows.
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

if (-not (Test-Path "$root\backend\.venv")) {
    Write-Host "Creating backend venv + installing dependencies..."
    python -m venv "$root\backend\.venv"
    & "$root\backend\.venv\Scripts\python.exe" -m pip install -r "$root\backend\requirements.txt"
}
if (-not (Test-Path "$root\frontend\node_modules")) {
    Write-Host "Installing frontend dependencies..."
    Push-Location "$root\frontend"; npm install; Pop-Location
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
