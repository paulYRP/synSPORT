"""
Run and merge synSPORT simulation experiments.

Description:
    Coordinates incremental synthetic-data simulations across models and epoch
    steps, collects per-model metrics, writes merged timeline summaries, and
    creates simulation plots and animated progress assets.

Input:
    Command-line arguments for models, sample size, session count, epoch
    schedule, privacy settings, parallel workers, and output folders.

Output:
    Per-step model folders, metrics_timeline.csv, simulation_summary.csv,
    simulation visual assets, logs, and refreshed dashboard data.

"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_SCRIPT = PROJECT_ROOT / "models" / "sport_eval_benchmark.py"
BUILD_DASHBOARD_SCRIPT = PROJECT_ROOT / "models" / "build_dashboard_data.py"
DEFAULT_SIMULATION_MODELS = "ctgan,dpctgan,pategan,tabsyn,sdv_gaussian,sdv_tvae,sdv_par,realtabformer"
SIMULATION_METRICS = ["Accuracy", "F1-score", "JSD", "Wasserstein", "MIA_Accuracy"]
TIMELINE_FIELDS = [
    "step",
    "scenario",
    "model",
    "epochs",
    "sample_rows",
    "sessions_per_person",
    "Accuracy",
    "F1-score",
    "PearsonCorrDiff",
    "UncertaintyCoeffDiff",
    "CorrelationRatioDiff",
    "Wasserstein",
    "JSD",
    "MIA_Accuracy",
]
SUMMARY_FIELDS = [
    "model",
    "first_step",
    "latest_step",
    "latest_epochs",
    "latest_accuracy",
    "latest_f1",
    "latest_jsd",
    "latest_wasserstein",
    "latest_mia_accuracy",
]


def read_csv(path: Path) -> List[Dict[str, str]]:
    """
    Description:
        Read data for `read_csv`.

    Input:
        path: Path.

    Output:
        List[Dict[str, str]].
    """
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: List[Dict[str, object]], fieldnames: Iterable[str]) -> None:
    """
    Description:
        Write outputs for `write_csv`.

    Input:
        path: Path; rows: List[Dict[str, object]]; fieldnames: Iterable[str].

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(rows)


def parse_models(models: str) -> List[str]:
    """
    Description:
        Parse input values for `parse_models`.

    Input:
        models: str.

    Output:
        List[str].
    """
    return [model.strip() for model in models.split(",") if model.strip()]


def get_model_rows(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """
    Description:
        Return values for `get_model_rows`.

    Input:
        rows: List[Dict[str, str]].

    Output:
        Dict[str, Dict[str, str]].
    """
    return {row.get("model", ""): row for row in rows if row.get("model")}


def metric_value(row: Dict[str, str], name: str) -> str:
    """
    Description:
        Return metric values for `metric_value`.

    Input:
        row: Dict[str, str]; name: str.

    Output:
        str.
    """
    value = row.get(name, "")
    return "" if value in {"", "None", "nan", "NaN"} else value


def to_float(value: object) -> float | None:
    """
    Description:
        Convert values for `to_float`.

    Input:
        value: object.

    Output:
        float | None.
    """
    try:
        if value in {"", None, "None", "nan", "NaN"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def step_metric_dirs(step_dir: Path) -> List[Path]:
    """
    Description:
        Run the helper for `step_metric_dirs`.

    Input:
        step_dir: Path.

    Output:
        List[Path].
    """
    dirs: List[Path] = []
    if (step_dir / "metrics").exists():
        dirs.append(step_dir)
    if step_dir.exists():
        dirs.extend(
            sorted(
                child
                for child in step_dir.iterdir()
                if child.is_dir() and (child / "metrics").exists()
            )
        )
    return dirs


def collect_metrics_from_dir(source_dir: Path, step: int, epochs: int, sample_rows: int, sessions_per_person: int) -> List[Dict[str, object]]:
    """
    Description:
        Collect data for `collect_metrics_from_dir`.

    Input:
        source_dir: Path; step: int; epochs: int; sample_rows: int; sessions_per_person: int.

    Output:
        List[Dict[str, object]].
    """
    metrics_dir = source_dir / "metrics"
    utility = get_model_rows(read_csv(metrics_dir / "ml_utility_with_pvalues.csv"))
    stat_sim = get_model_rows(read_csv(metrics_dir / "stat_sim_with_pvalues.csv"))
    feature = get_model_rows(read_csv(metrics_dir / "fd_metrics_with_pvalues.csv"))
    privacy = get_model_rows(read_csv(metrics_dir / "privacy_metrics_with_pvalues.csv"))

    models = sorted(set(utility) | set(stat_sim) | set(feature) | set(privacy))
    rows: List[Dict[str, object]] = []
    for model in models:
        utility_row = utility.get(model, {})
        stat_row = stat_sim.get(model, {})
        feature_row = feature.get(model, {})
        privacy_row = privacy.get(model, {})
        rows.append({
            "step": step,
            "scenario": f"small_increase_{step:03d}",
            "model": model,
            "epochs": epochs,
            "sample_rows": sample_rows,
            "sessions_per_person": sessions_per_person,
            "Accuracy": metric_value(utility_row, "Accuracy"),
            "F1-score": metric_value(utility_row, "F1-score"),
            "PearsonCorrDiff": metric_value(feature_row, "PearsonCorrDiff"),
            "UncertaintyCoeffDiff": metric_value(feature_row, "UncertaintyCoeffDiff"),
            "CorrelationRatioDiff": metric_value(feature_row, "CorrelationRatioDiff"),
            "Wasserstein": metric_value(stat_row, "Wasserstein"),
            "JSD": metric_value(stat_row, "JSD"),
            "MIA_Accuracy": metric_value(privacy_row, "MIA_Accuracy"),
        })
    return rows


def collect_step_metrics(step_dir: Path, step: int, epochs: int, sample_rows: int, sessions_per_person: int) -> List[Dict[str, object]]:
    """
    Description:
        Collect data for `collect_step_metrics`.

    Input:
        step_dir: Path; step: int; epochs: int; sample_rows: int; sessions_per_person: int.

    Output:
        List[Dict[str, object]].
    """
    rows: List[Dict[str, object]] = []
    for source_dir in step_metric_dirs(step_dir):
        rows.extend(collect_metrics_from_dir(source_dir, step, epochs, sample_rows, sessions_per_person))

    deduped: Dict[tuple[int, str], Dict[str, object]] = {}
    for row in rows:
        deduped[(int(row["step"]), str(row["model"]))] = row
    return [deduped[key] for key in sorted(deduped, key=lambda item: (item[0], item[1]))]


def summarize_timeline(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """
    Description:
        Summarize results for `summarize_timeline`.

    Input:
        rows: List[Dict[str, object]].

    Output:
        List[Dict[str, object]].
    """
    summary: List[Dict[str, object]] = []
    by_model: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        by_model.setdefault(str(row["model"]), []).append(row)

    for model, model_rows in sorted(by_model.items()):
        model_rows = sorted(model_rows, key=lambda row: int(row["step"]))
        first = model_rows[0]
        latest = model_rows[-1]
        summary.append({
            "model": model,
            "first_step": first["step"],
            "latest_step": latest["step"],
            "latest_epochs": latest["epochs"],
            "latest_accuracy": latest.get("Accuracy", ""),
            "latest_f1": latest.get("F1-score", ""),
            "latest_jsd": latest.get("JSD", ""),
            "latest_wasserstein": latest.get("Wasserstein", ""),
            "latest_mia_accuracy": latest.get("MIA_Accuracy", ""),
        })
    return summary


def metric_lookup(rows: List[Dict[str, object]]) -> Dict[tuple[int, str, str], float]:
    """
    Description:
        Return metric values for `metric_lookup`.

    Input:
        rows: List[Dict[str, object]].

    Output:
        Dict[tuple[int, str, str], float].
    """
    lookup: Dict[tuple[int, str, str], float] = {}
    for row in rows:
        step = int(row["step"])
        model = str(row["model"])
        for metric in SIMULATION_METRICS:
            value = to_float(row.get(metric))
            if value is not None:
                lookup[(step, model, metric)] = value
    return lookup


def style_axis(ax, title: str) -> None:
    """
    Description:
        Style plot axes for `style_axis`.

    Input:
        ax; title: str.

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    ax.set_title(title, color="#fff", fontsize=11, fontweight="bold")
    ax.set_facecolor("#111")
    ax.tick_params(colors="#fff", labelsize=8)
    ax.grid(True, color="#444", alpha=0.35, linewidth=0.6)
    for spine in ax.spines.values():
        spine.set_color("#555")


def plot_metric_lines(ax, rows: List[Dict[str, object]], metric: str, max_step: int | None = None) -> None:
    """
    Description:
        Plot trend data for `plot_metric_lines`.

    Input:
        ax; rows: List[Dict[str, object]]; metric: str; max_step: int | None.

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    models = sorted({str(row["model"]) for row in rows})
    steps = sorted({int(row["step"]) for row in rows if max_step is None or int(row["step"]) <= max_step})
    lookup = metric_lookup(rows)

    for model in models:
        values = [lookup.get((step, model, metric)) for step in steps]
        plotted_steps = [step for step, value in zip(steps, values) if value is not None]
        plotted_values = [value for value in values if value is not None]
        if plotted_values:
            ax.plot(plotted_steps, plotted_values, marker="o", linewidth=2, label=model)

    style_axis(ax, metric)
    ax.set_xlabel("Simulation step", color="#fff", fontsize=8)


def save_trend_plot(rows: List[Dict[str, object]], visuals_dir: Path) -> Path:
    """
    Description:
        Save outputs for `save_trend_plot`.

    Input:
        rows: List[Dict[str, object]]; visuals_dir: Path.

    Output:
        Path.
    """
    plot_path = visuals_dir / "simulation_metric_trends.png"
    fig, axes = plt.subplots(3, 2, figsize=(13, 9), facecolor="#151515")
    axes_flat = axes.flatten()

    for ax, metric in zip(axes_flat, SIMULATION_METRICS):
        plot_metric_lines(ax, rows, metric)

    axes_flat[-1].axis("off")
    handles, labels = axes_flat[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="lower center", ncol=min(len(labels), 4), facecolor="#151515", labelcolor="#fff")
    fig.suptitle("Synthetic Data Simulation Metric Trends", color="#fff", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=[0, 0.06, 1, 0.95])
    fig.savefig(plot_path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)
    return plot_path


def save_progress_gif(rows: List[Dict[str, object]], visuals_dir: Path) -> Path | None:
    """
    Description:
        Save outputs for `save_progress_gif`.

    Input:
        rows: List[Dict[str, object]]; visuals_dir: Path.

    Output:
        Path | None.
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    steps = sorted({int(row["step"]) for row in rows})
    if not steps:
        return None

    frame_paths: List[Path] = []
    for step in steps:
        frame_path = visuals_dir / f"simulation_frame_{step:03d}.png"
        fig, axes = plt.subplots(3, 2, figsize=(13, 9), facecolor="#151515")
        axes_flat = axes.flatten()
        for ax, metric in zip(axes_flat, SIMULATION_METRICS):
            plot_metric_lines(ax, rows, metric, max_step=step)
        axes_flat[-1].axis("off")
        handles, labels = axes_flat[0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="lower center", ncol=min(len(labels), 4), facecolor="#151515", labelcolor="#fff")
        fig.suptitle(f"Simulation Progress - Step {step}", color="#fff", fontsize=15, fontweight="bold")
        fig.tight_layout(rect=[0, 0.06, 1, 0.95])
        fig.savefig(frame_path, dpi=140, facecolor=fig.get_facecolor())
        plt.close(fig)
        frame_paths.append(frame_path)

    images = [Image.open(path) for path in frame_paths]
    gif_path = visuals_dir / "simulation_progress.gif"
    images[0].save(gif_path, save_all=True, append_images=images[1:], duration=1200, loop=0)
    for image in images:
        image.close()
    return gif_path


def generate_visuals(rows: List[Dict[str, object]], output_dir: Path) -> None:
    """
    Description:
        Generate outputs for `generate_visuals`.

    Input:
        rows: List[Dict[str, object]]; output_dir: Path.

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    if not rows:
        return
    visuals_dir = output_dir / "visuals"
    visuals_dir.mkdir(parents=True, exist_ok=True)
    save_trend_plot(rows, visuals_dir)
    save_progress_gif(rows, visuals_dir)


def persist_simulation_outputs(args: argparse.Namespace, rows: List[Dict[str, object]]) -> None:
    """
    Description:
        Persist outputs for `persist_simulation_outputs`.

    Input:
        args: argparse.Namespace; rows: List[Dict[str, object]].

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    write_csv(args.output_dir / "metrics_timeline.csv", rows, TIMELINE_FIELDS)
    write_csv(args.output_dir / "simulation_summary.csv", summarize_timeline(rows), SUMMARY_FIELDS)
    generate_visuals(rows, args.output_dir)

    try:
        subprocess.run([
            sys.executable,
            str(BUILD_DASHBOARD_SCRIPT),
            "--results-dir",
            str(args.dashboard_results_dir),
            "--simulation-dir",
            str(args.output_dir),
            "--output",
            str(PROJECT_ROOT / "dashboard" / "data" / "dashboard-data.js"),
        ], cwd=PROJECT_ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Dashboard refresh failed after this simulation step: {exc}", flush=True)


def worker_env(worker_threads: int) -> Dict[str, str]:
    """
    Description:
        Build worker settings for `worker_env`.

    Input:
        worker_threads: int.

    Output:
        Dict[str, str].
    """
    env = os.environ.copy()
    if worker_threads > 0:
        for name in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"]:
            env[name] = str(worker_threads)
    return env


def run_model_step(args: argparse.Namespace, step: int, epochs: int, model: str) -> Path:
    """
    Description:
        Run processing for `run_model_step`.

    Input:
        args: argparse.Namespace; step: int; epochs: int; model: str.

    Output:
        Path.
    """
    output_dir = args.output_dir / f"step_{step:03d}" / model
    log_path = PROJECT_ROOT / "logs" / f"simulation_step_{step:03d}_{model}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    cmd = [
        sys.executable,
        str(BENCHMARK_SCRIPT),
        "--sample-rows",
        str(args.sample_rows),
        "--sessions-per-person",
        str(args.sessions_per_person),
        "--n-runs",
        str(args.n_runs),
        "--models",
        model,
        "--epochs",
        str(epochs),
        "--batch-size",
        str(args.batch_size),
        "--tabsyn-steps",
        str(args.tabsyn_steps),
        "--epsilon",
        str(args.epsilon),
        "--delta",
        str(args.delta),
        "--dp-epsilon",
        str(args.dp_epsilon),
        "--dp-delta",
        str(args.dp_delta),
        "--pate-epsilon",
        str(args.pate_epsilon),
        "--pate-delta",
        str(args.pate_delta),
        "--latent-dim",
        str(args.latent_dim),
        "--teacher-iters",
        str(args.teacher_iters),
        "--student-iters",
        str(args.student_iters),
        "--target",
        args.target,
        "--task",
        args.task,
        "--output-dir",
        str(output_dir),
        "--log-path",
        str(log_path),
    ]
    print(f"Starting step {step}/{args.steps}, model={model}, epochs={epochs}, log={log_path}", flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", errors="replace") as handle:
        handle.write(f"Simulation model step started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        handle.write(f"Step: {step}\n")
        handle.write(f"Model: {model}\n")
        handle.write(f"Epochs: {epochs}\n")
        handle.write(f"Output folder: {output_dir}\n")
        handle.write("Command: " + " ".join(cmd) + "\n\n")
        handle.flush()
        subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            check=True,
            env=worker_env(args.worker_threads),
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        handle.write(f"\nSimulation model step finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    print(f"Finished step {step}/{args.steps}, model={model}", flush=True)
    return output_dir


def run_step(args: argparse.Namespace, step: int, epochs: int) -> Path:
    """
    Description:
        Run processing for `run_step`.

    Input:
        args: argparse.Namespace; step: int; epochs: int.

    Output:
        Path.
    """
    step_dir = args.output_dir / f"step_{step:03d}"
    models = parse_models(args.models)
    max_workers = max(1, min(args.max_workers, len(models)))

    print(f"\n=== Simulation step {step}/{args.steps}: epochs={epochs}, models={len(models)}, workers={max_workers} ===", flush=True)
    if max_workers == 1:
        for model in models:
            run_model_step(args, step, epochs, model)
        return step_dir

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_model_step, args, step, epochs, model): model
            for model in models
        }
        for future in concurrent.futures.as_completed(futures):
            model = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f"Model-step failed: step={step}, model={model}, error={type(exc).__name__}: {exc}", flush=True)
                raise
    return step_dir


def merge_existing_outputs(args: argparse.Namespace) -> List[Dict[str, object]]:
    """
    Description:
        Merge outputs for `merge_existing_outputs`.

    Input:
        args: argparse.Namespace.

    Output:
        List[Dict[str, object]].
    """
    rows: List[Dict[str, object]] = []
    for step in range(1, args.steps + 1):
        epochs = args.start_epochs + ((step - 1) * args.epoch_step)
        step_dir = args.output_dir / f"step_{step:03d}"
        rows.extend(collect_step_metrics(step_dir, step, epochs, args.sample_rows, args.sessions_per_person))

    persist_simulation_outputs(args, rows)
    return rows


def main() -> None:
    """
    Description:
        Run the command-line entry point for `main`.

    Input:
        None.

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    parser = argparse.ArgumentParser(description="Run study-scale incremental synthetic-data simulations.")
    parser.add_argument("--models", default=DEFAULT_SIMULATION_MODELS)
    parser.add_argument("--sample-rows", type=int, default=0, help="Use 0 to run on all rows.")
    parser.add_argument("--sessions-per-person", type=int, default=3)
    parser.add_argument("--n-runs", type=int, default=5)
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--start-epochs", type=int, default=50)
    parser.add_argument("--epoch-step", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--tabsyn-steps", type=int, default=50)
    parser.add_argument("--epsilon", type=float, default=1.0)
    parser.add_argument("--delta", type=float, default=1e-5)
    parser.add_argument("--dp-epsilon", type=float, default=0.5)
    parser.add_argument("--dp-delta", type=float, default=1e-5)
    parser.add_argument("--pate-epsilon", type=float, default=1.0)
    parser.add_argument("--pate-delta", type=float, default=1e-5)
    parser.add_argument("--latent-dim", type=int, default=64)
    parser.add_argument("--teacher-iters", type=int, default=10)
    parser.add_argument("--student-iters", type=int, default=5)
    parser.add_argument("--target", default="Training_Outcome")
    parser.add_argument("--task", choices=["classification", "regression"], default="classification")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results" / "simulation")
    parser.add_argument("--dashboard-results-dir", type=Path, default=PROJECT_ROOT / "results" / "test")
    parser.add_argument("--max-workers", type=int, default=1, help="Number of model jobs to run in parallel within each step.")
    parser.add_argument("--worker-threads", type=int, default=1, help="CPU math threads assigned to each model worker.")
    parser.add_argument("--merge-only", action="store_true", help="Merge existing step/model outputs without launching model jobs.")
    args = parser.parse_args()

    if not args.output_dir.is_absolute():
        args.output_dir = PROJECT_ROOT / args.output_dir
    if not args.dashboard_results_dir.is_absolute():
        args.dashboard_results_dir = PROJECT_ROOT / args.dashboard_results_dir

    if args.merge_only:
        timeline_rows = merge_existing_outputs(args)
        print(f"\nMerged existing simulation outputs: {args.output_dir / 'metrics_timeline.csv'}")
        print(f"Simulation summary saved: {args.output_dir / 'simulation_summary.csv'}")
        return

    timeline_rows: List[Dict[str, object]] = []
    for step in range(1, args.steps + 1):
        epochs = args.start_epochs + ((step - 1) * args.epoch_step)
        step_dir = run_step(args, step, epochs)
        step_rows = collect_step_metrics(step_dir, step, epochs, args.sample_rows, args.sessions_per_person)
        timeline_rows.extend(step_rows)
        persist_simulation_outputs(args, timeline_rows)
        print(f"Simulation outputs refreshed after step {step}: {args.output_dir}", flush=True)

    print(f"\nSimulation timeline saved: {args.output_dir / 'metrics_timeline.csv'}")
    print(f"Simulation summary saved: {args.output_dir / 'simulation_summary.csv'}")


if __name__ == "__main__":
    main()
