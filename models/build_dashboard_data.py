"""
Build the static dashboard data payload for synSPORT.

Description:
    Collects metrics, logs, generated files, and simulation outputs from the
    results folders and writes a JavaScript data file consumed by the dashboard.

Input:
    Command-line arguments for the results folder, optional simulation folder,
    and dashboard data output path.

Output:
    dashboard/data/dashboard-data.js containing a JSON-compatible payload.

"""

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def rel(path: Path) -> str:
    """
    Description:
        Return a relative path for `rel`.

    Input:
        path: Path.

    Output:
        str.
    """
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def file_size(path: Path) -> int:
    """
    Description:
        Return file information for `file_size`.

    Input:
        path: Path.

    Output:
        int.
    """
    try:
        return path.stat().st_size
    except OSError:
        return 0


def count_csv_rows(path: Path) -> int:
    """
    Description:
        Count records for `count_csv_rows`.

    Input:
        path: Path.

    Output:
        int.
    """
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            row_count = sum(1 for _ in reader)
        return max(row_count - 1, 0)
    except OSError:
        return 0


def read_csv_dicts(path: Path, limit: int = 100) -> List[Dict[str, str]]:
    """
    Description:
        Read data for `read_csv_dicts`.

    Input:
        path: Path; limit: int.

    Output:
        List[Dict[str, str]].
    """
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for _, row in zip(range(limit), reader)]
    except OSError:
        return []


def read_json(path: Path) -> Dict[str, object]:
    """
    Description:
        Read data for `read_json`.

    Input:
        path: Path.

    Output:
        Dict[str, object].
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def list_files(folder: Path, patterns: Iterable[str], limit: int = 200) -> List[Dict[str, object]]:
    """
    Description:
        List files for `list_files`.

    Input:
        folder: Path; patterns: Iterable[str]; limit: int.

    Output:
        List[Dict[str, object]].
    """
    files: List[Path] = []
    for pattern in patterns:
        files.extend(folder.glob(pattern))
    unique_files = sorted({path.resolve(): path for path in files if path.is_file()}.values())
    return [
        {
            "name": path.name,
            "path": rel(path),
            "size": file_size(path),
            "rows": count_csv_rows(path) if path.suffix.lower() == ".csv" else None,
        }
        for path in unique_files[:limit]
    ]


def latest_log_lines(path: Path, max_lines: int = 40) -> List[str]:
    """
    Description:
        Return latest log lines for `latest_log_lines`.

    Input:
        path: Path; max_lines: int.

    Output:
        List[str].
    """
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-max_lines:]


def log_sort_key(path: Path) -> tuple[int, float]:
    """
    Description:
        Build log ordering data for `log_sort_key`.

    Input:
        path: Path.

    Output:
        tuple[int, float].
    """
    name = path.name.lower()
    if name.startswith("simulation_") and not name.startswith("simulation_step_"):
        priority = 0
    elif name.startswith("large_simulation"):
        priority = 1
    elif name.startswith("run_"):
        priority = 2
    elif name.startswith("simulation_step_"):
        priority = 3
    else:
        priority = 4
    return (priority, -path.stat().st_mtime)


def build_payload(results_dir: Path, simulation_dir: Path | None = None) -> Dict[str, object]:
    """
    Description:
        Build data for `build_payload`.

    Input:
        results_dir: Path; simulation_dir: Path | None.

    Output:
        Dict[str, object].
    """
    metrics_dir = results_dir / "metrics"
    synthetic_dir = results_dir / "synthetic"
    simulation_dir = simulation_dir or PROJECT_ROOT / "results" / "simulation"
    config_path = results_dir / "config" / "run_config.json"
    log_files = sorted((PROJECT_ROOT / "logs").glob("*.log"), key=log_sort_key)
    latest_log = log_files[0] if log_files else None

    model_files = list_files(PROJECT_ROOT / "models", ["*.py", "tabsyn/**/*.py"], limit=120)
    result_files = list_files(results_dir, ["**/*.csv", "**/*.json", "**/*.pdf"], limit=200)
    data_files = list_files(PROJECT_ROOT / "data", ["*.csv", "*.json"], limit=50)
    data_csv_files = sorted((PROJECT_ROOT / "data").glob("*.csv"))
    data_preview_file = data_csv_files[0] if data_csv_files else None
    session_files = list_files(synthetic_dir / "sessions", ["*.csv"], limit=50)
    simulation_files = list_files(
        simulation_dir,
        ["*.csv", "visuals/*.png", "visuals/*.gif", "step_*/**/*.csv", "step_*/**/*.json"],
        limit=160,
    )
    simulation_visuals = list_files(simulation_dir / "visuals", ["*.gif", "*.png", "*.mp4"], limit=40)

    payload: Dict[str, object] = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "project_root": str(PROJECT_ROOT),
        "results_dir": rel(results_dir) if results_dir.exists() else results_dir.as_posix(),
        "latest_log": {
            "name": latest_log.name,
            "path": rel(latest_log),
            "size": file_size(latest_log),
        } if latest_log else None,
        "folders": {
            "data": (PROJECT_ROOT / "data").exists(),
            "models": (PROJECT_ROOT / "models").exists(),
            "results": results_dir.exists(),
            "logs": (PROJECT_ROOT / "logs").exists(),
        },
        "config": read_json(config_path),
        "metrics_summary": read_csv_dicts(metrics_dir / "metrics_summary.csv", limit=200),
        "real_baselines": read_csv_dicts(metrics_dir / "real_baselines.csv", limit=80),
        "feature_dependence": read_csv_dicts(metrics_dir / "fd_metrics_with_pvalues.csv", limit=80),
        "statistical_similarity": read_csv_dicts(metrics_dir / "stat_sim_with_pvalues.csv", limit=80),
        "privacy": read_csv_dicts(metrics_dir / "privacy_metrics_with_pvalues.csv", limit=80),
        "utility": read_csv_dicts(metrics_dir / "ml_utility_with_pvalues.csv", limit=80),
        "simulation_timeline": read_csv_dicts(simulation_dir / "metrics_timeline.csv", limit=300),
        "simulation_summary": read_csv_dicts(simulation_dir / "simulation_summary.csv", limit=80),
        "simulation_files": simulation_files,
        "simulation_visuals": simulation_visuals,
        "synthetic_sessions": session_files,
        "result_files": result_files,
        "model_files": model_files,
        "data_files": data_files,
        "data_preview_file": rel(data_preview_file) if data_preview_file else None,
        "data_preview": read_csv_dicts(data_preview_file, limit=100) if data_preview_file else [],
        "logs": [
            {
                "name": path.name,
                "path": rel(path),
                "size": file_size(path),
            }
            for path in log_files[:20]
        ],
        "latest_log_tail": latest_log_lines(latest_log) if latest_log else [],
        "counts": {
            "model_files": len(model_files),
            "result_files": len(result_files),
            "data_files": len(data_files),
            "synthetic_session_files": len(session_files),
            "simulation_rows": len(read_csv_dicts(simulation_dir / "metrics_timeline.csv", limit=10000)),
            "log_files": len(log_files),
            "metrics_summary_rows": len(read_csv_dicts(metrics_dir / "metrics_summary.csv", limit=10000)),
        },
    }
    return payload


def main() -> None:
    """
    Description:
        Run the command-line entry point for `main`.

    Input:
        None.

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    parser = argparse.ArgumentParser(description="Build static data for the Syn Sport dashboard.")
    parser.add_argument("--results-dir", type=Path, default=PROJECT_ROOT / "results" / "test")
    parser.add_argument("--simulation-dir", type=Path, default=PROJECT_ROOT / "results" / "simulation")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "dashboard" / "data" / "dashboard-data.js")
    args = parser.parse_args()

    results_dir = args.results_dir
    if not results_dir.is_absolute():
        results_dir = PROJECT_ROOT / results_dir
    simulation_dir = args.simulation_dir
    if not simulation_dir.is_absolute():
        simulation_dir = PROJECT_ROOT / simulation_dir
    payload = build_payload(results_dir, simulation_dir)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=True, indent=2).replace("</", "<\\/")
    args.output.write_text(f"window.SYN_SPORT_DASHBOARD = {data};\n", encoding="utf-8")
    print(f"Dashboard data saved: {args.output}")


if __name__ == "__main__":
    main()
