#!/usr/bin/env bash
#
# Description:
#   Run a quick benchmark for one model or a small comma-separated model list.
#   This script is intended for fast checks before running the full simulation.
#
# Input:
#   Environment variables such as MODEL, MODELS, SAMPLE_ROWS,
#   SESSIONS_PER_PERSON, N_RUNS, EPOCHS, TARGET, TASK, and OUTPUT_DIR.
#
# Output:
#   Writes test metrics, synthetic samples, logs, and dashboard data under
#   results/test by default.

set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python}"
OUTPUT_DIR="${OUTPUT_DIR:-results/test}"
CLEAN_OUTPUT="${CLEAN_OUTPUT:-1}"
MODEL="${MODEL:-sdv_gaussian}"
MODELS="${MODELS:-${MODEL}}"
SAMPLE_ROWS="${SAMPLE_ROWS:-0}"
SESSIONS_PER_PERSON="${SESSIONS_PER_PERSON:-3}"
N_RUNS="${N_RUNS:-1}"
EPOCHS="${EPOCHS:-1}"
BATCH_SIZE="${BATCH_SIZE:-128}"
TABSYN_STEPS="${TABSYN_STEPS:-1}"
TARGET="${TARGET:-Training_Outcome}"
TASK="${TASK:-classification}"
RUN_STARTED="$(date +"%Y%m%d_%H%M%S")"
LOG_FILE="${LOG_FILE:-logs/run_${RUN_STARTED}.log}"

mkdir -p "$(dirname "${LOG_FILE}")"

{
  echo "Run started: $(date +"%Y-%m-%d %H:%M:%S")"
  echo "Python: ${PYTHON_BIN}"
  echo "Models: ${MODELS}"
  echo "Sample rows: ${SAMPLE_ROWS}"
  echo "Output folder: ${OUTPUT_DIR}"
  echo "Dashboard: dashboard/production/index.html"
  echo "Log file: ${LOG_FILE}"
  echo

  if [[ "${CLEAN_OUTPUT}" == "1" ]]; then
    case "${OUTPUT_DIR}" in
      results/*)
        echo "Cleaning output folder: ${OUTPUT_DIR}"
        rm -rf "${OUTPUT_DIR}"
        ;;
      *)
        echo "Refusing to clean OUTPUT_DIR outside results/: ${OUTPUT_DIR}" >&2
        echo "Set CLEAN_OUTPUT=0 to keep the folder, or use a results/... path." >&2
        exit 1
        ;;
    esac
  fi

  echo
  echo "Running benchmark..."
  "${PYTHON_BIN}" models/sport_eval_benchmark.py \
    --sample-rows "${SAMPLE_ROWS}" \
    --sessions-per-person "${SESSIONS_PER_PERSON}" \
    --n-runs "${N_RUNS}" \
    --models "${MODELS}" \
    --epochs "${EPOCHS}" \
    --batch-size "${BATCH_SIZE}" \
    --tabsyn-steps "${TABSYN_STEPS}" \
    --target "${TARGET}" \
    --task "${TASK}" \
    --output-dir "${OUTPUT_DIR}" \
    --log-path "${LOG_FILE}"

  echo
  echo "Refreshing dashboard data..."
  "${PYTHON_BIN}" models/build_dashboard_data.py \
    --results-dir "${OUTPUT_DIR}" \
    --output dashboard/data/dashboard-data.js

  echo
  echo "Full test complete."
  echo "Dashboard: dashboard/production/index.html"
  echo "Results folder: ${OUTPUT_DIR}"
  echo "Log file: ${LOG_FILE}"
  echo "Run finished: $(date +"%Y-%m-%d %H:%M:%S")"
} 2>&1 | tee "${LOG_FILE}"
