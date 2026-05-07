#!/usr/bin/env bash
#
# Description:
#   Build dashboard data from available outputs and serve the static dashboard
#   locally with Python's built-in HTTP server.
#
# Input:
#   Environment variables PORT, PYTHON_BIN, RESULTS_DIR, and SIMULATION_DIR.
#
# Output:
#   Writes dashboard/data/dashboard-data.js and starts a local static file
#   server for dashboard/production/index.html.

set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8010}"
PYTHON_BIN="${PYTHON_BIN:-}"
DASHBOARD_DIR="dashboard"
RESULTS_DIR="${RESULTS_DIR:-results/test}"
SIMULATION_DIR="${SIMULATION_DIR:-results/simulation}"

if [[ ! -d "${DASHBOARD_DIR}" ]]; then
  echo "Missing ${DASHBOARD_DIR}. Restore the dashboard static files before serving." >&2
  exit 1
fi

PYTHON_CMD=()

# Description: Check whether a Python command can execute.
# Input: Command and arguments passed to the function.
# Output: Returns success when the command prints its Python version; otherwise returns failure.
can_run_python() {
  "$@" -V >/dev/null 2>&1
}

if [[ -n "${PYTHON_BIN}" ]]; then
  if can_run_python "${PYTHON_BIN}"; then
    PYTHON_CMD=("${PYTHON_BIN}")
  else
    echo "Ignoring PYTHON_BIN=${PYTHON_BIN}; it could not be executed." >&2
  fi
fi

if [[ "${#PYTHON_CMD[@]}" -eq 0 ]] && command -v python >/dev/null 2>&1 && can_run_python python; then
  PYTHON_CMD=(python)
fi

if [[ "${#PYTHON_CMD[@]}" -eq 0 ]] && command -v py >/dev/null 2>&1 && can_run_python py -3; then
  PYTHON_CMD=(py -3)
fi

if [[ "${#PYTHON_CMD[@]}" -eq 0 ]]; then
  echo "Python was not found. Activate your environment or set PYTHON_BIN to a working Python executable." >&2
  exit 1
fi

echo "Building dashboard data from:"
echo "  ${RESULTS_DIR}"
echo "Simulation data from:"
echo "  ${SIMULATION_DIR}"
"${PYTHON_CMD[@]}" models/build_dashboard_data.py \
  --results-dir "${RESULTS_DIR}" \
  --simulation-dir "${SIMULATION_DIR}" \
  --output "${DASHBOARD_DIR}/data/dashboard-data.js"
echo

echo "Serving Syn Sport dashboard at:"
echo "  http://127.0.0.1:${PORT}/dashboard/production/index.html"
echo "  dashboard/production/index.html"
echo
echo "Press Ctrl+C to stop."

"${PYTHON_CMD[@]}" -m http.server "${PORT}"
