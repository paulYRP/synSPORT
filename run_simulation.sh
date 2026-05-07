#!/usr/bin/env bash
#
# Description:
#   Run synSPORT simulations in one of three modes: full, step, or merge.
#   Full mode runs configured models over epoch steps, step mode runs one
#   model-step job, and merge mode combines completed model-step outputs.
#
# Input:
#   Environment variables such as SIMULATION_MODE, MODELS, MODEL, STEP, EPOCHS,
#   STEPS, START_EPOCHS, EPOCH_STEP, MAX_WORKERS, WORKER_THREADS, TARGET, TASK,
#   and OUTPUT_DIR.
#
# Output:
#   Writes simulation result folders, merged timeline CSV files, visualization
#   assets, logs, and refreshed dashboard data.

set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python}"
SIMULATION_MODE="${SIMULATION_MODE:-full}"
MODELS="${MODELS:-ctgan,dpctgan,pategan,tabsyn,sdv_gaussian,sdv_tvae,sdv_par,realtabformer}"
MODEL="${MODEL:-}"
STEP="${STEP:-}"
EPOCHS="${EPOCHS:-}"
SAMPLE_ROWS="${SAMPLE_ROWS:-0}"
SESSIONS_PER_PERSON="${SESSIONS_PER_PERSON:-300}"
N_RUNS="${N_RUNS:-5}"
STEPS="${STEPS:-3}"
START_EPOCHS="${START_EPOCHS:-50}"
EPOCH_STEP="${EPOCH_STEP:-50}"
BATCH_SIZE="${BATCH_SIZE:-64}"
TABSYN_STEPS="${TABSYN_STEPS:-50}"
EPSILON="${EPSILON:-1.0}"
DELTA="${DELTA:-1e-5}"
DP_EPSILON="${DP_EPSILON:-0.5}"
DP_DELTA="${DP_DELTA:-1e-5}"
PATE_EPSILON="${PATE_EPSILON:-1.0}"
PATE_DELTA="${PATE_DELTA:-1e-5}"
LATENT_DIM="${LATENT_DIM:-64}"
TEACHER_ITERS="${TEACHER_ITERS:-10}"
STUDENT_ITERS="${STUDENT_ITERS:-5}"
MAX_WORKERS="${MAX_WORKERS:-1}"
WORKER_THREADS="${WORKER_THREADS:-1}"
OUTPUT_DIR="${OUTPUT_DIR:-results/simulation}"
DASHBOARD_RESULTS_DIR="${DASHBOARD_RESULTS_DIR:-results/test}"
DASHBOARD_SIMULATION_DIR="${OUTPUT_DIR}"
CLEAN_OUTPUT="${CLEAN_OUTPUT:-1}"
MERGE_AFTER_RUN="${MERGE_AFTER_RUN:-1}"
TARGET="${TARGET:-Training_Outcome}"
TASK="${TASK:-classification}"
RUN_STARTED="$(date +"%Y%m%d_%H%M%S")"

case "${SIMULATION_MODE}" in
  full)
    LOG_FILE="${LOG_FILE:-logs/simulation_${RUN_STARTED}.log}"
    ;;
  step)
    if [[ -z "${MODEL}" ]]; then
      echo "Set MODEL to one model name, for example MODEL=ctgan" >&2
      exit 1
    fi
    if [[ -z "${STEP}" ]]; then
      echo "Set STEP to the simulation step number, for example STEP=1" >&2
      exit 1
    fi
    if [[ -z "${EPOCHS}" ]]; then
      echo "Set EPOCHS for this job, for example EPOCHS=50" >&2
      exit 1
    fi
    STEP_PADDED="$(printf "%03d" "${STEP}")"
    MODEL_OUTPUT_DIR="${OUTPUT_DIR}/step_${STEP_PADDED}/${MODEL}"
    LOG_FILE="${LOG_FILE:-logs/simulation_step_${STEP_PADDED}_${MODEL}_${RUN_STARTED}.log}"
    ;;
  merge)
    LOG_FILE="${LOG_FILE:-logs/simulation_merge_${RUN_STARTED}.log}"
    ;;
  *)
    echo "SIMULATION_MODE must be one of: full, step, merge" >&2
    exit 1
    ;;
esac

mkdir -p "$(dirname "${LOG_FILE}")"

# Description: Remove the full simulation output folder when cleaning is enabled.
# Input: Uses CLEAN_OUTPUT and OUTPUT_DIR from the script environment.
# Output: Deletes OUTPUT_DIR when it is a safe results/ path; otherwise exits on unsafe paths.
clean_output_dir() {
  if [[ "${CLEAN_OUTPUT}" != "1" ]]; then
    return
  fi

  case "${OUTPUT_DIR}" in
    results/*)
      echo "Cleaning output folder: ${OUTPUT_DIR}"
      rm -rf "${OUTPUT_DIR}"
      ;;
    *)
      echo "Refusing to clean OUTPUT_DIR outside results/: ${OUTPUT_DIR}" >&2
      exit 1
      ;;
  esac
}

# Description: Remove the output folder for one simulation model-step.
# Input: Uses CLEAN_OUTPUT and MODEL_OUTPUT_DIR from the script environment.
# Output: Deletes MODEL_OUTPUT_DIR when it is a safe results/.../step_... path; otherwise exits.
clean_model_step_dir() {
  if [[ "${CLEAN_OUTPUT}" != "1" ]]; then
    return
  fi

  case "${MODEL_OUTPUT_DIR}" in
    results/*/step_*/*)
      echo "Cleaning model-step folder: ${MODEL_OUTPUT_DIR}"
      rm -rf "${MODEL_OUTPUT_DIR}"
      ;;
    *)
      echo "Refusing to clean MODEL_OUTPUT_DIR outside results/*/step_*/*: ${MODEL_OUTPUT_DIR}" >&2
      exit 1
      ;;
  esac
}

# Description: Limit math library thread usage for a model worker.
# Input: Uses WORKER_THREADS from the script environment.
# Output: Exports thread-count environment variables for child Python processes.
export_worker_threads() {
  export OMP_NUM_THREADS="${WORKER_THREADS}"
  export MKL_NUM_THREADS="${WORKER_THREADS}"
  export OPENBLAS_NUM_THREADS="${WORKER_THREADS}"
  export NUMEXPR_NUM_THREADS="${WORKER_THREADS}"
}

# Description: Merge completed simulation step/model outputs into summary files.
# Input: Uses model, step, metric, privacy, and output configuration variables.
# Output: Writes merged simulation CSV files and visualization assets under OUTPUT_DIR.
run_merge() {
  echo "Simulation merge started: $(date +"%Y-%m-%d %H:%M:%S")"
  echo "Python: ${PYTHON_BIN}"
  echo "Output folder: ${OUTPUT_DIR}"
  echo "Steps: ${STEPS}"
  echo "Epoch schedule: ${START_EPOCHS}, +${EPOCH_STEP} per step"
  echo "Dashboard results folder: ${DASHBOARD_RESULTS_DIR}"
  echo

  "${PYTHON_BIN}" models/run_simulation.py \
    --merge-only \
    --models "${MODELS}" \
    --sample-rows "${SAMPLE_ROWS}" \
    --sessions-per-person "${SESSIONS_PER_PERSON}" \
    --n-runs "${N_RUNS}" \
    --steps "${STEPS}" \
    --start-epochs "${START_EPOCHS}" \
    --epoch-step "${EPOCH_STEP}" \
    --batch-size "${BATCH_SIZE}" \
    --tabsyn-steps "${TABSYN_STEPS}" \
    --epsilon "${EPSILON}" \
    --delta "${DELTA}" \
    --dp-epsilon "${DP_EPSILON}" \
    --dp-delta "${DP_DELTA}" \
    --pate-epsilon "${PATE_EPSILON}" \
    --pate-delta "${PATE_DELTA}" \
    --latent-dim "${LATENT_DIM}" \
    --teacher-iters "${TEACHER_ITERS}" \
    --student-iters "${STUDENT_ITERS}" \
    --output-dir "${OUTPUT_DIR}" \
    --dashboard-results-dir "${DASHBOARD_RESULTS_DIR}" \
    --target "${TARGET}" \
    --task "${TASK}"

  echo
  echo "Simulation merge finished: $(date +"%Y-%m-%d %H:%M:%S")"
}

# Description: Build the dashboard data file from test and simulation outputs.
# Input: Uses DASHBOARD_RESULTS_DIR, DASHBOARD_SIMULATION_DIR, and PYTHON_BIN.
# Output: Writes dashboard/data/dashboard-data.js.
refresh_dashboard_data() {
  echo
  echo "Refreshing dashboard data: $(date +"%Y-%m-%d %H:%M:%S")"
  "${PYTHON_BIN}" models/build_dashboard_data.py \
    --results-dir "${DASHBOARD_RESULTS_DIR}" \
    --simulation-dir "${DASHBOARD_SIMULATION_DIR}" \
    --output dashboard/data/dashboard-data.js
}

# Description: Run the complete local simulation across configured models and steps.
# Input: Uses MODELS, STEPS, epochs, privacy settings, output settings, and worker settings.
# Output: Writes per-step results, merged simulation outputs, logs, and dashboard data.
run_full_simulation() {
  echo "Simulation started: $(date +"%Y-%m-%d %H:%M:%S")"
  echo "Python: ${PYTHON_BIN}"
  echo "Models: ${MODELS}"
  echo "Sample rows: ${SAMPLE_ROWS}"
  echo "Steps: ${STEPS}"
  echo "Epoch schedule: ${START_EPOCHS}, +${EPOCH_STEP} per step"
  echo "Runs per model: ${N_RUNS}"
  echo "Sessions per person: ${SESSIONS_PER_PERSON}"
  echo "Parallel model workers: ${MAX_WORKERS}"
  echo "Threads per worker: ${WORKER_THREADS}"
  echo "Merge after run: ${MERGE_AFTER_RUN}"
  echo "Output folder: ${OUTPUT_DIR}"
  echo "Log file: ${LOG_FILE}"
  echo

  clean_output_dir
  echo

  "${PYTHON_BIN}" models/run_simulation.py \
    --models "${MODELS}" \
    --sample-rows "${SAMPLE_ROWS}" \
    --sessions-per-person "${SESSIONS_PER_PERSON}" \
    --n-runs "${N_RUNS}" \
    --steps "${STEPS}" \
    --start-epochs "${START_EPOCHS}" \
    --epoch-step "${EPOCH_STEP}" \
    --batch-size "${BATCH_SIZE}" \
    --tabsyn-steps "${TABSYN_STEPS}" \
    --epsilon "${EPSILON}" \
    --delta "${DELTA}" \
    --dp-epsilon "${DP_EPSILON}" \
    --dp-delta "${DP_DELTA}" \
    --pate-epsilon "${PATE_EPSILON}" \
    --pate-delta "${PATE_DELTA}" \
    --latent-dim "${LATENT_DIM}" \
    --teacher-iters "${TEACHER_ITERS}" \
    --student-iters "${STUDENT_ITERS}" \
    --max-workers "${MAX_WORKERS}" \
    --worker-threads "${WORKER_THREADS}" \
    --output-dir "${OUTPUT_DIR}" \
    --dashboard-results-dir "${DASHBOARD_RESULTS_DIR}" \
    --target "${TARGET}" \
    --task "${TASK}"

  echo
  if [[ "${MERGE_AFTER_RUN}" == "1" ]]; then
    run_merge
  fi

  echo
  echo "Simulation completed: $(date +"%Y-%m-%d %H:%M:%S")"
  echo "Final full log: ${LOG_FILE}"
  echo "Dashboard: dashboard/production/index.html"
}

# Description: Run one model for one simulation step.
# Input: Uses MODEL, STEP, EPOCHS, dataset settings, privacy settings, and output settings.
# Output: Writes one model-step result folder and one model-step log file.
run_model_step() {
  export_worker_threads
  clean_model_step_dir

  echo "Simulation model-step started: $(date +"%Y-%m-%d %H:%M:%S")"
  echo "Python: ${PYTHON_BIN}"
  echo "Model: ${MODEL}"
  echo "Step: ${STEP_PADDED}"
  echo "Epochs: ${EPOCHS}"
  echo "Sample rows: ${SAMPLE_ROWS}"
  echo "Runs: ${N_RUNS}"
  echo "Sessions per person: ${SESSIONS_PER_PERSON}"
  echo "Output folder: ${MODEL_OUTPUT_DIR}"
  echo "Log file: ${LOG_FILE}"
  echo

  "${PYTHON_BIN}" models/sport_eval_benchmark.py \
    --sample-rows "${SAMPLE_ROWS}" \
    --sessions-per-person "${SESSIONS_PER_PERSON}" \
    --n-runs "${N_RUNS}" \
    --models "${MODEL}" \
    --epochs "${EPOCHS}" \
    --batch-size "${BATCH_SIZE}" \
    --tabsyn-steps "${TABSYN_STEPS}" \
    --epsilon "${EPSILON}" \
    --delta "${DELTA}" \
    --dp-epsilon "${DP_EPSILON}" \
    --dp-delta "${DP_DELTA}" \
    --pate-epsilon "${PATE_EPSILON}" \
    --pate-delta "${PATE_DELTA}" \
    --latent-dim "${LATENT_DIM}" \
    --teacher-iters "${TEACHER_ITERS}" \
    --student-iters "${STUDENT_ITERS}" \
    --target "${TARGET}" \
    --task "${TASK}" \
    --output-dir "${MODEL_OUTPUT_DIR}" \
    --log-path "${LOG_FILE}"

  echo
  echo "Simulation model-step finished: $(date +"%Y-%m-%d %H:%M:%S")"
}

{
  case "${SIMULATION_MODE}" in
    full)
      run_full_simulation
      refresh_dashboard_data
      ;;
    step)
      run_model_step
      ;;
    merge)
      run_merge
      refresh_dashboard_data
      echo
      echo "Dashboard: dashboard/production/index.html"
      ;;
  esac
} 2>&1 | tee "${LOG_FILE}"
