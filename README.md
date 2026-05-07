# Syn Sport Synthetic Data Pipeline

This project generates and evaluates synthetic tabular sport sessions from:

```text
data/tabular.csv
```

The pipeline preserves participant-level fields such as athlete identity, age,
gender, sport type, and training experience, then generates repeated synthetic
session records for each participant. Results are saved as CSV metrics,
synthetic sessions, plots, logs, and a local dashboard.

## Dataset

The expected dataset is a tabular CSV located at:

```text
data/tabular.csv
```

Default columns used by the pipeline:

- `Athlete_ID`: participant identifier.
- `Training_Outcome`: default target variable.
- `Age`, `Gender`, `Sport_Type`, `Training_Experience_Years`: default static participant fields.
- Remaining numeric and categorical columns are treated as session-level variables.

The default task is classification. You can change the target and task with:

```bash
TARGET=Training_Outcome TASK=classification bash run_test.sh
```

## Models

The implemented models are:

- `ctgan`: GAN-based tabular generator for mixed numerical and categorical data.
- `dpctgan`: differentially private CTGAN for privacy-aware generation.
- `pategan`: privacy-preserving GAN using teacher-student aggregation.
- `tabsyn`: diffusion-based tabular generator using a latent denoising process.
- `sdv_gaussian`: Gaussian Copula statistical generator; fast baseline model.
- `sdv_tvae`: variational autoencoder for tabular data.
- `sdv_par`: sequential model for participant/session-style records.
- `realtabformer`: transformer-based tabular generator.
- `bootstrap`: lightweight resampling baseline for quick checks.

## Install

Use the Python installation available in the working environment, then install
the dependencies from the files in this folder:

```bash
cd synSPORT
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If your Python executable is not named `python`, set it explicitly:

```bash
PYTHON_BIN=/path/to/python bash run_test.sh
```

## Quick Local Test

Use this first to confirm the pipeline works:

```bash
MODEL=sdv_gaussian \
SAMPLE_ROWS=120 \
SESSIONS_PER_PERSON=2 \
N_RUNS=1 \
EPOCHS=2 \
bash run_test.sh
```

Use `MODELS=model_a,model_b` only when a quick test should include more than
one model.

Outputs are written to:

```text
results/test/
logs/
dashboard/data/dashboard-data.js
```

## Simulation Run

Use `run_simulation.sh` when you want to compare metrics over increasing model
settings such as epoch steps. The script runs the simulation, merges the
step/model outputs, and refreshes the dashboard data in one command.

Small local parallel example:

```bash
MODELS=sdv_gaussian,sdv_tvae \
SAMPLE_ROWS=120 \
SESSIONS_PER_PERSON=2 \
N_RUNS=2 \
STEPS=2 \
START_EPOCHS=2 \
EPOCH_STEP=2 \
MAX_WORKERS=2 \
WORKER_THREADS=1 \
OUTPUT_DIR=results/simulation_parallel_test \
LOG_FILE=logs/simulation_parallel_test.log \
bash run_simulation.sh
```

Larger production-style example:

```bash
MODELS=ctgan,dpctgan,pategan,tabsyn,sdv_gaussian,sdv_tvae,sdv_par,realtabformer \
SAMPLE_ROWS=0 \
SESSIONS_PER_PERSON=300 \
N_RUNS=5 \
STEPS=3 \
START_EPOCHS=50 \
EPOCH_STEP=50 \
MAX_WORKERS=2 \
WORKER_THREADS=1 \
bash run_simulation.sh
```

Increase `MAX_WORKERS` only if the machine has enough CPU and memory. Set
`MERGE_AFTER_RUN=0` only when you intentionally want to skip the automatic merge.

Simulation modes:

- `SIMULATION_MODE=full`: runs all configured models and steps. This is the default.
- `SIMULATION_MODE=step`: runs one model for one simulation step.
- `SIMULATION_MODE=merge`: merges completed step/model outputs and refreshes the dashboard data.

## Dashboard

Start the dashboard with:

```bash
bash run_dashboard.sh
```

Open:

```text
dashboard/production/index.html
```

To view a specific simulation output folder:

```bash
SIMULATION_DIR=results/simulation_parallel_test bash run_dashboard.sh
```

## Batch Workflow

For larger runs, each model and epoch step can be executed as a separate job.
Each job writes to a model-specific folder under `results/simulation/`.

Example single model-step job:

```bash
SIMULATION_MODE=step \
MODEL=ctgan \
STEP=1 \
EPOCHS=50 \
SAMPLE_ROWS=0 \
SESSIONS_PER_PERSON=300 \
N_RUNS=5 \
bash run_simulation.sh
```

The included `pipeline.pbs` file runs the same single model-step workflow with
the variables supplied by the job environment.

After all separate model-step jobs finish, merge the outputs:

```bash
SIMULATION_MODE=merge bash run_simulation.sh
```

Then inspect the dashboard:

```bash
bash run_dashboard.sh
```

## Files To Keep

The pipeline needs:

- `data/`
- `models/`
- `dashboard/`
- `requirements.txt`
- `run_test.sh`
- `run_simulation.sh`
- `run_dashboard.sh`
- `pipeline.pbs`
- `README.md`

The scripts create output folders such as `results/` and `logs/` when they run.

## References

```bibtex
@article{challagundla2025synthetic,
  title={Synthetic Tabular Data Generation: A Comparative Survey for Modern Techniques},
  author={Challagundla, Raju and Dorodchi, Mohsen and Wang, Pu and Lee, Minwoo},
  journal={arXiv preprint arXiv:2507.11590},
  year={2025}
}
```
