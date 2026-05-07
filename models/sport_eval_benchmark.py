"""
Benchmark synthetic sport-session generators.

Description:
    Loads the sport tabular dataset, prepares participant and session features,
    trains selected synthetic-data generators, evaluates generated data with
    utility, statistical-similarity, privacy, and report metrics, and writes
    outputs for the dashboard.

Input:
    Command-line arguments for dataset path, model list, target column, task
    type, sampling, generated sessions per participant, training parameters,
    privacy parameters, and output folders.

Output:
    Synthetic session CSV files, metrics CSV files, plots, configuration files,
    logs, and static report assets under the selected output folder.

"""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import torch
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    explained_variance_score,
    f1_score,
    mean_absolute_percentage_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, OrdinalEncoder

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*deprecated as an API.*")
warnings.filterwarnings("ignore", message=".*SingleTableMetadata.*")
warnings.filterwarnings("ignore", message=".*sample rate.*")
warnings.filterwarnings("ignore", message=".*Secure RNG.*")
warnings.filterwarnings("ignore", message=".*non-full backward hook.*")

try:
    from syn_metrics import SyntheticDataMetrics
except ImportError:
    from models.syn_metrics import SyntheticDataMetrics

try:
    from sdv.metadata import SingleTableMetadata
    from sdv.sequential import PARSynthesizer
    from sdv.single_table import CTGANSynthesizer, GaussianCopulaSynthesizer, TVAESynthesizer
except ImportError:
    SingleTableMetadata = None
    PARSynthesizer = None
    CTGANSynthesizer = None
    GaussianCopulaSynthesizer = None
    TVAESynthesizer = None

try:
    from realtabformer import REaLTabFormer
    from transformers import GPT2Config
except Exception as exc:
    REaLTabFormer = None
    GPT2Config = None
    REALTABFORMER_IMPORT_ERROR = exc
else:
    REALTABFORMER_IMPORT_ERROR = None

try:
    from snsynth import Synthesizer
    from snsynth.transform import MinMaxTransformer
except ImportError:
    Synthesizer = None
    MinMaxTransformer = None

try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "tabular.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "test"
TABSYN_DIR = CURRENT_DIR / "tabsyn"
DATASET_NAME = "sport"


PREFERRED_STATIC_COLUMNS = [
    "Athlete_ID",
    "Age",
    "Gender",
    "Sport_Type",
    "Training_Experience_Years",
]

DOMAIN_BOUNDS = {
    "Oxygen_Saturation_pct": (0, 100),
    "Nutrition_Score": (0, 1),
    "Perceived_Fatigue_1to10": (1, 10),
    "Performance_Score": (0, 100),
}

INTEGER_LIKE_COLUMNS = {
    "Age",
    "Training_Experience_Years",
    "Heart_Rate_bpm",
    "HRV_ms",
    "Oxygen_Saturation_pct",
    "Respiration_Rate_bpm",
    "Step_Count",
    "Session_Duration_min",
    "Perceived_Fatigue_1to10",
    "Performance_Score",
}


@dataclass
class SportDataConfig:
    id_col: str
    target_col: str
    task_type: str
    static_cols: List[str]
    numeric_cols: List[str]
    categorical_cols: List[str]
    session_numeric_cols: List[str]
    session_categorical_cols: List[str]

    @property
    def continuous(self) -> List[str]:
        """
        Description:
            Return the continuous columns used for metric evaluation.

        Input:
            None.

        Output:
            List[str].
        """
        return [col for col in self.numeric_cols if col != self.id_col]

    @property
    def categorical(self) -> List[str]:
        """
        Description:
            Return the categorical columns used for metric evaluation.

        Input:
            None.

        Output:
            List[str].
        """
        return [col for col in self.categorical_cols if col != self.id_col]


class SessionBootstrapSynthesizer:
    """Lightweight baseline for quick checks before running heavier models."""

    def __init__(
        self,
        config: SportDataConfig,
        sessions_per_person: int,
        noise_scale: float,
        donor_min_pool: int,
        random_state: int,
    ) -> None:
        """
        Description:
            Initialize `SessionBootstrapSynthesizer` with configuration used by later methods.

        Input:
            config: SportDataConfig; sessions_per_person: int; noise_scale: float; donor_min_pool: int; random_state: int.

        Output:
            None; the function performs file, state, logging, or plotting side effects.
        """
        self.config = config
        self.sessions_per_person = sessions_per_person
        self.noise_scale = noise_scale
        self.donor_min_pool = donor_min_pool
        self.rng = np.random.default_rng(random_state)

    def fit(self, data: pd.DataFrame) -> "SessionBootstrapSynthesizer":
        """
        Description:
            Fit `SessionBootstrapSynthesizer` using the provided training data.

        Input:
            data: pd.DataFrame.

        Output:
            'SessionBootstrapSynthesizer'.
        """
        self.training_df = data.reset_index(drop=True).copy()
        self.columns = list(data.columns)
        self.numeric_bounds = get_numeric_bounds(data, self.config)
        self.numeric_std: Dict[str, float] = {}

        for col in self.config.session_numeric_cols:
            values = pd.to_numeric(self.training_df[col], errors="coerce")
            lower, upper = self.numeric_bounds.get(col, (float(values.min()), float(values.max())))
            std = float(values.std())
            if not np.isfinite(std) or std == 0:
                std = max((upper - lower) * 0.01, 1.0)
            self.numeric_std[col] = std
        return self

    def generate(self, athletes: pd.DataFrame) -> pd.DataFrame:
        """
        Description:
            Generate synthetic records using the fitted `SessionBootstrapSynthesizer` instance.

        Input:
            athletes: pd.DataFrame.

        Output:
            pd.DataFrame.
        """
        records = []
        for _, athlete in athletes.reset_index(drop=True).iterrows():
            donor_pool = self._donor_pool_for(athlete)
            donor_idx = self.rng.integers(0, len(donor_pool), size=self.sessions_per_person)
            donors = donor_pool.iloc[donor_idx].reset_index(drop=True)

            for session_no, (_, donor) in enumerate(donors.iterrows(), start=1):
                record = {}
                for col in self.columns:
                    if col in self.config.static_cols:
                        record[col] = athlete[col]
                    elif col in self.config.session_numeric_cols:
                        record[col] = self._jitter_numeric(col, donor[col])
                    else:
                        record[col] = donor[col]
                record["Synthetic_Session_Number"] = session_no
                records.append(record)

        return pd.DataFrame(records)

    def _donor_pool_for(self, athlete: pd.Series) -> pd.DataFrame:
        """
        Description:
            Run the internal `_donor_pool_for` helper for `SessionBootstrapSynthesizer`.

        Input:
            athlete: pd.Series.

        Output:
            pd.DataFrame.
        """
        pool = self.training_df
        for group_cols in (["Sport_Type", "Gender"], ["Sport_Type"], ["Gender"]):
            available = [col for col in group_cols if col in pool.columns and col in athlete.index]
            if not available:
                continue
            mask = pd.Series(True, index=pool.index)
            for col in available:
                mask &= pool[col] == athlete[col]
            candidate_pool = pool.loc[mask]
            if len(candidate_pool) >= self.donor_min_pool:
                return candidate_pool
        return pool

    def _jitter_numeric(self, col: str, value: object) -> object:
        """
        Description:
            Run the internal `_jitter_numeric` helper for `SessionBootstrapSynthesizer`.

        Input:
            col: str; value: object.

        Output:
            object.
        """
        numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(numeric_value):
            numeric_value = self.training_df[col].median()

        lower, upper = self.numeric_bounds[col]
        synthetic_value = float(
            np.clip(numeric_value + self.rng.normal(0, self.numeric_std[col] * self.noise_scale), lower, upper)
        )
        if col in INTEGER_LIKE_COLUMNS:
            return int(round(synthetic_value))
        return round(synthetic_value, 3)


class SDVCTGANSportSynthesizer:
    """CTGAN path kept close to the original benchmark."""

    def __init__(self, config: SportDataConfig, sessions_per_person: int, epochs: int, verbose: bool) -> None:
        """
        Description:
            Initialize `SDVCTGANSportSynthesizer` with configuration used by later methods.

        Input:
            config: SportDataConfig; sessions_per_person: int; epochs: int; verbose: bool.

        Output:
            None; the function performs file, state, logging, or plotting side effects.
        """
        if SingleTableMetadata is None or CTGANSynthesizer is None:
            raise ImportError("SDV is not installed in this environment.")
        self.config = config
        self.sessions_per_person = sessions_per_person
        self.epochs = epochs
        self.verbose = verbose

    def fit(self, data: pd.DataFrame) -> "SDVCTGANSportSynthesizer":
        """
        Description:
            Fit `SDVCTGANSportSynthesizer` using the provided training data.

        Input:
            data: pd.DataFrame.

        Output:
            'SDVCTGANSportSynthesizer'.
        """
        self.columns = list(data.columns)
        self.numeric_bounds = get_numeric_bounds(data, self.config)
        train_data = remove_identifier(data, self.config.id_col)

        metadata = SingleTableMetadata()
        metadata.detect_from_dataframe(train_data)
        self.synthesizer = CTGANSynthesizer(metadata, epochs=self.epochs, verbose=self.verbose)
        self.synthesizer.fit(train_data)
        return self

    def generate(self, athletes: pd.DataFrame) -> pd.DataFrame:
        """
        Description:
            Generate synthetic records using the fitted `SDVCTGANSportSynthesizer` instance.

        Input:
            athletes: pd.DataFrame.

        Output:
            pd.DataFrame.
        """
        synth_size = len(athletes) * self.sessions_per_person
        generated = self.synthesizer.sample(synth_size).reset_index(drop=True)
        return attach_generated_sessions(
            generated, athletes, self.config, self.sessions_per_person, self.columns, self.numeric_bounds
        )


class SDVSingleTableSportSynthesizer:
    """Additional SDV single-table synthesizers evaluated through the same benchmark metrics."""

    def __init__(
        self,
        config: SportDataConfig,
        sessions_per_person: int,
        synthesizer_cls,
        synthesizer_name: str,
        synthesizer_params: Dict[str, object],
    ) -> None:
        """
        Description:
            Initialize `SDVSingleTableSportSynthesizer` with configuration used by later methods.

        Input:
            config: SportDataConfig; sessions_per_person: int; synthesizer_cls; synthesizer_name: str; synthesizer_params: Dict[str, object].

        Output:
            None; the function performs file, state, logging, or plotting side effects.
        """
        if SingleTableMetadata is None or synthesizer_cls is None:
            raise ImportError("SDV is not installed in this environment.")
        self.config = config
        self.sessions_per_person = sessions_per_person
        self.synthesizer_cls = synthesizer_cls
        self.synthesizer_name = synthesizer_name
        self.synthesizer_params = synthesizer_params

    def fit(self, data: pd.DataFrame) -> "SDVSingleTableSportSynthesizer":
        """
        Description:
            Fit `SDVSingleTableSportSynthesizer` using the provided training data.

        Input:
            data: pd.DataFrame.

        Output:
            'SDVSingleTableSportSynthesizer'.
        """
        self.columns = list(data.columns)
        self.numeric_bounds = get_numeric_bounds(data, self.config)
        train_data = remove_identifier(data, self.config.id_col)

        metadata = SingleTableMetadata()
        metadata.detect_from_dataframe(train_data)
        self.synthesizer = self.synthesizer_cls(metadata, **self.synthesizer_params)
        self.synthesizer.fit(train_data)
        return self

    def generate(self, athletes: pd.DataFrame) -> pd.DataFrame:
        """
        Description:
            Generate synthetic records using the fitted `SDVSingleTableSportSynthesizer` instance.

        Input:
            athletes: pd.DataFrame.

        Output:
            pd.DataFrame.
        """
        synth_size = len(athletes) * self.sessions_per_person
        generated = self.synthesizer.sample(synth_size).reset_index(drop=True)
        return attach_generated_sessions(
            generated, athletes, self.config, self.sessions_per_person, self.columns, self.numeric_bounds
        )


class SDVPARSportSynthesizer:
    """SDV PAR wrapper for sequence-capable generation, evaluated with the same sport metrics."""

    def __init__(
        self,
        config: SportDataConfig,
        sessions_per_person: int,
        epochs: int,
        verbose: bool,
    ) -> None:
        """
        Description:
            Initialize `SDVPARSportSynthesizer` with configuration used by later methods.

        Input:
            config: SportDataConfig; sessions_per_person: int; epochs: int; verbose: bool.

        Output:
            None; the function performs file, state, logging, or plotting side effects.
        """
        if SingleTableMetadata is None or PARSynthesizer is None:
            raise ImportError("SDV sequential synthesizers are not installed in this environment.")
        self.config = config
        self.sessions_per_person = sessions_per_person
        self.epochs = epochs
        self.verbose = verbose

    def fit(self, data: pd.DataFrame) -> "SDVPARSportSynthesizer":
        """
        Description:
            Fit `SDVPARSportSynthesizer` using the provided training data.

        Input:
            data: pd.DataFrame.

        Output:
            'SDVPARSportSynthesizer'.
        """
        self.columns = list(data.columns)
        self.numeric_bounds = get_numeric_bounds(data, self.config)
        train_data = data.copy()

        metadata = SingleTableMetadata()
        metadata.detect_from_dataframe(train_data)
        metadata.set_primary_key(None)
        metadata.update_column(self.config.id_col, sdtype="id")
        metadata.set_sequence_key(self.config.id_col)

        self.synthesizer = PARSynthesizer(
            metadata,
            epochs=self.epochs,
            sample_size=1,
            cuda=torch.cuda.is_available(),
            verbose=self.verbose,
        )
        self.synthesizer.fit(train_data)
        return self

    def generate(self, athletes: pd.DataFrame) -> pd.DataFrame:
        """
        Description:
            Generate synthetic records using the fitted `SDVPARSportSynthesizer` instance.

        Input:
            athletes: pd.DataFrame.

        Output:
            pd.DataFrame.
        """
        generated = self.synthesizer.sample(num_sequences=len(athletes)).reset_index(drop=True)
        return attach_generated_sessions(
            generated, athletes, self.config, self.sessions_per_person, self.columns, self.numeric_bounds
        )


class REaLTabFormerSportSynthesizer:
    """REaLTabFormer tabular wrapper evaluated through the same sport-session benchmark."""

    def __init__(
        self,
        config: SportDataConfig,
        sessions_per_person: int,
        epochs: int,
        batch_size: int,
        output_dir: Path,
        random_state: int,
        verbose: bool,
    ) -> None:
        """
        Description:
            Initialize `REaLTabFormerSportSynthesizer` with configuration used by later methods.

        Input:
            config: SportDataConfig; sessions_per_person: int; epochs: int; batch_size: int; output_dir: Path; random_state: int; verbose: bool.

        Output:
            None; the function performs file, state, logging, or plotting side effects.
        """
        if REaLTabFormer is None or GPT2Config is None:
            message = "REaLTabFormer is not installed in this environment."
            if REALTABFORMER_IMPORT_ERROR is not None:
                message = f"{message} Import error: {REALTABFORMER_IMPORT_ERROR}"
            raise ImportError(message)
        self.config = config
        self.sessions_per_person = sessions_per_person
        self.epochs = epochs
        self.batch_size = max(1, min(batch_size, 8))
        self.output_dir = output_dir
        self.random_state = random_state
        self.verbose = verbose

    def fit(self, data: pd.DataFrame) -> "REaLTabFormerSportSynthesizer":
        """
        Description:
            Fit `REaLTabFormerSportSynthesizer` using the provided training data.

        Input:
            data: pd.DataFrame.

        Output:
            'REaLTabFormerSportSynthesizer'.
        """
        self.columns = list(data.columns)
        self.numeric_bounds = get_numeric_bounds(data, self.config)
        train_data = remove_identifier(data, self.config.id_col).copy()

        model_dir = self.output_dir / "model_artifacts" / "realtabformer"
        model_dir.mkdir(parents=True, exist_ok=True)

        tabular_config = GPT2Config(
            n_layer=2,
            n_head=2,
            n_embd=128,
            n_positions=256,
        )
        self.synthesizer = REaLTabFormer(
            model_type="tabular",
            tabular_config=tabular_config,
            epochs=self.epochs,
            batch_size=self.batch_size,
            random_state=self.random_state,
            train_size=1,
            checkpoints_dir=str(model_dir / "checkpoints"),
            samples_save_dir=str(model_dir / "samples"),
            full_save_dir=str(model_dir / "full"),
            logging_steps=50,
            save_steps=500,
            eval_steps=500,
            report_to=[],
            disable_tqdm=not self.verbose,
            dataloader_pin_memory=False,
        )
        self.synthesizer.fit(
            train_data,
            device="cpu",
            n_critic=0,
            target_col=self.config.target_col,
        )
        return self

    def generate(self, athletes: pd.DataFrame) -> pd.DataFrame:
        """
        Description:
            Generate synthetic records using the fitted `REaLTabFormerSportSynthesizer` instance.

        Input:
            athletes: pd.DataFrame.

        Output:
            pd.DataFrame.
        """
        synth_size = len(athletes) * self.sessions_per_person
        generated = self.synthesizer.sample(
            n_samples=synth_size,
            device="cpu",
            gen_batch=max(1, min(64, synth_size)),
            save_samples=False,
        ).reset_index(drop=True)
        return attach_generated_sessions(
            generated, athletes, self.config, self.sessions_per_person, self.columns, self.numeric_bounds
        )


class SmartNoiseSportSynthesizer:
    """DPCTGAN/PATEGAN path kept close to the original SmartNoise benchmark."""

    def __init__(
        self,
        config: SportDataConfig,
        sessions_per_person: int,
        model_name: str,
        model_params: Dict[str, object],
    ) -> None:
        """
        Description:
            Initialize `SmartNoiseSportSynthesizer` with configuration used by later methods.

        Input:
            config: SportDataConfig; sessions_per_person: int; model_name: str; model_params: Dict[str, object].

        Output:
            None; the function performs file, state, logging, or plotting side effects.
        """
        if Synthesizer is None or MinMaxTransformer is None:
            raise ImportError("SmartNoise Synth is not installed in this environment.")
        self.config = config
        self.sessions_per_person = sessions_per_person
        self.model_name = model_name
        self.model_params = model_params

    def fit(self, data: pd.DataFrame) -> "SmartNoiseSportSynthesizer":
        """
        Description:
            Fit `SmartNoiseSportSynthesizer` using the provided training data.

        Input:
            data: pd.DataFrame.

        Output:
            'SmartNoiseSportSynthesizer'.
        """
        if self.model_name == "pategan" and len(data) < 1000:
            raise ValueError("PATEGAN needs at least 1000 rows because it creates one teacher per 1000 records.")

        self.columns = list(data.columns)
        self.numeric_bounds = get_numeric_bounds(data, self.config)
        train_data = remove_identifier(data, self.config.id_col).copy()

        categorical_cols = [col for col in self.config.categorical if col in train_data.columns]
        continuous_cols = [col for col in self.config.continuous if col in train_data.columns]
        constraints = self._continuous_constraints(train_data, continuous_cols)

        params = dict(self.model_params)
        if self.model_name == "dpctgan":
            params.setdefault("cuda", torch.cuda.is_available())

        self.synthesizer = Synthesizer.create(self.model_name, **params)
        self.synthesizer.fit(
            train_data,
            transformer=constraints,
            categorical_columns=categorical_cols,
            continuous_columns=continuous_cols,
            preprocessor_eps=0.2,
        )
        return self

    def generate(self, athletes: pd.DataFrame) -> pd.DataFrame:
        """
        Description:
            Generate synthetic records using the fitted `SmartNoiseSportSynthesizer` instance.

        Input:
            athletes: pd.DataFrame.

        Output:
            pd.DataFrame.
        """
        synth_size = len(athletes) * self.sessions_per_person
        generated = self.synthesizer.sample(synth_size).reset_index(drop=True)
        return attach_generated_sessions(
            generated, athletes, self.config, self.sessions_per_person, self.columns, self.numeric_bounds
        )

    def _continuous_constraints(self, train_data: pd.DataFrame, continuous_cols: Iterable[str]) -> Dict[str, object]:
        """
        Description:
            Run the internal `_continuous_constraints` helper for `SmartNoiseSportSynthesizer`.

        Input:
            train_data: pd.DataFrame; continuous_cols: Iterable[str].

        Output:
            Dict[str, object].
        """
        constraints = {}
        for col in continuous_cols:
            values = pd.to_numeric(train_data[col], errors="coerce").dropna()
            lower = float(values.min())
            upper = float(values.max())
            if np.isfinite(lower) and np.isfinite(upper):
                if lower == upper:
                    upper = lower + 1.0
                constraints[col] = MinMaxTransformer(lower=lower, upper=upper, nullable=False)
        return constraints


class TabSynSportSynthesizer:
    """TabSyn wrapper that runs the copied author scripts through their CLI."""

    def __init__(
        self,
        config: SportDataConfig,
        sessions_per_person: int,
        epochs: int,
        batch_size: int,
        steps: int,
        gpu: int,
        output_dir: Path,
    ) -> None:
        """
        Description:
            Initialize `TabSynSportSynthesizer` with configuration used by later methods.

        Input:
            config: SportDataConfig; sessions_per_person: int; epochs: int; batch_size: int; steps: int; gpu: int; output_dir: Path.

        Output:
            None; the function performs file, state, logging, or plotting side effects.
        """
        if not TABSYN_DIR.exists():
            raise FileNotFoundError(f"TabSyn folder not found: {TABSYN_DIR}")
        self.config = config
        self.sessions_per_person = sessions_per_person
        self.epochs = epochs
        self.batch_size = batch_size
        self.steps = steps
        self.gpu = gpu
        self.output_dir = output_dir
        self.dataname = DATASET_NAME
        self.sample_counter = 0

    def fit(self, data: pd.DataFrame) -> "TabSynSportSynthesizer":
        """
        Description:
            Fit `TabSynSportSynthesizer` using the provided training data.

        Input:
            data: pd.DataFrame.

        Output:
            'TabSynSportSynthesizer'.
        """
        self.columns = list(data.columns)
        self.numeric_bounds = get_numeric_bounds(data, self.config)
        train_data = remove_identifier(data, self.config.id_col).copy()

        prepare_tabsyn_dataset(train_data, self.config, self.dataname)

        self._run(["process_dataset.py", "--dataname", self.dataname])
        self._run([
            "main.py",
            "--dataname",
            self.dataname,
            "--method",
            "vae",
            "--mode",
            "train",
            "--epochs",
            str(self.epochs),
            "--batch_size",
            str(self.batch_size),
            "--gpu",
            str(self.gpu),
        ])
        self._run([
            "main.py",
            "--dataname",
            self.dataname,
            "--method",
            "tabsyn",
            "--mode",
            "train",
            "--epochs",
            str(self.epochs),
            "--batch_size",
            str(self.batch_size),
            "--gpu",
            str(self.gpu),
        ])
        return self

    def generate(self, athletes: pd.DataFrame) -> pd.DataFrame:
        """
        Description:
            Generate synthetic records using the fitted `TabSynSportSynthesizer` instance.

        Input:
            athletes: pd.DataFrame.

        Output:
            pd.DataFrame.
        """
        self.sample_counter += 1
        synth_size = len(athletes) * self.sessions_per_person
        sample_path = TABSYN_DIR / "synthetic" / self.dataname / f"tabsyn_trial_{self.sample_counter}.csv"

        self._run([
            "main.py",
            "--dataname",
            self.dataname,
            "--method",
            "tabsyn",
            "--mode",
            "sample",
            "--steps",
            str(self.steps),
            "--num-samples",
            str(synth_size),
            "--save_path",
            str(sample_path.relative_to(TABSYN_DIR)),
            "--gpu",
            str(self.gpu),
        ])
        generated = pd.read_csv(sample_path)
        return attach_generated_sessions(
            generated, athletes, self.config, self.sessions_per_person, self.columns, self.numeric_bounds
        )

    def _run(self, args: List[str]) -> None:
        """
        Description:
            Run the internal `_run` helper for `TabSynSportSynthesizer`.

        Input:
            args: List[str].

        Output:
            None; the function performs file, state, logging, or plotting side effects.
        """
        cmd = [sys.executable, *args]
        print("$ " + " ".join(args), flush=True)
        env = os.environ.copy()
        env["PYTHONWARNINGS"] = "ignore"
        subprocess.run(cmd, cwd=TABSYN_DIR, check=True, env=env)

def prepare_tabsyn_dataset(train_data: pd.DataFrame, config: SportDataConfig, dataname: str) -> None:
    """
    Description:
        Prepare data for `prepare_tabsyn_dataset`.

    Input:
        train_data: pd.DataFrame; config: SportDataConfig; dataname: str.

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    data_dir = TABSYN_DIR / "data" / dataname
    info_dir = TABSYN_DIR / "data" / "Info"
    data_dir.mkdir(parents=True, exist_ok=True)
    info_dir.mkdir(parents=True, exist_ok=True)

    data_path = data_dir / f"{dataname}.csv"
    train_data.to_csv(data_path, index=False)

    columns = list(train_data.columns)
    target_idx = columns.index(config.target_col)
    num_col_idx = []
    cat_col_idx = []

    for idx, col in enumerate(columns):
        if idx == target_idx:
            continue
        if pd.api.types.is_numeric_dtype(train_data[col]):
            num_col_idx.append(idx)
        else:
            cat_col_idx.append(idx)

    task_type = "regression"
    n_classes = None
    if config.task_type == "classification":
        n_classes = int(train_data[config.target_col].nunique())
        task_type = "binclass" if n_classes == 2 else "multiclass"

    info = {
        "name": dataname,
        "task_type": task_type,
        "header": "infer",
        "column_names": None,
        "num_col_idx": num_col_idx,
        "cat_col_idx": cat_col_idx,
        "target_col_idx": [target_idx],
        "file_type": "csv",
        "data_path": f"data/{dataname}/{dataname}.csv",
        "test_path": None,
    }
    if n_classes is not None:
        info["n_classes"] = n_classes

    with open(info_dir / f"{dataname}.json", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=4)


def read_dataset(path: Path) -> pd.DataFrame:
    """
    Description:
        Read data for `read_dataset`.

    Input:
        path: Path.

    Output:
        pd.DataFrame.
    """
    df = pd.read_csv(path)
    df.columns = [col.strip() for col in df.columns]

    for col in df.columns:
        if col == "Athlete_ID":
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() == df[col].notna().sum():
            df[col] = converted
    return df


def infer_config(df: pd.DataFrame, id_col: str, target_col: str, task_type: str) -> SportDataConfig:
    """
    Description:
        Infer configuration for `infer_config`.

    Input:
        df: pd.DataFrame; id_col: str; target_col: str; task_type: str.

    Output:
        SportDataConfig.
    """
    if id_col not in df.columns:
        raise ValueError(f"ID column '{id_col}' not found in dataset.")
    if target_col not in df.columns:
        raise ValueError(f"Target column '{target_col}' not found in dataset.")

    static_cols = [col for col in PREFERRED_STATIC_COLUMNS if col in df.columns]
    if id_col not in static_cols:
        static_cols.insert(0, id_col)

    numeric_cols = [col for col in df.columns if col != id_col and pd.api.types.is_numeric_dtype(df[col])]
    categorical_cols = [col for col in df.columns if col != id_col and not pd.api.types.is_numeric_dtype(df[col])]

    session_numeric_cols = [col for col in numeric_cols if col not in static_cols]
    session_categorical_cols = [col for col in categorical_cols if col not in static_cols]

    return SportDataConfig(
        id_col=id_col,
        target_col=target_col,
        task_type=task_type,
        static_cols=static_cols,
        numeric_cols=numeric_cols,
        categorical_cols=categorical_cols,
        session_numeric_cols=session_numeric_cols,
        session_categorical_cols=session_categorical_cols,
    )


def remove_identifier(df: pd.DataFrame, id_col: str) -> pd.DataFrame:
    """
    Description:
        Remove helper columns for `remove_identifier`.

    Input:
        df: pd.DataFrame; id_col: str.

    Output:
        pd.DataFrame.
    """
    return df.drop(columns=[id_col], errors="ignore")


def remove_evaluation_helpers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Description:
        Remove helper columns for `remove_evaluation_helpers`.

    Input:
        df: pd.DataFrame.

    Output:
        pd.DataFrame.
    """
    return df.drop(columns=["Synthetic_Session_Number"], errors="ignore")


def preprocess_data(df: pd.DataFrame, config: SportDataConfig) -> pd.DataFrame:
    """
    Description:
        Preprocess data for `preprocess_data`.

    Input:
        df: pd.DataFrame; config: SportDataConfig.

    Output:
        pd.DataFrame.
    """
    df_clean = df.dropna().reset_index(drop=True)
    print(f"Original rows: {len(df)}")
    print(f"Clean rows: {len(df_clean)}")
    print(f"Dropped: {len(df) - len(df_clean)} rows")
    print("Target distribution:\n", df_clean[config.target_col].value_counts())
    return df_clean


def prepare_features(X_train: pd.DataFrame, X_test: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Description:
        Prepare data for `prepare_features`.

    Input:
        X_train: pd.DataFrame; X_test: pd.DataFrame.

    Output:
        Tuple[pd.DataFrame, pd.DataFrame].
    """
    X_train = X_train.copy()
    X_test = X_test.copy()
    cat_cols = X_train.select_dtypes(include=["object", "category"]).columns

    if len(cat_cols) > 0:
        X_train[cat_cols] = X_train[cat_cols].astype(str).fillna("NA")
        X_test[cat_cols] = X_test[cat_cols].astype(str).fillna("NA")
        enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        X_train[cat_cols] = enc.fit_transform(X_train[cat_cols])
        X_test[cat_cols] = enc.transform(X_test[cat_cols])

    for col in X_train.columns:
        X_train[col] = pd.to_numeric(X_train[col], errors="coerce")
        X_test[col] = pd.to_numeric(X_test[col], errors="coerce")
        median = X_train[col].median()
        X_train[col] = X_train[col].fillna(median)
        X_test[col] = X_test[col].fillna(median)

    return X_train, X_test


def train_model(X_train, y_train, X_test, y_test, classification=True):
    """
    Description:
        Train a predictive model for `train_model`.

    Input:
        X_train; y_train; X_test; y_test; classification.

    Output:
        Computed value returned by the function.
    """
    if not isinstance(X_train, pd.DataFrame):
        X_train = pd.DataFrame(X_train)
    if not isinstance(X_test, pd.DataFrame):
        X_test = pd.DataFrame(X_test)

    common_cols = [col for col in X_train.columns if col in X_test.columns]
    X_train = X_train[common_cols]
    X_test = X_test[common_cols]
    X_train, X_test = prepare_features(X_train, X_test)

    if classification:
        le = LabelEncoder()
        combined = pd.concat([pd.Series(y_train), pd.Series(y_test)], axis=0).astype(str)
        le.fit(combined)
        y_train = le.transform(pd.Series(y_train).astype(str))
        y_test = le.transform(pd.Series(y_test).astype(str))

        clf = RandomForestClassifier(random_state=0)
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_test)

        y_proba = None
        if hasattr(clf, "predict_proba"):
            proba = clf.predict_proba(X_test)
            y_proba = proba[:, 1] if proba.shape[1] == 2 else None

        return {
            "Accuracy": accuracy_score(y_test, y_pred),
            "F1-score": f1_score(y_test, y_pred, average="weighted"),
            "AUROC": roc_auc_score(y_test, y_proba) if y_proba is not None else None,
            "AUPRC": average_precision_score(y_test, y_proba) if y_proba is not None else None,
            "Classes": str(le.classes_),
        }

    y_train = pd.to_numeric(pd.Series(y_train), errors="coerce")
    y_test = pd.to_numeric(pd.Series(y_test), errors="coerce")
    reg = RandomForestRegressor(random_state=0)
    reg.fit(X_train, y_train)
    y_pred = reg.predict(X_test)

    return {
        "MAPE": mean_absolute_percentage_error(y_test, y_pred),
        "R2": r2_score(y_test, y_pred),
        "EVS": explained_variance_score(y_test, y_pred),
        "Target_range": f"{y_train.min():.2f}-{y_train.max():.2f}",
    }


def get_numeric_bounds(df: pd.DataFrame, config: SportDataConfig) -> Dict[str, Tuple[float, float]]:
    """
    Description:
        Return values for `get_numeric_bounds`.

    Input:
        df: pd.DataFrame; config: SportDataConfig.

    Output:
        Dict[str, Tuple[float, float]].
    """
    bounds = {}
    for col in config.numeric_cols:
        if col not in df.columns:
            continue
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        if values.empty:
            continue
        lower = float(values.min())
        upper = float(values.max())
        if col in DOMAIN_BOUNDS:
            domain_lower, domain_upper = DOMAIN_BOUNDS[col]
            lower = max(lower, domain_lower)
            upper = min(upper, domain_upper)
        bounds[col] = (lower, upper)
    return bounds


def postprocess_generated_data(
    df: pd.DataFrame,
    config: SportDataConfig,
    numeric_bounds: Optional[Dict[str, Tuple[float, float]]] = None,
) -> pd.DataFrame:
    """
    Description:
        Postprocess generated data for `postprocess_generated_data`.

    Input:
        df: pd.DataFrame; config: SportDataConfig; numeric_bounds: Optional[Dict[str, Tuple[float, float]]].

    Output:
        pd.DataFrame.
    """
    df = df.copy()
    numeric_bounds = numeric_bounds or {}

    for col in config.numeric_cols:
        if col not in df.columns:
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if col in numeric_bounds:
            lower, upper = numeric_bounds[col]
            df[col] = df[col].clip(lower, upper)
        elif col in DOMAIN_BOUNDS:
            lower, upper = DOMAIN_BOUNDS[col]
            df[col] = df[col].clip(lower, upper)
        if col in INTEGER_LIKE_COLUMNS:
            df[col] = df[col].round().astype("Int64")

    return df


def attach_generated_sessions(
    generated: pd.DataFrame,
    athletes: pd.DataFrame,
    config: SportDataConfig,
    sessions_per_person: int,
    original_columns: List[str],
    numeric_bounds: Optional[Dict[str, Tuple[float, float]]] = None,
) -> pd.DataFrame:
    """
    Description:
        Attach generated records for `attach_generated_sessions`.

    Input:
        generated: pd.DataFrame; athletes: pd.DataFrame; config: SportDataConfig; sessions_per_person: int; original_columns: List[str]; numeric_bounds: Optional[Dict[str, Tuple[float, float]]].

    Output:
        pd.DataFrame.
    """
    athletes = athletes.reset_index(drop=True)
    repeated_athletes = athletes.loc[athletes.index.repeat(sessions_per_person)].reset_index(drop=True)
    synth_size = len(repeated_athletes)

    generated = generated.reset_index(drop=True)
    if generated.empty:
        raise ValueError("Synthetic model returned no rows.")
    if len(generated) < synth_size:
        generated = generated.sample(n=synth_size, replace=True, random_state=42).reset_index(drop=True)
    else:
        generated = generated.iloc[:synth_size].reset_index(drop=True)

    for col in original_columns:
        if col not in generated.columns and col != config.id_col:
            generated[col] = np.nan

    for col in config.static_cols:
        if col in repeated_athletes.columns:
            generated[col] = repeated_athletes[col].values

    generated[config.id_col] = repeated_athletes[config.id_col].values
    generated["Synthetic_Session_Number"] = np.tile(np.arange(1, sessions_per_person + 1), len(athletes))
    generated = postprocess_generated_data(generated, config, numeric_bounds)

    return generated[original_columns + ["Synthetic_Session_Number"]]


def compute_statistical_metrics(real_df: pd.DataFrame, synth_data: pd.DataFrame, config: SportDataConfig):
    """
    Description:
        Compute metrics for `compute_statistical_metrics`.

    Input:
        real_df: pd.DataFrame; synth_data: pd.DataFrame; config: SportDataConfig.

    Output:
        Computed value returned by the function.
    """
    real_eval = remove_evaluation_helpers(remove_identifier(real_df, config.id_col))
    synth_eval = remove_evaluation_helpers(remove_identifier(synth_data, config.id_col))
    continuous = [col for col in config.continuous if col in real_eval.columns and col in synth_eval.columns]
    categorical = [col for col in config.categorical if col in real_eval.columns and col in synth_eval.columns]

    return {
        "PearsonCorrDiff": SyntheticDataMetrics.pearson_correlation_difference(
            real_eval, synth_eval, continuous_cols=continuous
        ),
        "UncertaintyCoeffDiff": SyntheticDataMetrics.uncertainty_coefficient_difference(
            real_eval, synth_eval, categorical_cols=categorical
        ),
        "CorrelationRatioDiff": SyntheticDataMetrics.correlation_ratio_difference(
            real_eval, synth_eval, categorical_cols=categorical, continuous_cols=continuous
        ),
        "Wasserstein": SyntheticDataMetrics.calculate_wasserstein(
            real_eval[continuous], synth_eval[continuous], continuous
        ),
        "JSD": SyntheticDataMetrics.calculate_jsd(
            real_eval[categorical], synth_eval[categorical], categorical
        ),
    }


def evaluate_real_data_baseline(df: pd.DataFrame, config: SportDataConfig, test_size: float):
    """
    Description:
        Evaluate data for `evaluate_real_data_baseline`.

    Input:
        df: pd.DataFrame; config: SportDataConfig; test_size: float.

    Output:
        Computed value returned by the function.
    """
    df_clean = preprocess_data(df, config)
    real_eval = remove_evaluation_helpers(remove_identifier(df_clean, config.id_col))
    X_real = real_eval.drop(columns=[config.target_col])
    y_real = real_eval[config.target_col]
    classification = SyntheticDataMetrics.is_classification(y_real)

    X_train, X_test, y_train, y_test = train_test_split(
        X_real, y_real, test_size=test_size, random_state=42, stratify=y_real if classification else None
    )

    print("\nGetting Real data utility metrics (baseline)")
    real_utility = train_model(X_train, y_train, X_test, y_test, classification)
    real_utility.update(compute_statistical_metrics(df_clean, df_clean, config))
    print("\nReal data utility metrics (baseline)", real_utility)

    print("\nGetting Real data attack metrics (baseline)")
    real_attack = SyntheticDataMetrics.model_inversion_attack(real_eval, real_eval, config.target_col)
    print("\nReal data attack metrics (baseline)", real_attack)

    return df_clean, real_utility, real_attack


def create_synthesizer(model_name: str, args: argparse.Namespace, config: SportDataConfig):
    """
    Description:
        Create objects for `create_synthesizer`.

    Input:
        model_name: str; args: argparse.Namespace; config: SportDataConfig.

    Output:
        Computed value returned by the function.
    """
    if model_name == "bootstrap":
        return SessionBootstrapSynthesizer(
            config=config,
            sessions_per_person=args.sessions_per_person,
            noise_scale=args.noise_scale,
            donor_min_pool=args.donor_min_pool,
            random_state=args.random_state,
        )
    if model_name == "ctgan":
        return SDVCTGANSportSynthesizer(
            config=config,
            sessions_per_person=args.sessions_per_person,
            epochs=args.epochs,
            verbose=args.verbose,
        )
    if model_name == "sdv_gaussian":
        return SDVSingleTableSportSynthesizer(
            config=config,
            sessions_per_person=args.sessions_per_person,
            synthesizer_cls=GaussianCopulaSynthesizer,
            synthesizer_name=model_name,
            synthesizer_params={
                "enforce_min_max_values": True,
                "enforce_rounding": True,
            },
        )
    if model_name == "sdv_tvae":
        return SDVSingleTableSportSynthesizer(
            config=config,
            sessions_per_person=args.sessions_per_person,
            synthesizer_cls=TVAESynthesizer,
            synthesizer_name=model_name,
            synthesizer_params={
                "epochs": args.epochs,
                "batch_size": args.batch_size,
                "verbose": args.verbose,
                "cuda": torch.cuda.is_available(),
            },
        )
    if model_name == "sdv_par":
        return SDVPARSportSynthesizer(
            config=config,
            sessions_per_person=args.sessions_per_person,
            epochs=args.epochs,
            verbose=args.verbose,
        )
    if model_name == "realtabformer":
        return REaLTabFormerSportSynthesizer(
            config=config,
            sessions_per_person=args.sessions_per_person,
            epochs=args.epochs,
            batch_size=args.batch_size,
            output_dir=args.output_dir,
            random_state=args.random_state,
            verbose=args.verbose,
        )
    if model_name == "dpctgan":
        dp_epsilon = args.dp_epsilon if args.dp_epsilon is not None else args.epsilon
        dp_delta = args.dp_delta if args.dp_delta is not None else args.delta
        return SmartNoiseSportSynthesizer(
            config=config,
            sessions_per_person=args.sessions_per_person,
            model_name=model_name,
            model_params={
                "epsilon": dp_epsilon,
                "delta": dp_delta,
                "batch_size": args.batch_size,
                "epochs": args.epochs,
                "cuda": torch.cuda.is_available(),
                "verbose": args.verbose,
            },
        )
    if model_name == "pategan":
        pate_epsilon = args.pate_epsilon if args.pate_epsilon is not None else args.epsilon
        pate_delta = args.pate_delta if args.pate_delta is not None else args.delta
        return SmartNoiseSportSynthesizer(
            config=config,
            sessions_per_person=args.sessions_per_person,
            model_name=model_name,
            model_params={
                "epsilon": pate_epsilon,
                "delta": pate_delta,
                "binary": False,
                "latent_dim": args.latent_dim,
                "batch_size": args.batch_size,
                "teacher_iters": args.teacher_iters,
                "student_iters": args.student_iters,
            },
        )
    if model_name == "tabsyn":
        return TabSynSportSynthesizer(
            config=config,
            sessions_per_person=args.sessions_per_person,
            epochs=args.epochs,
            batch_size=args.batch_size,
            steps=args.tabsyn_steps,
            gpu=args.gpu,
            output_dir=args.output_dir,
        )
    raise ValueError(f"Unsupported model: {model_name}")


def evaluate_synthetic_data_model(
    real_df: pd.DataFrame,
    config: SportDataConfig,
    model_name: str,
    args: argparse.Namespace,
):
    """
    Description:
        Evaluate data for `evaluate_synthetic_data_model`.

    Input:
        real_df: pd.DataFrame; config: SportDataConfig; model_name: str; args: argparse.Namespace.

    Output:
        Computed value returned by the function.
    """
    real_eval_full = remove_evaluation_helpers(remove_identifier(real_df, config.id_col))
    X_real = real_eval_full.drop(columns=[config.target_col])
    y_real = real_eval_full[config.target_col]
    classification = SyntheticDataMetrics.is_classification(y_real)
    _, X_real_test, _, y_real_test = train_test_split(
        X_real, y_real, test_size=args.test_size, random_state=42, stratify=y_real if classification else None
    )

    synth_utility_metrics = []
    synth_attack_metrics = []
    synth_trials = []

    print(f"\n--- Training {model_name} (one-time training) ---")
    synthesizer = create_synthesizer(model_name, args, config)
    synthesizer.fit(real_df)

    for trial in range(args.n_runs):
        print(f"\n--- Trial {trial + 1}/{args.n_runs}: Generating and evaluating samples ---")
        synth_data = synthesizer.generate(real_df)
        synth_trials.append(synth_data)

        if config.target_col not in synth_data.columns:
            print(f"Warning: Target column {config.target_col} missing in trial {trial + 1}")
            continue

        synth_eval = remove_evaluation_helpers(remove_identifier(synth_data, config.id_col))
        X_synth = synth_eval.drop(columns=[config.target_col])
        y_synth = synth_eval[config.target_col]

        stats = compute_statistical_metrics(real_df, synth_data, config)
        utility_metrics = train_model(X_synth, y_synth, X_real_test, y_real_test, classification)
        utility_metrics.update(stats)

        real_eval = remove_evaluation_helpers(remove_identifier(real_df, config.id_col))
        attack_metrics = SyntheticDataMetrics.model_inversion_attack(real_eval, synth_eval, config.target_col)

        synth_utility_metrics.append(utility_metrics)
        synth_attack_metrics.append(attack_metrics)

        print(f"\nTrial {trial + 1} Results:")
        print_metric_block("Statistical Metrics:", stats)
        print_metric_block("Utility Metrics:", utility_metrics)
        print_metric_block("Privacy Attack Results:", attack_metrics)

    return synth_utility_metrics, synth_attack_metrics, synth_trials


def print_metric_block(title: str, metrics: Dict[str, object]) -> None:
    """
    Description:
        Print metric information for `print_metric_block`.

    Input:
        title: str; metrics: Dict[str, object].

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    print(title)
    for key, value in metrics.items():
        if value is None:
            continue
        if isinstance(value, (int, float, np.integer, np.floating)):
            print(f"{key}: {float(value):.4f}")
        else:
            print(f"{key}: {value}")


def summarize_runs(metric_runs: Dict[Tuple[str, str], List[Dict[str, object]]]) -> pd.DataFrame:
    """
    Description:
        Summarize results for `summarize_runs`.

    Input:
        metric_runs: Dict[Tuple[str, str], List[Dict[str, object]]].

    Output:
        pd.DataFrame.
    """
    rows = []
    for (dataset, model), runs in metric_runs.items():
        df = pd.DataFrame(runs).select_dtypes(include="number")
        for metric in df.columns:
            rows.append({
                "dataset": dataset,
                "model": model,
                "metric": metric,
                "mean": df[metric].mean(),
                "std": df[metric].std(ddof=0),
            })
    return pd.DataFrame(rows)


def save_results(all_results: List[Dict[str, object]], metric_runs: Dict[Tuple[str, str], List[Dict[str, object]]], output_dir: Path):
    """
    Description:
        Save outputs for `save_results`.

    Input:
        all_results: List[Dict[str, object]]; metric_runs: Dict[Tuple[str, str], List[Dict[str, object]]]; output_dir: Path.

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir = output_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    fd_metrics = []
    stat_sim = []
    privacy_metrics = []
    ml_utility = []

    for result in all_results:
        dataset = result["dataset"]
        model = result["model"]
        utility = result["utility_metrics"]
        attack = result["attack_metrics"]
        utility_pvals = result["utility_p_values"]
        attack_pvals = result["attack_p_values"]

        runs = pd.DataFrame(metric_runs[(dataset, model)])
        numeric_cols = runs.select_dtypes(include="number").columns
        stds = runs[numeric_cols].std().to_dict()

        fd_metrics.append({
            "dataset": dataset,
            "model": model,
            "PearsonCorrDiff": utility.get("PearsonCorrDiff"),
            "PearsonCorrDiff_std": stds.get("PearsonCorrDiff"),
            "PearsonCorrDiff_p": utility_pvals.get("PearsonCorrDiff"),
            "UncertaintyCoeffDiff": utility.get("UncertaintyCoeffDiff"),
            "UncertaintyCoeffDiff_std": stds.get("UncertaintyCoeffDiff"),
            "UncertaintyCoeffDiff_p": utility_pvals.get("UncertaintyCoeffDiff"),
            "CorrelationRatioDiff": utility.get("CorrelationRatioDiff"),
            "CorrelationRatioDiff_std": stds.get("CorrelationRatioDiff"),
            "CorrelationRatioDiff_p": utility_pvals.get("CorrelationRatioDiff"),
        })
        stat_sim.append({
            "dataset": dataset,
            "model": model,
            "JSD": utility.get("JSD"),
            "JSD_std": stds.get("JSD"),
            "JSD_p": utility_pvals.get("JSD"),
            "Wasserstein": utility.get("Wasserstein"),
            "Wasserstein_std": stds.get("Wasserstein"),
            "Wasserstein_p": utility_pvals.get("Wasserstein"),
        })
        privacy_metrics.append({
            "dataset": dataset,
            "model": model,
            "MIA_Accuracy": attack.get("Accuracy"),
            "MIA_Accuracy_std": stds.get("MIA_Accuracy"),
            "MIA_Accuracy_p": attack_pvals.get("Accuracy"),
            "MIA_AUROC": attack.get("AUROC"),
            "MIA_AUROC_std": stds.get("MIA_AUROC"),
            "MIA_AUROC_p": attack_pvals.get("AUROC"),
            "MIA_MSE": attack.get("MSE"),
            "MIA_MSE_std": stds.get("MIA_MSE"),
            "MIA_MSE_p": attack_pvals.get("MSE"),
        })
        ml_utility.append({
            "dataset": dataset,
            "model": model,
            "F1-score": utility.get("F1-score"),
            "F1-score_std": stds.get("F1-score"),
            "F1-score_p": utility_pvals.get("F1-score"),
            "AUROC": utility.get("AUROC"),
            "AUROC_std": stds.get("AUROC"),
            "AUROC_p": utility_pvals.get("AUROC"),
            "AUPRC": utility.get("AUPRC"),
            "AUPRC_std": stds.get("AUPRC"),
            "AUPRC_p": utility_pvals.get("AUPRC"),
            "Accuracy": utility.get("Accuracy"),
            "Accuracy_std": stds.get("Accuracy"),
            "Accuracy_p": utility_pvals.get("Accuracy"),
            "MAPE": utility.get("MAPE"),
            "MAPE_std": stds.get("MAPE"),
            "MAPE_p": utility_pvals.get("MAPE"),
            "R2": utility.get("R2"),
            "R2_std": stds.get("R2"),
            "R2_p": utility_pvals.get("R2"),
            "EVS": utility.get("EVS"),
            "EVS_std": stds.get("EVS"),
            "EVS_p": utility_pvals.get("EVS"),
        })

    metrics = {
        "fd_metrics": fd_metrics,
        "stat_sim": stat_sim,
        "privacy_metrics": privacy_metrics,
        "ml_utility": ml_utility,
    }

    for name, data in metrics.items():
        df = pd.DataFrame(data)
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].round(4)
        csv_path = metrics_dir / f"{name}_with_pvalues.csv"
        df.to_csv(csv_path, index=False)
        print(f"Saved {csv_path}")

    generate_plots_for_metrics(metrics, output_dir)


def save_real_baselines(metrics_dir: Path, real_utility: Dict[str, object], real_attack: Dict[str, object]) -> None:
    """
    Description:
        Save outputs for `save_real_baselines`.

    Input:
        metrics_dir: Path; real_utility: Dict[str, object]; real_attack: Dict[str, object].

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    rows = []
    for group_name, metrics in (("utility", real_utility), ("privacy_attack", real_attack)):
        for metric_name, value in metrics.items():
            rows.append({
                "baseline_group": group_name,
                "metric": metric_name,
                "value": format_report_value(value),
            })

    path = metrics_dir / "real_baselines.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"Saved {path}")


def generate_plots_for_metrics(metrics_dict: Dict[str, List[Dict[str, object]]], output_dir: Path):
    """
    Description:
        Generate outputs for `generate_plots_for_metrics`.

    Input:
        metrics_dict: Dict[str, List[Dict[str, object]]]; output_dir: Path.

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    dataset_colors = {DATASET_NAME: "#1f77b4"}

    for group_name, metric_list in metrics_dict.items():
        df = pd.DataFrame(metric_list)
        metric_cols = [
            col for col in df.columns
            if col not in ["dataset", "model"] and not col.endswith("_p") and not col.endswith("_std")
        ]
        print(f"Plotting metrics from group: {group_name} ({len(metric_cols)} metrics)")

        for metric in metric_cols:
            if metric not in df.columns or not pd.api.types.is_numeric_dtype(df[metric]):
                continue
            std_col = f"{metric}_std"
            plot_df = df[["dataset", "model", metric]].copy()
            plot_df["std"] = df[std_col] if std_col in df.columns else 0.0
            plot_df = plot_df.rename(columns={metric: "value"})

            plt.figure(figsize=(10, 6))
            sns.set(style="whitegrid")
            ax = sns.barplot(data=plot_df, x="model", y="value", hue="dataset", palette=dataset_colors, errorbar=None)

            for i, row in plot_df.reset_index(drop=True).iterrows():
                if pd.notna(row["std"]):
                    ax.errorbar(i, row["value"], yerr=row["std"], fmt="none", ecolor="black", capsize=5)

            ax.set_title(f"{metric} ({group_name})", fontsize=14)
            ax.set_xlabel("Model", fontsize=12)
            ax.set_ylabel(metric, fontsize=12)
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()

            filename = plots_dir / f"{group_name}_{metric}.pdf".replace(" ", "_")
            plt.savefig(filename)
            plt.close()
            print(f"Saved plot: {filename}")

    save_dataset_legend(dataset_colors, plots_dir)


def save_dataset_legend(dataset_colors: Dict[str, str], plots_dir: Path):
    """
    Description:
        Save outputs for `save_dataset_legend`.

    Input:
        dataset_colors: Dict[str, str]; plots_dir: Path.

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    from matplotlib.lines import Line2D

    plt.figure(figsize=(4, 2))
    handles = [
        Line2D([0], [0], marker="o", color=color, linestyle="", markersize=8, label=dataset)
        for dataset, color in dataset_colors.items()
    ]
    plt.legend(handles=handles, title="Dataset", ncol=2, loc="center", frameon=False)
    plt.axis("off")
    filename = plots_dir / "dataset_legend.pdf"
    plt.savefig(filename, bbox_inches="tight")
    plt.close()
    print(f"Saved dataset legend: {filename}")


def format_report_value(value: object) -> str:
    """
    Description:
        Format values for `format_report_value`.

    Input:
        value: object.

    Output:
        str.
    """
    if value is None:
        return ""
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return ""
        return f"{float(value):.4f}"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return str(value)


def dataframe_to_html(df: pd.DataFrame, max_rows: Optional[int] = None) -> str:
    """
    Description:
        Convert a dataframe for `dataframe_to_html`.

    Input:
        df: pd.DataFrame; max_rows: Optional[int].

    Output:
        str.
    """
    if df.empty:
        return "<p class=\"muted\">No rows available.</p>"

    display_df = df.copy()
    if max_rows is not None and len(display_df) > max_rows:
        display_df = display_df.head(max_rows)

    for col in display_df.columns:
        if pd.api.types.is_float_dtype(display_df[col]):
            display_df[col] = display_df[col].map(lambda x: "" if pd.isna(x) else f"{x:.4f}")
        elif pd.api.types.is_integer_dtype(display_df[col]):
            display_df[col] = display_df[col].map(lambda x: "" if pd.isna(x) else str(x))

    table_html = display_df.to_html(index=False, escape=True, classes="result-table")
    if max_rows is not None and len(df) > max_rows:
        table_html += f"<p class=\"muted\">Showing first {max_rows} of {len(df)} rows.</p>"
    return table_html


def report_href(path: Path, base_dir: Optional[Path] = None) -> str:
    """
    Description:
        Build report assets for `report_href`.

    Input:
        path: Path; base_dir: Optional[Path].

    Output:
        str.
    """
    base_dir = base_dir or PROJECT_ROOT
    try:
        rel = Path(os.path.relpath(path.resolve(), base_dir.resolve()))
    except ValueError:
        rel = path.resolve()
    return html.escape(rel.as_posix().replace("\\", "/"))


def csv_section(
    output_dir: Path,
    filename: str,
    title: str,
    max_rows: Optional[int] = None,
    base_dir: Optional[Path] = None,
) -> str:
    """
    Description:
        Build an HTML CSV section for `csv_section`.

    Input:
        output_dir: Path; filename: str; title: str; max_rows: Optional[int]; base_dir: Optional[Path].

    Output:
        str.
    """
    path = output_dir / filename
    if not path.exists():
        return f"<section><h2>{html.escape(title)}</h2><p class=\"muted\">File not generated: {html.escape(filename)}</p></section>"

    df = pd.read_csv(path)
    href = report_href(path, base_dir)
    return (
        f"<section><h2>{html.escape(title)}</h2>"
        f"<p><a href=\"{href}\">{html.escape(path.relative_to(output_dir).as_posix())}</a></p>"
        f"{dataframe_to_html(df, max_rows=max_rows)}</section>"
    )


def key_value_table(rows: Dict[str, object]) -> str:
    """
    Description:
        Build key-value display data for `key_value_table`.

    Input:
        rows: Dict[str, object].

    Output:
        str.
    """
    body = []
    for key, value in rows.items():
        body.append(
            "<tr>"
            f"<th>{html.escape(str(key))}</th>"
            f"<td>{html.escape(format_report_value(value))}</td>"
            "</tr>"
        )
    return "<table class=\"kv-table\"><tbody>" + "".join(body) + "</tbody></table>"


def model_status_summary(metrics_by_run: pd.DataFrame) -> pd.DataFrame:
    """
    Description:
        Run model evaluation for `model_status_summary`.

    Input:
        metrics_by_run: pd.DataFrame.

    Output:
        pd.DataFrame.
    """
    if metrics_by_run.empty or "model" not in metrics_by_run.columns:
        return pd.DataFrame()

    rows = []
    for model_name, group in metrics_by_run.groupby("model", dropna=False):
        status_counts = group["status"].value_counts().to_dict() if "status" in group.columns else {}
        row = {
            "model": model_name,
            "trials": len(group),
            "ok": status_counts.get("ok", 0),
            "failed": status_counts.get("failed", 0),
        }
        for metric in ["Accuracy", "F1-score", "PearsonCorrDiff", "Wasserstein", "JSD", "attack_Accuracy"]:
            if metric in group.columns:
                row[f"{metric}_mean"] = pd.to_numeric(group[metric], errors="coerce").mean()
        if "error" in group.columns:
            errors = sorted(set(group["error"].dropna().astype(str)))
            row["errors"] = " | ".join(errors)
        rows.append(row)
    return pd.DataFrame(rows)


def file_list_html(output_dir: Path, pattern: str, title: str, base_dir: Optional[Path] = None) -> str:
    """
    Description:
        Return file information for `file_list_html`.

    Input:
        output_dir: Path; pattern: str; title: str; base_dir: Optional[Path].

    Output:
        str.
    """
    files = sorted(output_dir.glob(pattern))
    if not files:
        return f"<section><h2>{html.escape(title)}</h2><p class=\"muted\">No files found.</p></section>"

    items = []
    for path in files:
        rel = path.relative_to(output_dir).as_posix()
        size_kb = path.stat().st_size / 1024
        items.append(
            f"<li><a href=\"{report_href(path, base_dir)}\">{html.escape(rel)}</a> "
            f"<span class=\"muted\">({size_kb:.1f} KB)</span></li>"
        )
    return f"<section><h2>{html.escape(title)}</h2><ul class=\"file-list\">{''.join(items)}</ul></section>"


def output_file_index_html(output_dir: Path, base_dir: Optional[Path] = None) -> str:
    """
    Description:
        Build output file index data for `output_file_index_html`.

    Input:
        output_dir: Path; base_dir: Optional[Path].

    Output:
        str.
    """
    files = sorted(path for path in output_dir.rglob("*") if path.is_file())
    if not files:
        return "<section><h2>Output File Index</h2><p class=\"muted\">No result files were found.</p></section>"

    rows = []
    for path in files:
        rel = path.relative_to(output_dir).as_posix()
        rows.append({
            "folder": path.parent.relative_to(output_dir).as_posix(),
            "file": f"<a href=\"{report_href(path, base_dir)}\">{html.escape(path.name)}</a>",
            "size_kb": path.stat().st_size / 1024,
            "relative_path": rel,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["size_kb"] = df["size_kb"].map(lambda value: f"{value:.1f}")
    table_html = df.to_html(index=False, escape=False, classes="result-table")
    return f"<section><h2>Output File Index</h2>{table_html}</section>"


def synthetic_preview_sections(output_dir: Path, base_dir: Optional[Path] = None) -> str:
    """
    Description:
        Run the helper for `synthetic_preview_sections`.

    Input:
        output_dir: Path; base_dir: Optional[Path].

    Output:
        str.
    """
    sections = []
    for path in sorted((output_dir / "synthetic" / "sessions").glob("synthetic_sessions_*.csv")):
        model_name = path.stem.replace("synthetic_sessions_", "")
        df = pd.read_csv(path)
        href = report_href(path, base_dir)
        sections.append(
            f"<section><h2>Synthetic Sessions: {html.escape(model_name)}</h2>"
            f"<p><a href=\"{href}\">{html.escape(path.name)}</a> "
            f"<span class=\"muted\">Rows: {len(df)}, columns: {len(df.columns)}</span></p>"
            f"{dataframe_to_html(df, max_rows=10)}</section>"
        )
    if not sections:
        return "<section><h2>Synthetic Sessions</h2><p class=\"muted\">No synthetic session files were generated.</p></section>"
    return "".join(sections)


def baseline_dict_from_csv(baseline_df: pd.DataFrame, group_name: str, fallback: Dict[str, object]) -> Dict[str, object]:
    """
    Description:
        Build baseline values for `baseline_dict_from_csv`.

    Input:
        baseline_df: pd.DataFrame; group_name: str; fallback: Dict[str, object].

    Output:
        Dict[str, object].
    """
    if baseline_df.empty or not {"baseline_group", "metric", "value"}.issubset(baseline_df.columns):
        return fallback

    group_df = baseline_df.loc[baseline_df["baseline_group"] == group_name]
    if group_df.empty:
        return fallback

    return {str(row["metric"]): row["value"] for _, row in group_df.iterrows()}


def run_log_section(log_path: Optional[Path], base_dir: Path) -> str:
    """
    Description:
        Run processing for `run_log_section`.

    Input:
        log_path: Optional[Path]; base_dir: Path.

    Output:
        str.
    """
    logs_dir = PROJECT_ROOT / "logs"
    latest_logs = sorted(logs_dir.glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True) if logs_dir.exists() else []
    items = []
    if log_path is not None:
        resolved_log = (PROJECT_ROOT / log_path).resolve() if not log_path.is_absolute() else log_path.resolve()
        if resolved_log.exists():
            items.append(
                f"<li><strong>Current run:</strong> <a href=\"{report_href(resolved_log, base_dir)}\">"
                f"{html.escape(resolved_log.name)}</a></li>"
            )

    for path in latest_logs[:10]:
        if log_path is not None:
            resolved_log = (PROJECT_ROOT / log_path).resolve() if not log_path.is_absolute() else log_path.resolve()
            if path.resolve() == resolved_log:
                continue
        items.append(
            f"<li><a href=\"{report_href(path, base_dir)}\">{html.escape(path.name)}</a> "
            f"<span class=\"muted\">({path.stat().st_size / 1024:.1f} KB)</span></li>"
        )

    if not items:
        return "<section><h2>Run Logs</h2><p class=\"muted\">No log files were found.</p></section>"
    return f"<section><h2>Run Logs</h2><ul class=\"file-list\">{''.join(items)}</ul></section>"


def metric_interpretation_html() -> str:
    """
    Description:
        Return metric values for `metric_interpretation_html`.

    Input:
        None.

    Output:
        str.
    """
    rows = [
        (
            "PearsonCorrDiff, UncertaintyCoeffDiff, CorrelationRatioDiff",
            "Lower is better",
            "< 0.05 very close; 0.05-0.15 moderate; > 0.15 should be reviewed",
            "Measures whether relationships between columns are preserved.",
        ),
        (
            "Wasserstein",
            "Lower is better",
            "< 0.05 close; 0.05-0.15 moderate shift; > 0.15 larger distribution shift",
            "Calculated on normalized numerical columns.",
        ),
        (
            "JSD",
            "Lower is better",
            "< 0.05 close; 0.05-0.15 moderate; > 0.15 categorical distribution mismatch",
            "Compares categorical distributions. Values are bounded, with 0 indicating identical distributions.",
        ),
        (
            "Accuracy, F1-score, AUROC, AUPRC",
            "Close to the real-data baseline",
            "Within about 0.05-0.10 of the real baseline is usually acceptable; drops above 0.15 are concerning",
            "For utility, synthetic data should support similar predictive performance, not necessarily maximize every score.",
        ),
        (
            "MIA Accuracy / MIA AUROC",
            "Lower is safer",
            "MIA AUROC near 0.50 is good; > 0.70 can indicate privacy risk. MIA Accuracy should be lower than the real baseline.",
            "High attack performance suggests the synthetic data may reveal too much about the real data.",
        ),
        (
            "p-values",
            "Depends on metric family",
            "Utility/statistical p >= 0.05 is preferred; privacy p < 0.05 is useful only when synthetic data is safer",
            "Use p-values together with metric direction and magnitude, not alone.",
        ),
    ]
    body = []
    for metric, direction, guide, note in rows:
        body.append(
            "<tr>"
            f"<td>{html.escape(metric)}</td>"
            f"<td>{html.escape(direction)}</td>"
            f"<td>{html.escape(guide)}</td>"
            f"<td>{html.escape(note)}</td>"
            "</tr>"
        )
    return (
        "<section>"
        "<h2>Interpretation Guide</h2>"
        "<p class=\"muted\">These ranges are practical screening guides for this benchmark. Final interpretation should consider the domain, sample size, and the real-data baseline.</p>"
        "<table class=\"result-table\"><thead><tr><th>Metric</th><th>Preferred Direction</th><th>Simple Range Guide</th><th>Notes</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
        "</section>"
    )


def add_anka_rows(rows: List[Dict[str, str]], section: str, values: Dict[str, object]) -> None:
    """
    Description:
        Add values for `add_anka_rows`.

    Input:
        rows: List[Dict[str, str]]; section: str; values: Dict[str, object].

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    for key, value in values.items():
        rows.append({
            "section": section,
            "item": str(key),
            "value": format_report_value(value),
            "note": "",
        })


def build_anka_report_objects(
    config_rows: Dict[str, object],
    saved_utility: Dict[str, object],
    saved_attack: Dict[str, object],
    model_summary: pd.DataFrame,
    metrics_summary: pd.DataFrame,
    generated_at: str,
) -> Tuple[Dict[str, object], Dict[str, object]]:
    """
    Description:
        Build data for `build_anka_report_objects`.

    Input:
        config_rows: Dict[str, object]; saved_utility: Dict[str, object]; saved_attack: Dict[str, object]; model_summary: pd.DataFrame; metrics_summary: pd.DataFrame; generated_at: str.

    Output:
        Tuple[Dict[str, object], Dict[str, object]].
    """
    summary_rows: List[Dict[str, str]] = []
    add_anka_rows(summary_rows, "Run Configuration", config_rows)
    add_anka_rows(summary_rows, "Real Data Utility Baseline", saved_utility)
    add_anka_rows(summary_rows, "Real Data Privacy Baseline", saved_attack)

    if not model_summary.empty:
        for _, row in model_summary.iterrows():
            model_name = format_report_value(row.get("model", ""))
            value_parts = []
            for col in ["trials", "ok", "failed", "F1-score_mean", "Accuracy_mean", "attack_Accuracy_mean"]:
                if col in row and pd.notna(row[col]):
                    value_parts.append(f"{col}: {format_report_value(row[col])}")
            summary_rows.append({
                "section": "Model Summary",
                "item": model_name,
                "value": "; ".join(value_parts),
                "note": format_report_value(row.get("errors", "")),
            })

    if not metrics_summary.empty:
        for _, row in metrics_summary.iterrows():
            model_name = format_report_value(row.get("model", ""))
            metric_name = format_report_value(row.get("metric", ""))
            summary_rows.append({
                "section": "Metric Summary",
                "item": f"{model_name} - {metric_name}",
                "value": f"mean: {format_report_value(row.get('mean', ''))}; std: {format_report_value(row.get('std', ''))}",
                "note": "",
            })

    data = {
        "reportTitle": "Syn Sport Synthetic Data Benchmark",
        "subtitle": "Sport synthetic data pipeline",
        "dataset": format_report_value(config_rows.get("Dataset", "")),
        "target": format_report_value(config_rows.get("Target", "")),
        "models": format_report_value(config_rows.get("Models", "")),
        "generatedAt": generated_at,
        "summaryRows": summary_rows,
        "footer1": "Generated by synSPORT",
        "footer2": "Generated from saved pipeline outputs",
    }

    layout = {
        "width": 860,
        "headerSection": {
            "height": 112,
            "items": [
                {"text": "Syn Sport Synthetic Data Benchmark", "binding": "reportTitle", "x": 18, "y": 10, "width": 520, "height": 22},
                {"text": "Sport synthetic data pipeline", "binding": "subtitle", "x": 18, "y": 36, "width": 520, "height": 18},
                {"text": "Dataset", "x": 600, "y": 10, "width": 80, "height": 18},
                {"binding": "dataset", "x": 690, "y": 10, "width": 140, "height": 18},
                {"text": "Target", "x": 600, "y": 34, "width": 80, "height": 18},
                {"binding": "target", "x": 690, "y": 34, "width": 140, "height": 18},
                {"text": "Models", "x": 18, "y": 66, "width": 70, "height": 18},
                {"binding": "models", "x": 92, "y": 66, "width": 500, "height": 18},
                {"text": "Section", "x": 18, "y": 88, "width": 160, "height": 18},
                {"text": "Item", "x": 188, "y": 88, "width": 230, "height": 18},
                {"text": "Value", "x": 428, "y": 88, "width": 250, "height": 18},
                {"text": "Note", "x": 688, "y": 88, "width": 150, "height": 18},
            ],
        },
        "contentSection": {
            "height": 26,
            "binding": "summaryRows",
            "items": [
                {"binding": "section", "x": 18, "y": 4, "width": 160, "height": 18},
                {"binding": "item", "x": 188, "y": 4, "width": 230, "height": 18},
                {"binding": "value", "x": 428, "y": 4, "width": 250, "height": 18},
                {"binding": "note", "x": 688, "y": 4, "width": 150, "height": 18},
            ],
        },
        "footerSection": {
            "height": 42,
            "items": [
                {"binding": "footer1", "x": 18, "y": 10, "width": 260, "height": 18},
                {"binding": "footer2", "x": 300, "y": 10, "width": 320, "height": 18},
                {"binding": "generatedAt", "x": 650, "y": 10, "width": 180, "height": 18},
            ],
        },
    }
    return data, layout


def report_styles() -> str:
    """
    Description:
        Build report assets for `report_styles`.

    Input:
        None.

    Output:
        str.
    """
    return """\
:root {
  color-scheme: dark;
  --ink: #111827;
  --muted: #5f6c7b;
  --line: #d8dee9;
  --panel: #ffffff;
  --page: #17181b;
  --nav: #222426;
  --hero: #28c3a5;
  --accent: #0f766e;
  --accent-soft: #e5fbf6;
  --accent-strong: #0c5f59;
  --good: #10b981;
  --warn: #a16207;
}
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  font-family: Arial, Helvetica, sans-serif;
  color: #f8fafc;
  background: var(--page);
  line-height: 1.45;
}
.shell {
  min-height: 100vh;
}
.site-nav {
  height: 88px;
  display: flex;
  align-items: center;
  gap: 34px;
  padding: 0 34px;
  background: var(--nav);
  color: #f8fafc;
}
.brand {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 24px;
  font-weight: 700;
  white-space: nowrap;
}
.brand-icon {
  width: 38px;
  height: 38px;
  display: inline-grid;
  place-items: center;
  border: 2px solid #111827;
  border-radius: 6px;
  background: #2f3136;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.12);
}
.brand-icon::before {
  content: "";
  width: 19px;
  height: 24px;
  border: 2px solid #111827;
  border-radius: 2px;
  background:
    linear-gradient(#111827, #111827) 4px 6px / 11px 2px no-repeat,
    linear-gradient(#111827, #111827) 4px 11px / 11px 2px no-repeat,
    linear-gradient(#111827, #111827) 4px 16px / 8px 2px no-repeat,
    #3d4046;
}
.nav-tabs {
  display: flex;
  align-items: center;
  gap: 22px;
  flex: 1;
}
.nav-link {
  margin-left: auto;
  color: #e5e7eb;
  font-size: 18px;
  font-weight: 700;
}
.hero {
  min-height: 310px;
  display: grid;
  place-items: center;
  text-align: center;
  padding: 54px 42px;
  color: #020617;
  background: var(--hero);
}
.eyebrow {
  margin: 0 0 8px;
  color: #053b35;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}
h1 {
  margin: 0 0 8px;
  font-size: 64px;
  line-height: 1.05;
  font-weight: 700;
}
h2 {
  margin: 0 0 12px;
  font-size: 18px;
  color: var(--accent);
  border-bottom: 1px solid var(--line);
  padding-bottom: 7px;
}
h3 {
  margin: 0 0 8px;
  font-size: 15px;
}
main {
  padding: 58px 42px 56px;
  max-width: 1440px;
  margin: 0 auto;
}
.muted {
  color: var(--muted);
  font-size: 13px;
}
.tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.tab-button,
.subtab-button {
  appearance: none;
  border: 0;
  background: transparent;
  color: #e5e7eb;
  padding: 10px 0;
  border-radius: 0;
  font-size: 22px;
  font-weight: 700;
  cursor: pointer;
}
.tab-button.active,
.subtab-button.active {
  background: transparent;
  color: #ffffff;
  font-weight: 700;
}
.tab-panel,
.subtab-panel {
  display: none;
}
.tab-panel.active,
.subtab-panel.active {
  display: block;
}
.subtabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 0 0 16px;
}
.subtab-button {
  border: 1px solid #3b3d42;
  border-radius: 6px;
  background: #222426;
  color: #e5e7eb;
  padding: 9px 13px;
  font-size: 14px;
}
.subtab-button.active {
  border-color: var(--hero);
  color: #061311;
  background: var(--hero);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 18px;
  margin-bottom: 24px;
}
.panel,
.anka-panel {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 18px;
  background: var(--panel);
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
  margin-bottom: 24px;
}
.note {
  border-left: 4px solid var(--accent);
  background: var(--accent-soft);
  padding: 12px 14px;
  margin: 0 0 22px;
  font-size: 14px;
}
.callout {
  border: 1px solid var(--line);
  border-left: 4px solid var(--good);
  background: #ffffff;
  color: var(--ink);
  padding: 14px 16px;
  border-radius: 6px;
  margin-bottom: 18px;
}
.feature-visual {
  height: 150px;
  display: grid;
  place-items: center;
  margin-bottom: 18px;
  border-radius: 6px;
  background: #1f2030;
  overflow: hidden;
}
.feature-visual svg {
  width: min(220px, 80%);
  height: 120px;
}
.report-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 0 0 12px;
}
.report-actions button {
  appearance: none;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #ffffff;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}
.report-actions button:hover {
  background: var(--accent-strong);
}
.section-heading {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
  margin-bottom: 14px;
}
.section-heading h2 {
  min-width: 220px;
  margin-bottom: 0;
}
.ankareport-viewer {
  min-height: 360px;
  overflow-x: auto;
  padding: 12px;
  border: 1px solid var(--line);
  background: #f8fafc;
}
.ankareport-fallback:empty {
  display: none;
}
.fallback-report {
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
  background: #ffffff;
}
.fallback-header {
  padding: 16px;
  background: var(--accent-soft);
  border-bottom: 1px solid var(--line);
}
table {
  border-collapse: collapse;
  width: 100%;
  font-size: 13px;
}
th,
td {
  border: 1px solid var(--line);
  padding: 7px 8px;
  vertical-align: top;
  text-align: left;
}
th {
  background: #eef2f7;
  font-weight: 700;
}
.kv-table th {
  width: 220px;
}
.result-table {
  display: block;
  overflow-x: auto;
  white-space: nowrap;
}
.file-list {
  columns: 2;
  padding-left: 20px;
}
a {
  color: var(--accent);
  text-decoration: none;
}
a:hover {
  text-decoration: underline;
}
ol,
ul {
  padding-left: 22px;
}
li {
  margin-bottom: 6px;
}
@media (max-width: 760px) {
  .site-nav {
    height: auto;
    align-items: flex-start;
    flex-direction: column;
    gap: 14px;
    padding: 18px;
  }
  .nav-tabs {
    width: 100%;
  }
  .nav-link {
    margin-left: 0;
  }
  .hero,
  main {
    padding-left: 18px;
    padding-right: 18px;
  }
  h1 {
    font-size: 42px;
  }
  .file-list {
    columns: 1;
  }
  .section-heading {
    display: block;
  }
}
"""


def report_script() -> str:
    """
    Description:
        Build report assets for `report_script`.

    Input:
        None.

    Output:
        str.
    """
    return """\
(function () {
  const report = window.SYN_SPORT_REPORT || {};
  const fragments = report.fragments || {};

  document.querySelectorAll("[data-fragment]").forEach((node) => {
    const name = node.getAttribute("data-fragment");
    node.innerHTML = fragments[name] || "<p class=\\"muted\\">No content was generated for this section.</p>";
  });

  let ankaRenderer = null;

  function activateTab(tabId) {
    document.querySelectorAll(".tab-button").forEach((button) => {
      button.classList.toggle("active", button.dataset.tab === tabId);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === tabId);
    });
  }

  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
      activateTab(button.dataset.tab);
      history.replaceState(null, "", "#" + button.dataset.tab);
    });
  });

  const initialTab = window.location.hash.replace("#", "");
  if (initialTab && document.getElementById(initialTab)) {
    activateTab(initialTab);
  }

  document.querySelectorAll(".subtab-button").forEach((button) => {
    button.addEventListener("click", () => {
      const group = button.dataset.group;
      const target = button.dataset.subtab;
      document.querySelectorAll(`.subtab-button[data-group="${group}"]`).forEach((item) => {
        item.classList.toggle("active", item.dataset.subtab === target);
      });
      document.querySelectorAll(`.subtab-panel[data-group="${group}"]`).forEach((panel) => {
        panel.classList.toggle("active", panel.id === target);
      });
    });
  });

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function renderAnkaFallback(message) {
    const fallback = document.getElementById("ankareport-fallback");
    const viewer = document.getElementById("ankareport-viewer");
    if (!fallback) {
      return;
    }
    if (viewer) {
      viewer.style.display = "none";
    }
    const data = report.ankaData || {};
    const rows = data.summaryRows || [];
    const tableRows = rows.map((row) => {
      return "<tr>"
        + "<td>" + escapeHtml(row.section || "") + "</td>"
        + "<td>" + escapeHtml(row.item || "") + "</td>"
        + "<td>" + escapeHtml(row.value || "") + "</td>"
        + "<td>" + escapeHtml(row.note || "") + "</td>"
        + "</tr>";
    }).join("");
    fallback.innerHTML = ""
      + '<div class="fallback-report">'
      + '<div class="fallback-header"><h3>' + escapeHtml(data.reportTitle || "Report") + '</h3>'
      + '<p class="muted">' + escapeHtml(message || "Static fallback report.") + '</p></div>'
      + '<table class="result-table"><thead><tr><th>Section</th><th>Item</th><th>Value</th><th>Note</th></tr></thead>'
      + '<tbody>' + tableRows + '</tbody></table></div>';
  }

  function renderAnkaReport() {
    const viewer = document.getElementById("ankareport-viewer");
    if (!viewer) {
      return;
    }
    if (window.AnkaReport && typeof window.AnkaReport.render === "function") {
      try {
        viewer.style.display = "";
        const fallback = document.getElementById("ankareport-fallback");
        if (fallback) {
          fallback.innerHTML = "";
        }
        ankaRenderer = window.AnkaReport.render({
          element: viewer,
          layout: report.ankaLayout,
          data: report.ankaData,
        });
        return;
      } catch (error) {
        renderAnkaFallback("Report viewer could not render this layout: " + error.message);
        return;
      }
    }
    renderAnkaFallback("Report viewer was not available; showing the same layout data as a static table.");
  }

  renderAnkaReport();

  const exportPdfButton = document.getElementById("export-to-pdf-button");
  if (exportPdfButton) {
    exportPdfButton.addEventListener("click", () => {
      if (ankaRenderer && typeof ankaRenderer.exportToPdf === "function") {
        ankaRenderer.exportToPdf("synSPORT_report.pdf");
      }
    });
  }

  const exportXlsxButton = document.getElementById("export-to-xlsx-button");
  if (exportXlsxButton) {
    exportXlsxButton.addEventListener("click", () => {
      if (ankaRenderer && typeof ankaRenderer.exportToXlsx === "function") {
        ankaRenderer.exportToXlsx("synSPORT_report.xlsx");
      }
    });
  }
})();
"""


def copy_anka_assets(report_dir: Path) -> None:
    """
    Description:
        Copy assets for `copy_anka_assets`.

    Input:
        report_dir: Path.

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    source_dir = PROJECT_ROOT / "vendor" / "ankareport-source" / "dist"
    vendor_dir = report_dir / "assets" / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)

    for filename in ("ankareport.js", "ankareport.css"):
        source = source_dir / filename
        destination = vendor_dir / filename
        if source.exists():
            shutil.copy2(source, destination)
        elif not destination.exists():
            raise FileNotFoundError(f"Missing local report asset: {filename}")


def write_static_report_assets(report_dir: Path, payload: Dict[str, object]) -> None:
    """
    Description:
        Write outputs for `write_static_report_assets`.

    Input:
        report_dir: Path; payload: Dict[str, object].

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    assets_dir = report_dir / "assets"
    data_dir = report_dir / "data"
    assets_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    copy_anka_assets(report_dir)
    (assets_dir / "report.css").write_text(report_styles(), encoding="utf-8")
    (assets_dir / "report.js").write_text(report_script(), encoding="utf-8")
    data_json = json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")
    (data_dir / "report-data.js").write_text(f"window.SYN_SPORT_REPORT = {data_json};\n", encoding="utf-8")


def generate_html_report(
    output_dir: Path,
    args: argparse.Namespace,
    config: SportDataConfig,
    source_rows: int,
    clean_rows: int,
    model_names: List[str],
    real_utility: Dict[str, object],
    real_attack: Dict[str, object],
) -> Path:
    """
    Description:
        Generate outputs for `generate_html_report`.

    Input:
        output_dir: Path; args: argparse.Namespace; config: SportDataConfig; source_rows: int; clean_rows: int; model_names: List[str]; real_utility: Dict[str, object]; real_attack: Dict[str, object].

    Output:
        Path.
    """
    metrics_by_run_path = output_dir / "metrics" / "metrics_by_run.csv"
    metrics_summary_path = output_dir / "metrics" / "metrics_summary.csv"
    baseline_path = output_dir / "metrics" / "real_baselines.csv"
    metrics_by_run = pd.read_csv(metrics_by_run_path) if metrics_by_run_path.exists() else pd.DataFrame()
    metrics_summary = pd.read_csv(metrics_summary_path) if metrics_summary_path.exists() else pd.DataFrame()
    baseline_df = pd.read_csv(baseline_path) if baseline_path.exists() else pd.DataFrame()
    model_summary = model_status_summary(metrics_by_run)
    saved_utility = baseline_dict_from_csv(baseline_df, "utility", real_utility)
    saved_attack = baseline_dict_from_csv(baseline_df, "privacy_attack", real_attack)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_dir = PROJECT_ROOT / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "index.html"

    config_rows = {
        "Dataset": DATASET_NAME,
        "Dataset path": Path(args.dataset_path).resolve(),
        "Results folder": output_dir.resolve(),
        "Report folder": report_dir.resolve(),
        "Rows used": source_rows,
        "Clean rows": clean_rows,
        "Target": config.target_col,
        "Task": config.task_type,
        "Models": ", ".join(model_names),
        "Epochs": args.epochs,
        "Runs / generated trials": args.n_runs,
        "Sessions per person": args.sessions_per_person,
        "Batch size": args.batch_size,
        "TabSyn steps": args.tabsyn_steps,
        "Epsilon": args.epsilon,
        "Delta": args.delta,
        "DPCTGAN epsilon": args.dp_epsilon if args.dp_epsilon is not None else args.epsilon,
        "DPCTGAN delta": args.dp_delta if args.dp_delta is not None else args.delta,
        "PATEGAN epsilon": args.pate_epsilon if args.pate_epsilon is not None else args.epsilon,
        "PATEGAN delta": args.pate_delta if args.pate_delta is not None else args.delta,
        "Run log": args.log_path if getattr(args, "log_path", None) else "",
        "Generated at": generated_at,
    }

    anka_data, anka_layout = build_anka_report_objects(
        config_rows=config_rows,
        saved_utility=saved_utility,
        saved_attack=saved_attack,
        model_summary=model_summary,
        metrics_summary=metrics_summary,
        generated_at=generated_at,
    )

    benchmark_summary_html = f"""
      <section class="anka-panel">
        <div class="section-heading">
          <h2>Report Viewer</h2>
          <p class="muted">This summary is rendered from local report assets using saved pipeline outputs.</p>
        </div>
        <div class="report-actions">
          <button id="export-to-pdf-button" type="button">Export To PDF</button>
          <button id="export-to-xlsx-button" type="button">Export To XLSX</button>
        </div>
        <div id="ankareport-viewer" class="ankareport-viewer"></div>
        <div id="ankareport-fallback" class="ankareport-fallback"></div>
      </section>
      <div class="grid">
        <section class="panel">
          <h2>Run Configuration</h2>
          {key_value_table(config_rows)}
        </section>
        <section class="panel">
          <h2>Real Data Utility Baseline</h2>
          {key_value_table(saved_utility)}
        </section>
        <section class="panel">
          <h2>Real Data Privacy Baseline</h2>
          {key_value_table(saved_attack)}
        </section>
      </div>
      <section>
        <h2>Model Summary</h2>
        {dataframe_to_html(model_summary)}
      </section>
      <section>
        <h2>Metrics Summary</h2>
        {dataframe_to_html(metrics_summary)}
      </section>
    """

    metrics_html = "".join([
        csv_section(output_dir, "metrics/real_baselines.csv", "Real Data Baselines", base_dir=report_dir),
        csv_section(output_dir, "metrics/fd_metrics_with_pvalues.csv", "Feature Dependence Metrics", base_dir=report_dir),
        csv_section(output_dir, "metrics/stat_sim_with_pvalues.csv", "Statistical Similarity Metrics", base_dir=report_dir),
        csv_section(output_dir, "metrics/privacy_metrics_with_pvalues.csv", "Privacy Metrics", base_dir=report_dir),
        csv_section(output_dir, "metrics/ml_utility_with_pvalues.csv", "Machine Learning Utility Metrics", base_dir=report_dir),
        csv_section(output_dir, "metrics/metrics_by_run.csv", "Metrics By Generated Trial", base_dir=report_dir),
        csv_section(output_dir, "metrics/metrics_summary.csv", "Metrics Summary CSV", base_dir=report_dir),
    ])

    synthetic_html = "".join([
        synthetic_preview_sections(output_dir, base_dir=report_dir),
        file_list_html(output_dir, "synthetic/trials/**/*.csv", "Synthetic Trial Files", base_dir=report_dir),
    ])

    files_html = "".join([
        output_file_index_html(output_dir, base_dir=report_dir),
        file_list_html(output_dir, "config/*.json", "Configuration Files", base_dir=report_dir),
        file_list_html(output_dir, "plots/*.pdf", "Generated Plots", base_dir=report_dir),
        run_log_section(getattr(args, "log_path", None), report_dir),
    ])

    payload = {
        "metadata": {
            "title": "Syn Sport Synthetic Data Benchmark",
            "subtitle": "Static report generated from saved benchmark outputs",
            "dataset": DATASET_NAME,
            "outputDir": output_dir.as_posix(),
            "generatedAt": generated_at,
        },
        "ankaData": anka_data,
        "ankaLayout": anka_layout,
        "fragments": {
            "benchmark-summary": benchmark_summary_html,
            "metric-guide": metric_interpretation_html(),
            "metrics": metrics_html,
            "synthetic": synthetic_html,
            "files": files_html,
        },
    }
    write_static_report_assets(report_dir, payload)

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Syn Sport Benchmark Report</title>
  <link rel="stylesheet" href="assets/vendor/ankareport.css">
  <link rel="stylesheet" href="assets/report.css">
</head>
<body>
  <div class="shell">
    <header class="site-nav">
      <div class="brand"><span class="brand-icon" aria-hidden="true"></span><span>Syn Sport</span></div>
      <nav class="nav-tabs" aria-label="Website sections">
        <button class="tab-button active" type="button" data-tab="overview">Overview</button>
        <button class="tab-button" type="button" data-tab="synthetic-report">Synthetic</button>
      </nav>
    </header>
    <header class="hero">
      <p class="eyebrow">Syn Sport Report</p>
      <h1>Sport Synthetic Data Benchmark</h1>
      <p>Static website for generating and evaluating synthetic sport sessions.</p>
    </header>
    <main>
      <section id="overview" class="tab-panel active">
        <div class="callout">
          <h2>Project Purpose</h2>
          <p>This project generates synthetic sport sessions from <code>data/tabular.csv</code>. The aim is to generate multiple realistic synthetic training sessions per athlete while preserving person-level fields for downstream analysis.</p>
        </div>
        <div class="grid">
          <section class="panel">
            <div class="feature-visual" aria-hidden="true">
              <svg viewBox="0 0 240 140" role="img">
                <circle cx="75" cy="72" r="48" fill="#494866"/>
                <path d="M22 118h186" stroke="#5c5a82" stroke-width="7" stroke-linecap="round"/>
                <path d="M42 112l32-70 31 70z" fill="#f8fafc"/>
                <path d="M88 112l34-56 39 56z" fill="#e5e7eb"/>
                <path d="M146 112l25-42 36 42z" fill="#f8fafc"/>
                <rect x="75" y="91" width="36" height="27" rx="7" fill="#22c55e"/>
                <circle cx="88" cy="88" r="4" fill="#22c55e"/>
                <circle cx="101" cy="88" r="4" fill="#22c55e"/>
              </svg>
            </div>
            <h2>Data Adaptation</h2>
            <p>The pipeline treats athlete identity, age, gender, sport type, and training experience as static attributes, then creates repeated synthetic session records using model-generated session-level measurements.</p>
          </section>
          <section class="panel">
            <div class="feature-visual" aria-hidden="true">
              <svg viewBox="0 0 240 140" role="img">
                <circle cx="82" cy="70" r="50" fill="#f4f4f5"/>
                <rect x="52" y="44" width="112" height="76" rx="4" fill="#454255"/>
                <rect x="66" y="60" width="52" height="42" fill="#737373"/>
                <rect x="132" y="68" width="64" height="6" rx="2" fill="#22c55e"/>
                <rect x="132" y="84" width="58" height="6" rx="2" fill="#22c55e"/>
                <rect x="132" y="100" width="70" height="6" rx="2" fill="#22c55e"/>
                <circle cx="178" cy="48" r="22" fill="#22c55e"/>
              </svg>
            </div>
            <h2>Study Alignment</h2>
            <p>The scripts keep the original benchmark approach: train synthetic generators, sample repeated trials, compare fidelity, evaluate predictive utility, estimate privacy risk, and save all outputs for review.</p>
          </section>
          <section class="panel">
            <div class="feature-visual" aria-hidden="true">
              <svg viewBox="0 0 240 140" role="img">
                <path d="M52 34c27 14 57 3 84 0 39-4 62 7 62 38 0 34-24 50-73 50H54c-25 0-38-17-32-42 5-23 9-57 30-46z" fill="#f4f4f5"/>
                <rect x="55" y="70" width="46" height="35" fill="#444052"/>
                <rect x="109" y="64" width="46" height="41" fill="#444052"/>
                <rect x="163" y="70" width="46" height="35" fill="#444052"/>
                <circle cx="137" cy="61" r="13" fill="#f97379"/>
                <path d="M121 102c3-27 32-27 35 0" fill="#394056"/>
                <rect x="67" y="83" width="20" height="15" rx="3" fill="#22c55e"/>
                <path d="M176 80l9 14 9-14" stroke="#38bdf8" stroke-width="4" fill="none"/>
              </svg>
            </div>
            <h2>Report Direction</h2>
            <p>This static report is organized so new tabs and subtabs can be added progressively without changing the model-running workflow.</p>
          </section>
        </div>
        <div class="grid">
          <section class="panel">
            <h2>Report Scope</h2>
            <p>The report summarizes one benchmark run. It is built after all models finish and reads from the saved metrics, synthetic CSVs, plots, configuration, and logs.</p>
          </section>
          <section class="panel">
            <h2>Benchmark Workflow</h2>
            <ol>
              <li>Load and clean the sport dataset.</li>
              <li>Compute the real-data utility and privacy baselines.</li>
              <li>Train each selected generator once.</li>
              <li>Generate repeated synthetic trials and synthetic sessions per athlete.</li>
              <li>Save metrics, plots, generated data, configuration, and terminal logs.</li>
              <li>Build this static report from the saved outputs.</li>
            </ol>
          </section>
          <section class="panel">
            <h2>Reading The Report</h2>
            <p>Open the Synthetic tab for the Anka-rendered report summary, metric interpretation guide, full metric tables, generated records, output files, plots, and logs.</p>
          </section>
        </div>
      </section>

      <section id="synthetic-report" class="tab-panel">
        <div class="subtabs" aria-label="Synthetic report sections">
          <button class="subtab-button active" type="button" data-group="synthetic" data-subtab="synthetic-summary">Summary</button>
          <button class="subtab-button" type="button" data-group="synthetic" data-subtab="synthetic-guide">Metric Guide</button>
          <button class="subtab-button" type="button" data-group="synthetic" data-subtab="synthetic-metrics">Metric Tables</button>
          <button class="subtab-button" type="button" data-group="synthetic" data-subtab="synthetic-data">Generated Data</button>
          <button class="subtab-button" type="button" data-group="synthetic" data-subtab="synthetic-files">Files & Logs</button>
        </div>
        <section id="synthetic-summary" class="subtab-panel active" data-group="synthetic" data-fragment="benchmark-summary"></section>
        <section id="synthetic-guide" class="subtab-panel" data-group="synthetic" data-fragment="metric-guide"></section>
        <section id="synthetic-metrics" class="subtab-panel" data-group="synthetic" data-fragment="metrics"></section>
        <section id="synthetic-data" class="subtab-panel" data-group="synthetic" data-fragment="synthetic"></section>
        <section id="synthetic-files" class="subtab-panel" data-group="synthetic" data-fragment="files"></section>
      </section>
    </main>
  </div>
  <script src="assets/vendor/ankareport.js"></script>
  <script src="data/report-data.js"></script>
  <script src="assets/report.js"></script>
</body>
</html>
"""
    report_path.write_text(html_doc, encoding="utf-8")
    print(f"Saved HTML report: {report_path}")
    return report_path


def write_config(path: Path, args: argparse.Namespace, config: SportDataConfig, source_rows: int) -> None:
    """
    Description:
        Write outputs for `write_config`.

    Input:
        path: Path; args: argparse.Namespace; config: SportDataConfig; source_rows: int.

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    payload = {
        "dataset": DATASET_NAME,
        "dataset_path": str(Path(args.dataset_path).resolve()),
        "source_rows_used": source_rows,
        "models": args.models,
        "epochs": args.epochs,
        "epsilon": args.epsilon,
        "delta": args.delta,
        "dp_epsilon": args.dp_epsilon,
        "dp_delta": args.dp_delta,
        "pate_epsilon": args.pate_epsilon,
        "pate_delta": args.pate_delta,
        "sessions_per_person": args.sessions_per_person,
        "n_runs": args.n_runs,
        "log_path": str(args.log_path) if getattr(args, "log_path", None) else "",
        "dashboard_path": str((PROJECT_ROOT / "dashboard" / "production" / "index.html").resolve()),
        "target_col": config.target_col,
        "task_type": config.task_type,
        "id_col": config.id_col,
        "static_cols": config.static_cols,
        "numeric_cols": config.numeric_cols,
        "categorical_cols": config.categorical_cols,
        "session_numeric_cols": config.session_numeric_cols,
        "session_categorical_cols": config.session_categorical_cols,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_model_names(models: str) -> List[str]:
    """
    Description:
        Parse input values for `parse_model_names`.

    Input:
        models: str.

    Output:
        List[str].
    """
    names = [model.strip().lower() for model in models.split(",") if model.strip()]
    allowed = {
        "ctgan",
        "dpctgan",
        "pategan",
        "tabsyn",
        "bootstrap",
        "sdv_gaussian",
        "sdv_tvae",
        "sdv_par",
        "realtabformer",
    }
    unknown = sorted(set(names) - allowed)
    if unknown:
        raise ValueError(f"Unknown model(s): {unknown}. Allowed models: {sorted(allowed)}")
    return names


def parse_args() -> argparse.Namespace:
    """
    Description:
        Parse input values for `parse_args`.

    Input:
        None.

    Output:
        argparse.Namespace.
    """
    parser = argparse.ArgumentParser(description="Sport synthetic data benchmark.")
    parser.add_argument("--dataset-path", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--id-col", default="Athlete_ID")
    parser.add_argument("--target", default="Training_Outcome")
    parser.add_argument("--task", choices=["classification", "regression"], default="classification")
    parser.add_argument("--sample-rows", type=int, default=0, help="Use 0 to run on all rows.")
    parser.add_argument(
        "--models",
        default="ctgan,dpctgan,pategan,tabsyn,sdv_gaussian,sdv_tvae,sdv_par,realtabformer",
        help="Comma-separated models: ctgan, dpctgan, pategan, tabsyn, bootstrap, sdv_gaussian, sdv_tvae, sdv_par, realtabformer.",
    )
    parser.add_argument("--epochs", type=int, default=5, help="Training epochs for neural generators and TabSyn.")
    parser.add_argument("--epsilon", type=float, default=2.0)
    parser.add_argument("--delta", type=float, default=1e-6)
    parser.add_argument("--dp-epsilon", type=float, default=None, help="Optional DPCTGAN epsilon override.")
    parser.add_argument("--dp-delta", type=float, default=None, help="Optional DPCTGAN delta override.")
    parser.add_argument("--pate-epsilon", type=float, default=None, help="Optional PATEGAN epsilon override.")
    parser.add_argument("--pate-delta", type=float, default=None, help="Optional PATEGAN delta override.")
    parser.add_argument("--batch-size", "--batch_size", dest="batch_size", type=int, default=128)
    parser.add_argument("--latent-dim", type=int, default=64)
    parser.add_argument("--teacher-iters", type=int, default=5)
    parser.add_argument("--student-iters", type=int, default=5)
    parser.add_argument("--sessions-per-person", type=int, default=3)
    parser.add_argument("--n-runs", type=int, default=5, help="Number of generated trials after one-time training.")
    parser.add_argument("--test-size", type=float, default=0.3)
    parser.add_argument("--noise-scale", type=float, default=0.08)
    parser.add_argument("--donor-min-pool", type=int, default=20)
    parser.add_argument("--tabsyn-steps", type=int, default=5)
    parser.add_argument("--log-path", type=Path, default=None, help="Optional run log path saved in the run configuration.")
    parser.add_argument("--gpu", type=int, default=-1)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    """
    Description:
        Run the command-line entry point for `main`.

    Input:
        None.

    Output:
        None; the function performs file, state, logging, or plotting side effects.
    """
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if torch.cuda.is_available() and args.gpu != -1:
        print("CUDA available. Running on GPU.")
    else:
        print("CUDA not available or disabled. Running on CPU.")

    full_df = read_dataset(args.dataset_path)
    if args.sample_rows and args.sample_rows < len(full_df):
        df = full_df.sample(n=args.sample_rows, random_state=args.random_state).reset_index(drop=True)
    else:
        df = full_df.reset_index(drop=True)

    config = infer_config(df, args.id_col, args.target, args.task)
    model_names = parse_model_names(args.models)

    print(f"\n=== Dataset: {DATASET_NAME.upper()} ===")
    print(f"Dataset path: {args.dataset_path}")
    print(f"Rows used: {len(df)}")
    print(f"Target: {config.target_col}")
    print(f"Continuous columns: {len(config.continuous)}")
    print(f"Categorical columns: {len(config.categorical)}")
    print(f"Static columns preserved: {config.static_cols}")

    df_clean, real_utility, real_attack = evaluate_real_data_baseline(df, config, args.test_size)
    real_utility_list = [real_utility]
    real_attack_list = [real_attack]

    all_results = []
    metric_runs = defaultdict(list)
    metrics_by_run_rows = []
    latest_sessions_by_model: Dict[str, pd.DataFrame] = {}

    for model_name in model_names:
        print(f"\nEvaluating model: {model_name}")
        try:
            synth_utility_metrics, synth_attack_metrics, synth_trials = evaluate_synthetic_data_model(
                df_clean, config, model_name, args
            )
        except Exception as exc:
            print(f"Model {model_name} failed: {type(exc).__name__}: {exc}")
            metrics_by_run_rows.append({
                "dataset": DATASET_NAME,
                "model": model_name,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        for trial_idx, (utility, attack) in enumerate(zip(synth_utility_metrics, synth_attack_metrics), start=1):
            row = {
                "dataset": DATASET_NAME,
                "model": model_name,
                "trial": trial_idx,
                "status": "ok",
            }
            row.update(utility)
            row.update({f"attack_{key}": value for key, value in attack.items()})
            metrics_by_run_rows.append(row)
            metric_runs[(DATASET_NAME, model_name)].append({
                **utility,
                **{f"MIA_{key}": value for key, value in attack.items()},
            })

        if synth_trials:
            latest_sessions_by_model[model_name] = synth_trials[-1]
            trial_dir = args.output_dir / "synthetic" / "trials" / model_name
            trial_dir.mkdir(parents=True, exist_ok=True)
            for trial_idx, trial_df in enumerate(synth_trials, start=1):
                trial_df.to_csv(trial_dir / f"{DATASET_NAME}_{model_name}_trial_{trial_idx}.csv", index=False)

        if synth_utility_metrics:
            utility_df = pd.DataFrame(synth_utility_metrics).select_dtypes(include="number")
            attack_df = pd.DataFrame(synth_attack_metrics).select_dtypes(include="number")
            mean_utility = utility_df.mean().to_dict()
            mean_attack = attack_df.mean().to_dict()

            utility_p_values = SyntheticDataMetrics.calculate_p_values(
                real_utility_list * len(synth_utility_metrics), synth_utility_metrics
            )
            attack_p_values = SyntheticDataMetrics.calculate_p_values(
                real_attack_list * len(synth_attack_metrics), synth_attack_metrics
            )

            all_results.append({
                "dataset": DATASET_NAME,
                "model": model_name,
                "utility_metrics": mean_utility,
                "attack_metrics": mean_attack,
                "utility_p_values": utility_p_values,
                "attack_p_values": attack_p_values,
                "real_utility": real_utility,
                "real_attack": real_attack,
            })

    metrics_dir = args.output_dir / "metrics"
    config_dir = args.output_dir / "config"
    sessions_dir = args.output_dir / "synthetic" / "sessions"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)

    for model_name, sessions in latest_sessions_by_model.items():
        sessions.to_csv(sessions_dir / f"synthetic_sessions_{model_name}.csv", index=False)

    metrics_by_run = pd.DataFrame(metrics_by_run_rows)
    metrics_by_run.to_csv(metrics_dir / "metrics_by_run.csv", index=False)
    summarize_runs(metric_runs).to_csv(metrics_dir / "metrics_summary.csv", index=False)
    save_results(all_results, metric_runs, args.output_dir)
    save_real_baselines(metrics_dir, real_utility, real_attack)
    write_config(config_dir / "run_config.json", args, config, len(df))
    print("\nSynthetic sport session benchmark complete.")
    print(f"Models requested: {', '.join(model_names)}")
    print(f"Synthetic sessions saved under: {sessions_dir}")
    print(f"Metrics saved: {metrics_dir / 'metrics_summary.csv'}")
    print("Dashboard data can be refreshed with: bash run_dashboard.sh")


if __name__ == "__main__":
    main()
