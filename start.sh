#!/usr/bin/env bash
# Start backend + frontend dev servers (Linux/macOS equivalent of start.ps1).
# First run on a fresh machine: installs the venv, node_modules and demo data.
# Automatically picks the next free port if the default backend port is taken.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

find_python() {
    for py in python3.12 python3.11 python3 python; do
        if command -v "$py" >/dev/null 2>&1; then
            if "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
                echo "$py"; return
            fi
        fi
    done
    echo "Python 3.11+ not found - install it first (e.g. apt install python3.11 python3.11-venv)" >&2
    exit 1
}

port_free() { ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

find_free_port() {
    local port=$1
    for _ in $(seq 50); do
        if port_free "$port"; then echo "$port"; return; fi
        port=$((port + 1))
    done
    echo "No free port found starting at $1" >&2; exit 1
}

if [ ! -d "$root/backend/.venv" ]; then
    py="$(find_python)"
    echo "Creating backend venv + installing dependencies..."
    "$py" -m venv "$root/backend/.venv"
    # requirements.lock pins the exact versions this repo was built against.
    req="$root/backend/requirements.txt"
    [ -f "$root/backend/requirements.lock" ] && req="$root/backend/requirements.lock"
    "$root/backend/.venv/bin/python" -m pip install -r "$req"
fi
if [ ! -d "$root/frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    (cd "$root/frontend" && (npm ci || npm install))
fi
if [ ! -f "$root/data/app.sqlite" ]; then
    echo "No data yet - generating demo portfolios (~10s)..."
    (cd "$root/backend" && ./.venv/bin/python -m app.sample_data)
fi

backend_port="$(find_free_port 8001)"
if [ "$backend_port" != 8001 ]; then
    echo "Port 8001 is occupied - using $backend_port for the backend instead."
fi

cleanup() { kill 0 2>/dev/null; }
trap cleanup EXIT INT TERM

(cd "$root/backend" && ./.venv/bin/python -m uvicorn app.main:app --port "$backend_port") &
# BACKEND_PORT tells the Vite proxy where to reach the API (see vite.config.ts).
(cd "$root/frontend" && BACKEND_PORT="$backend_port" npm run dev) &

echo "Backend  -> http://localhost:$backend_port/docs"
echo "Frontend -> http://localhost:5173 (or next free port - see vite output)"
wait
