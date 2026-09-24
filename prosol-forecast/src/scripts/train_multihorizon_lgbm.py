"""
PROSOL FORECAST — PHASE 5.1
DIRECT MULTI-HORIZON LIGHTGBM FORECASTING

Horizons:
    H+1  -> t + 1 hour
    H+6  -> t + 6 hours
    H+12 -> t + 12 hours
    H+24 -> t + 24 hours
    H+72 -> t + 72 hours

Dataset:
    data/processed/features/district_features.parquet

Split:
    Train      : 2005-2018
    Validation : 2019
    Test       : 2020

Target:
    p_pvgis_kw_per_kwp

Leakage policy:
    Historical features -> from forecast origin t
    Deterministic geometry/calendar -> from target time t+h
    Future actual weather/PV -> NEVER used

Primary benchmark:
    H+1  : current-value persistence
    H+6  : daily persistence
    H+12 : daily persistence
    H+24 : daily persistence
    H+72 : daily persistence

Additional benchmark:
    H+72 : weekly persistence
"""

from __future__ import annotations

import gc
import json
import pickle
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# =============================================================================
# PATHS
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FEATURE_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "features"
    / "district_features.parquet"
)

MODEL_DIR = PROJECT_ROOT / "models"
ML_DIR = PROJECT_ROOT / "data" / "processed" / "ml"

MODEL_DIR.mkdir(parents=True, exist_ok=True)
ML_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# CONFIGURATION
# =============================================================================

TARGET = "p_pvgis_kw_per_kwp"
TIME_COL = "timestamp"
DISTRICT_COL = "district_id"

RANDOM_STATE = 42

# -------------------------------------------------------------------------
# Forecast horizons
# -------------------------------------------------------------------------

HORIZONS = {
    "h1": 1,
    "h6": 6,
    "h12": 12,
    "h24": 24,
    "h72": 72,
}

# -------------------------------------------------------------------------
# Chronological split
# -------------------------------------------------------------------------

TRAIN_START = "2005-01-01"
TRAIN_END = "2018-12-31 23:00:00"

VAL_START = "2019-01-01"
VAL_END = "2019-12-31 23:00:00"

TEST_START = "2020-01-01"
TEST_END = "2020-12-31 23:00:00"


# =============================================================================
# FORECAST-SAFE FEATURES
# =============================================================================

FEATURES = [
    # Spatial
    "region_id",

    # Deterministic solar geometry
    "solar_elevation_deg",
    "solar_zenith_deg",
    "solar_azimuth_deg",
    "solar_elevation_calc_deg",
    "ghi_clearsky_w_m2",
    "dni_clearsky_w_m2",
    "dhi_clearsky_w_m2",
    "is_daylight",

    # Calendar
    "hour",
    "day_of_week",
    "month",
    "day_of_year",
    "week_of_year",
    "is_weekend",
    "hour_sin",
    "hour_cos",
    "doy_sin",
    "doy_cos",

    # Historical PV / clearness-index lags
    "p_lag_1h",
    "kt_lag_1h",
    "p_lag_2h",
    "kt_lag_2h",
    "p_lag_3h",
    "kt_lag_3h",
    "p_lag_6h",
    "kt_lag_6h",
    "p_lag_12h",
    "kt_lag_12h",
    "p_lag_24h",
    "kt_lag_24h",
    "p_lag_48h",
    "kt_lag_48h",
    "p_lag_168h",
    "kt_lag_168h",

    # Rolling historical features
    "p_roll_mean_3h",
    "p_roll_std_3h",
    "kt_roll_mean_3h",

    "p_roll_mean_6h",
    "p_roll_std_6h",
    "kt_roll_mean_6h",

    "p_roll_mean_24h",
    "p_roll_std_24h",
    "kt_roll_mean_24h",

    # Historical differences
    "p_lag_diff_1h_24h",
    "p_lag_diff_24h_168h",
    "kt_lag_diff_1h_24h",

    # Historical spatial context
    "region_mean_p_lag",
    "region_mean_kt_lag",
    "national_mean_p_lag",
    "national_mean_kt_lag",
    "p_dev_from_region",
]


# =============================================================================
# FEATURES ALLOWED AT FUTURE TARGET TIME
# =============================================================================

FUTURE_DETERMINISTIC_FEATURES = [
    "solar_elevation_deg",
    "solar_zenith_deg",
    "solar_azimuth_deg",
    "solar_elevation_calc_deg",
    "ghi_clearsky_w_m2",
    "dni_clearsky_w_m2",
    "dhi_clearsky_w_m2",
    "is_daylight",
    "hour",
    "day_of_week",
    "month",
    "day_of_year",
    "week_of_year",
    "is_weekend",
    "hour_sin",
    "hour_cos",
    "doy_sin",
    "doy_cos",
]


# =============================================================================
# LIGHTGBM CONFIGURATION
# =============================================================================

LGB_PARAMS = {
    "objective": "regression",
    "metric": "rmse",

    "n_estimators": 1200,
    "learning_rate": 0.05,

    "num_leaves": 31,
    "max_depth": -1,
    "min_child_samples": 100,

    "subsample": 0.80,
    "subsample_freq": 1,
    "colsample_bytree": 0.80,

    "reg_alpha": 0.10,
    "reg_lambda": 0.20,

    "random_state": RANDOM_STATE,
    "n_jobs": -1,

    "verbosity": -1,
    "force_col_wise": True,
}

EARLY_STOPPING_ROUNDS = 50


# =============================================================================
# UTILITIES
# =============================================================================

def print_header(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def rmse(y_true, y_pred):
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def safe_mape(y_true, y_pred, epsilon=1e-3):
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)

    mask = np.abs(y_true) > epsilon

    if mask.sum() == 0:
        return float("nan")

    return float(
        np.mean(
            np.abs(
                (y_true[mask] - y_pred[mask])
                / y_true[mask]
            )
        ) * 100.0
    )


def normalized_rmse(y_true, y_pred):
    mean_actual = float(np.mean(y_true))

    if mean_actual == 0:
        return float("nan")

    return rmse(y_true, y_pred) / mean_actual


def skill_vs_persistence(y_true, y_pred, persistence):
    model_rmse = rmse(y_true, y_pred)
    persistence_rmse = rmse(y_true, persistence)

    if persistence_rmse == 0:
        return float("nan")

    return float(
        1.0 - model_rmse / persistence_rmse
    )


def check_required_columns(df):
    required = set(
        FEATURES
        + [TARGET, TIME_COL, DISTRICT_COL]
    )

    missing = sorted(
        required - set(df.columns)
    )

    if missing:
        raise ValueError(
            "Missing required columns:\n"
            + "\n".join(missing)
        )


def print_memory_usage(df, label):
    memory_gb = (
        df.memory_usage(deep=True).sum()
        / (1024 ** 3)
    )

    print(
        f"[MEMORY] {label}: "
        f"{memory_gb:.2f} GB"
    )


# =============================================================================
# LOAD DATA
# =============================================================================

def load_data():

    print_header(
        "LOADING FEATURE DATASET"
    )

    print(
        f"Feature file:\n{FEATURE_FILE}"
    )

    if not FEATURE_FILE.exists():
        raise FileNotFoundError(
            f"Feature file not found:\n"
            f"{FEATURE_FILE}"
        )

    df = pd.read_parquet(
        FEATURE_FILE
    )

    print(
        f"Rows    : {len(df):,}"
    )

    print(
        f"Columns : {len(df.columns)}"
    )

    check_required_columns(df)

    df[TIME_COL] = pd.to_datetime(
        df[TIME_COL],
        errors="coerce"
    )

    if df[TIME_COL].isna().any():
        raise ValueError(
            "Invalid timestamps detected."
        )

    print(
        "Sorting by district + timestamp..."
    )

    df.sort_values(
        [DISTRICT_COL, TIME_COL],
        inplace=True,
        kind="mergesort"
    )

    df.reset_index(
        drop=True,
        inplace=True
    )

    print(
        f"Timestamp range: "
        f"{df[TIME_COL].min()} -> "
        f"{df[TIME_COL].max()}"
    )

    print(
        f"Districts: "
        f"{df[DISTRICT_COL].nunique():,}"
    )

    print_memory_usage(
        df,
        "after loading"
    )

    return df


# =============================================================================
# HOURLY INTEGRITY CHECK
# =============================================================================

def check_hourly_integrity(df):

    print_header(
        "CHECKING HOURLY TIMESTAMP INTEGRITY"
    )

    district_ids = (
        df[DISTRICT_COL]
        .drop_duplicates()
    )

    problems = []

    for district_id in district_ids:

        timestamps = df.loc[
            df[DISTRICT_COL] == district_id,
            TIME_COL
        ]

        diffs = (
            timestamps
            .diff()
            .dropna()
        )

        bad = diffs[
            diffs != pd.Timedelta(hours=1)
        ]

        if len(bad) > 0:

            problems.append(
                {
                    "district_id": district_id,
                    "bad_intervals": len(bad),
                }
            )

    if problems:

        print(
            "WARNING: Non-hourly gaps detected."
        )

        for item in problems[:10]:
            print(item)

        raise ValueError(
            "Hourly integrity check failed."
        )

    print(
        f"PASS — all "
        f"{len(district_ids)} districts "
        f"have continuous hourly timestamps."
    )


# =============================================================================
# BUILD HORIZON DATASET
# =============================================================================

def build_horizon_dataset(
    df,
    horizon_label,
    horizon_hours,
):

    print_header(
        f"BUILDING DATASET — "
        f"{horizon_label.upper()} "
        f"(t + {horizon_hours}h)"
    )

    start = time.perf_counter()

    work_cols = list(
        dict.fromkeys(
            [DISTRICT_COL, TIME_COL, TARGET]
            + FEATURES
        )
    )

    data = df[
        work_cols
    ].copy()

    # -------------------------------------------------------------------------
    # Target at t+h
    # -------------------------------------------------------------------------

    print(
        f"Creating target: "
        f"{TARGET}(t+{horizon_hours}h)"
    )

    grouped = data.groupby(
        DISTRICT_COL,
        sort=False
    )

    data["target_h"] = (
        grouped[TARGET]
        .shift(-horizon_hours)
    )

    # -------------------------------------------------------------------------
    # Target timestamp
    # -------------------------------------------------------------------------

    data[
        "forecast_target_timestamp"
    ] = (
        data[TIME_COL]
        + pd.Timedelta(
            hours=horizon_hours
        )
    )

    # -------------------------------------------------------------------------
    # Shift deterministic features to t+h
    # -------------------------------------------------------------------------

    print(
        "Creating future deterministic features..."
    )

    grouped = data.groupby(
        DISTRICT_COL,
        sort=False
    )

    for col in FUTURE_DETERMINISTIC_FEATURES:

        data[col] = (
            grouped[col]
            .shift(-horizon_hours)
        )

    # -------------------------------------------------------------------------
    # Persistence baselines
    # -------------------------------------------------------------------------

    # Current persistence:
    #
    # y_hat(t+h) = y(t)
    #
    data[
        "persistence_current_h"
    ] = data[TARGET]

    # Daily persistence:
    #
    # y_hat(t+h) = y(t+h-24)
    #
    # Since target_h = y(t+h),
    # shift(24) gives y(t+h-24).
    #
    data[
        "persistence_daily_h"
    ] = (
        data.groupby(
            DISTRICT_COL,
            sort=False
        )["target_h"]
        .shift(24)
    )

    # Weekly persistence:
    #
    # y_hat(t+h) = y(t+h-168)
    #
    # Only used as an additional benchmark
    # for H+72.
    #
    data[
        "persistence_weekly_h"
    ] = (
        data.groupby(
            DISTRICT_COL,
            sort=False
        )["target_h"]
        .shift(168)
    )

    # -------------------------------------------------------------------------
    # Remove rows without target
    # -------------------------------------------------------------------------

    before = len(data)

    data.dropna(
        subset=["target_h"],
        inplace=True
    )

    print(
        f"Rows before target filtering: "
        f"{before:,}"
    )

    print(
        f"Rows after target filtering : "
        f"{len(data):,}"
    )

    # -------------------------------------------------------------------------
    # Forecast origin / target years
    # -------------------------------------------------------------------------

    data["origin_year"] = (
        data[TIME_COL].dt.year
    )

    data["target_year"] = (
        data[
            "forecast_target_timestamp"
        ].dt.year
    )

    # -------------------------------------------------------------------------
    # Train
    # -------------------------------------------------------------------------

    train_mask = (
        (data[TIME_COL] >= pd.Timestamp(TRAIN_START))
        & (data[TIME_COL] <= pd.Timestamp(TRAIN_END))
        & (data["target_year"] <= 2018)
    )

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    val_mask = (
        (data[TIME_COL] >= pd.Timestamp(VAL_START))
        & (data[TIME_COL] <= pd.Timestamp(VAL_END))
        & (data["target_year"] == 2019)
    )

    # -------------------------------------------------------------------------
    # Test
    # -------------------------------------------------------------------------

    test_mask = (
        (data[TIME_COL] >= pd.Timestamp(TEST_START))
        & (data[TIME_COL] <= pd.Timestamp(TEST_END))
        & (data["target_year"] == 2020)
    )

    train = data.loc[
        train_mask
    ].copy()

    val = data.loc[
        val_mask
    ].copy()

    test = data.loc[
        test_mask
    ].copy()

    print()
    print("SPLIT:")
    print(
        f"Train      : {len(train):,}"
    )
    print(
        f"Validation : {len(val):,}"
    )
    print(
        f"Test       : {len(test):,}"
    )

    if (
        len(train) == 0
        or len(val) == 0
        or len(test) == 0
    ):
        raise ValueError(
            "One or more splits are empty."
        )

    # -------------------------------------------------------------------------
    # Target timestamp ranges
    # -------------------------------------------------------------------------

    print()
    print(
        "TARGET TIMESTAMP RANGES:"
    )

    for name, part in [
        ("Train", train),
        ("Validation", val),
        ("Test", test),
    ]:

        print(
            f"{name:<12}: "
            f"{part['forecast_target_timestamp'].min()} "
            f"-> "
            f"{part['forecast_target_timestamp'].max()}"
        )

    # -------------------------------------------------------------------------
    # Leakage check
    # -------------------------------------------------------------------------

    forbidden_columns = [
        "ghi_w_m2",
        "beam_w_m2",
        "diffuse_w_m2",
        "reflected_w_m2",
        "temperature_2m_c",
        "wind_speed_10m_ms",
        "kt",
        "estimated_power_mw",
        TARGET,
    ]

    forbidden_used = [
        col
        for col in forbidden_columns
        if col in FEATURES
    ]

    if forbidden_used:

        raise ValueError(
            "Potential leakage features found:\n"
            + "\n".join(
                forbidden_used
            )
        )

    print()
    print("LEAKAGE CHECK:")
    print(
        "PASS — no future actual weather/PV "
        "is included in model features."
    )

    print(
        f"\nDataset construction time: "
        f"{time.perf_counter() - start:.1f} s"
    )

    return train, val, test


# =============================================================================
# METRICS
# =============================================================================

def calculate_metrics(
    y_true,
    y_pred,
    persistence,
):

    y_true = np.asarray(
        y_true
    )

    y_pred = np.asarray(
        y_pred
    )

    persistence = np.asarray(
        persistence
    )

    valid = np.isfinite(
        persistence
    )

    if valid.sum() == 0:

        persistence_mae = np.nan
        persistence_rmse = np.nan
        skill = np.nan

    else:

        y_t_p = y_true[valid]
        p_p = persistence[valid]

        persistence_mae = (
            mean_absolute_error(
                y_t_p,
                p_p
            )
        )

        persistence_rmse = rmse(
            y_t_p,
            p_p
        )

        skill = skill_vs_persistence(
            y_t_p,
            y_pred[valid],
            p_p
        )

    return {
        "mae": float(
            mean_absolute_error(
                y_true,
                y_pred
            )
        ),
        "rmse": float(
            rmse(
                y_true,
                y_pred
            )
        ),
        "r2": float(
            r2_score(
                y_true,
                y_pred
            )
        ),
        "mape_percent": float(
            safe_mape(
                y_true,
                y_pred
            )
        ),
        "nrmse": float(
            normalized_rmse(
                y_true,
                y_pred
            )
        ),
        "persistence_mae": (
            float(persistence_mae)
            if np.isfinite(
                persistence_mae
            )
            else None
        ),
        "persistence_rmse": (
            float(persistence_rmse)
            if np.isfinite(
                persistence_rmse
            )
            else None
        ),
        "skill_vs_persistence": (
            float(skill)
            if np.isfinite(skill)
            else None
        ),
        "mean_actual": float(
            np.mean(y_true)
        ),
        "mean_prediction": float(
            np.mean(y_pred)
        ),
    }


def print_metrics(metrics):

    print(
        f"MAE                  : "
        f"{metrics['mae']:.6f}"
    )

    print(
        f"RMSE                 : "
        f"{metrics['rmse']:.6f}"
    )

    print(
        f"R²                   : "
        f"{metrics['r2']:.6f}"
    )

    print(
        f"MAPE                 : "
        f"{metrics['mape_percent']:.2f}%"
    )

    print(
        f"NRMSE                : "
        f"{metrics['nrmse']:.6f}"
    )

    if metrics[
        "persistence_rmse"
    ] is not None:

        print(
            f"Persistence RMSE     : "
            f"{metrics['persistence_rmse']:.6f}"
        )

        print(
            f"Skill vs persistence : "
            f"{metrics['skill_vs_persistence']:.6f}"
        )

    else:

        print(
            "Persistence RMSE     : N/A"
        )

        print(
            "Skill vs persistence : N/A"
        )


# =============================================================================
# DISTRICT METRICS
# =============================================================================

def calculate_district_metrics(
    predictions
):

    rows = []

    for district_id, group in predictions.groupby(
        "district_id",
        sort=True
    ):

        y_true = group[
            "actual_p_kw_per_kwp"
        ].to_numpy()

        y_pred = group[
            "predicted_p_kw_per_kwp"
        ].to_numpy()

        persistence = group[
            "persistence_p_kw_per_kwp"
        ].to_numpy()

        valid = np.isfinite(
            persistence
        )

        y_t_p = y_true[valid]
        y_p_p = y_pred[valid]
        p_p = persistence[valid]

        if len(p_p) > 0:

            persistence_rmse = rmse(
                y_t_p,
                p_p
            )

            skill = (
                skill_vs_persistence(
                    y_t_p,
                    y_p_p,
                    p_p
                )
            )

        else:

            persistence_rmse = np.nan
            skill = np.nan

        rows.append(
            {
                "district_id": district_id,
                "n_test": len(group),

                "mae": mean_absolute_error(
                    y_true,
                    y_pred
                ),

                "rmse": rmse(
                    y_true,
                    y_pred
                ),

                "r2": r2_score(
                    y_true,
                    y_pred
                ),

                "mape_percent": safe_mape(
                    y_true,
                    y_pred
                ),

                "nrmse": normalized_rmse(
                    y_true,
                    y_pred
                ),

                "persistence_rmse":
                    persistence_rmse,

                "skill_vs_persistence":
                    skill,
            }
        )

    return pd.DataFrame(
        rows
    )


# =============================================================================
# TRAIN ONE HORIZON
# =============================================================================

def train_one_horizon(
    train,
    val,
    test,
    horizon_label,
    horizon_hours,
):

    print_header(
        f"TRAINING LIGHTGBM — "
        f"{horizon_label.upper()} "
        f"(t + {horizon_hours}h)"
    )

    start_time = time.perf_counter()

    X_train = train[FEATURES]
    y_train = train["target_h"]

    X_val = val[FEATURES]
    y_val = val["target_h"]

    X_test = test[FEATURES]
    y_test = test["target_h"]

    # -------------------------------------------------------------------------
    # Persistence arrays
    # -------------------------------------------------------------------------

    persistence_current_test = (
        test[
            "persistence_current_h"
        ].to_numpy(
            dtype=np.float32
        )
    )

    persistence_daily_test = (
        test[
            "persistence_daily_h"
        ].to_numpy(
            dtype=np.float32
        )
    )

    persistence_weekly_test = (
        test[
            "persistence_weekly_h"
        ].to_numpy(
            dtype=np.float32
        )
    )

    print(
        f"\nX_train: {X_train.shape}"
    )

    print(
        f"X_val  : {X_val.shape}"
    )

    print(
        f"X_test : {X_test.shape}"
    )

    # -------------------------------------------------------------------------
    # Model
    # -------------------------------------------------------------------------

    model = lgb.LGBMRegressor(
        **LGB_PARAMS
    )

    print(
        f"\nStarting LightGBM training "
        f"(max trees = "
        f"{LGB_PARAMS['n_estimators']})..."
    )

    model.fit(
        X_train,
        y_train,
        eval_X=X_val,
        eval_y=y_val,
        eval_names=[
            "validation"
        ],
        callbacks=[
            lgb.early_stopping(
                EARLY_STOPPING_ROUNDS,
                verbose=True
            ),
            lgb.log_evaluation(
                period=100
            ),
        ],
    )

    training_time = (
        time.perf_counter()
        - start_time
    )

    best_iteration = (
        model.best_iteration_
    )

    print()
    print("=" * 80)
    print("TRAINING FINISHED")
    print("=" * 80)

    print(
        f"Training time : "
        f"{training_time / 60:.2f} minutes"
    )

    print(
        f"Best iteration: "
        f"{best_iteration}"
    )

    # -------------------------------------------------------------------------
    # Predictions
    # -------------------------------------------------------------------------

    print(
        "\nGenerating validation predictions..."
    )

    val_pred = model.predict(
        X_val,
        num_iteration=best_iteration
    )

    print(
        "Generating test predictions..."
    )

    test_pred = model.predict(
        X_test,
        num_iteration=best_iteration
    )

    # PV production cannot be negative
    val_pred = np.clip(
        val_pred,
        0.0,
        None
    )

    test_pred = np.clip(
        test_pred,
        0.0,
        None
    )

    # -------------------------------------------------------------------------
    # Validation benchmark
    # -------------------------------------------------------------------------

    val_persistence_daily = (
        val[
            "persistence_daily_h"
        ].to_numpy(
            dtype=np.float32
        )
    )

    val_metrics = calculate_metrics(
        y_val.to_numpy(),
        val_pred,
        val_persistence_daily
    )

    # -------------------------------------------------------------------------
    # Test benchmarks
    # -------------------------------------------------------------------------

    test_metrics_current = (
        calculate_metrics(
            y_test.to_numpy(),
            test_pred,
            persistence_current_test
        )
    )

    test_metrics_daily = (
        calculate_metrics(
            y_test.to_numpy(),
            test_pred,
            persistence_daily_test
        )
    )

    test_metrics_weekly = (
        calculate_metrics(
            y_test.to_numpy(),
            test_pred,
            persistence_weekly_test
        )
    )

    # -------------------------------------------------------------------------
    # Print validation
    # -------------------------------------------------------------------------

    print()
    print(
        "VALIDATION METRICS "
        "(daily persistence)"
    )

    print_metrics(
        val_metrics
    )

    # -------------------------------------------------------------------------
    # Print test
    # -------------------------------------------------------------------------

    print()
    print(
        "2020 TEST METRICS "
        "(current-value persistence)"
    )

    if horizon_hours >= 6:

        print(
            "NOTE: daily persistence is "
            "the primary benchmark for "
            f"H+{horizon_hours}."
        )

    print_metrics(
        test_metrics_current
    )

    print()
    print(
        "2020 TEST METRICS "
        "(daily persistence — primary)"
    )

    print_metrics(
        test_metrics_daily
    )

    # Weekly only for H+72
    if horizon_hours == 72:

        print()
        print(
            "2020 TEST METRICS "
            "(weekly persistence — additional)"
        )

        print_metrics(
            test_metrics_weekly
        )

    # -------------------------------------------------------------------------
    # Prediction dataframe
    # -------------------------------------------------------------------------

    predictions = pd.DataFrame(
        {
            "district_id":
                test[
                    DISTRICT_COL
                ].to_numpy(),

            "timestamp":
                test[
                    TIME_COL
                ].to_numpy(),

            "horizon_label":
                horizon_label,

            "horizon_hours":
                horizon_hours,

            "forecast_target_timestamp":
                test[
                    "forecast_target_timestamp"
                ].to_numpy(),

            "actual_p_kw_per_kwp":
                y_test.to_numpy(
                    dtype=np.float32
                ),

            "predicted_p_kw_per_kwp":
                test_pred.astype(
                    np.float32
                ),

            "persistence_current_p_kw_per_kwp":
                persistence_current_test,

            "persistence_daily_p_kw_per_kwp":
                persistence_daily_test,

            "persistence_weekly_p_kw_per_kwp":
                persistence_weekly_test,

            "residual_kw_per_kwp":
                (
                    y_test.to_numpy(
                        dtype=np.float32
                    )
                    - test_pred.astype(
                        np.float32
                    )
                ),
        }
    )

    # -------------------------------------------------------------------------
    # Canonical persistence for district metrics
    # -------------------------------------------------------------------------

    predictions[
        "persistence_p_kw_per_kwp"
    ] = predictions[
        "persistence_daily_p_kw_per_kwp"
    ]

    district_metrics = (
        calculate_district_metrics(
            predictions
        )
    )

    predictions.drop(
        columns=[
            "persistence_p_kw_per_kwp"
        ],
        inplace=True
    )

    # -------------------------------------------------------------------------
    # Save model
    # -------------------------------------------------------------------------

    model_path = (
        MODEL_DIR
        / f"lightgbm_{horizon_label}.pkl"
    )

    print(
        f"\nSaving model:\n{model_path}"
    )

    with open(
        model_path,
        "wb"
    ) as f:

        pickle.dump(
            model,
            f,
            protocol=pickle.HIGHEST_PROTOCOL
        )

    # -------------------------------------------------------------------------
    # Save metadata
    # -------------------------------------------------------------------------

    feature_path = (
        MODEL_DIR
        / f"lightgbm_{horizon_label}_features.json"
    )

    feature_metadata = {

        "project":
            "Prosol Forecast",

        "phase":
            "5.1",

        "model_type":
            "Direct multi-horizon LightGBM",

        "horizon_label":
            horizon_label,

        "horizon_hours":
            horizon_hours,

        "target":
            TARGET,

        "n_features":
            len(FEATURES),

        "features":
            FEATURES,

        "future_deterministic_features":
            FUTURE_DETERMINISTIC_FEATURES,

        "training_period":
            [TRAIN_START, TRAIN_END],

        "validation_period":
            [VAL_START, VAL_END],

        "test_period":
            [TEST_START, TEST_END],

        "best_iteration":
            int(best_iteration),

        "training_time_seconds":
            float(training_time),

        "lightgbm_parameters":
            LGB_PARAMS,

        "persistence_baselines":
            {
                "current_value":
                    "y_hat(t+h) = y(t)",

                "daily":
                    "y_hat(t+h) = y(t+h-24)",

                "weekly":
                    "y_hat(t+h) = y(t+h-168)",
            },

        "primary_benchmark":
            "daily",

        "leakage_policy":
            {
                "future_actual_weather":
                    False,

                "future_actual_pv":
                    False,

                "future_actual_temperature":
                    False,

                "future_actual_wind":
                    False,

                "future_actual_ghi":
                    False,

                "future_deterministic_solar_geometry":
                    True,

                "future_calendar":
                    True,

                "historical_pv_lags":
                    True,

                "historical_kt_lags":
                    True,

                "historical_rolling_features":
                    True,

                "historical_spatial_features":
                    True,
            },
    }

    with open(
        feature_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            feature_metadata,
            f,
            indent=2
        )

    # -------------------------------------------------------------------------
    # Result
    # -------------------------------------------------------------------------

    result = {

        "horizon_label":
            horizon_label,

        "horizon_hours":
            horizon_hours,

        "n_train":
            int(len(train)),

        "n_validation":
            int(len(val)),

        "n_test":
            int(len(test)),

        "best_iteration":
            int(best_iteration),

        "training_time_seconds":
            float(training_time),

        "training_time_minutes":
            float(
                training_time / 60.0
            ),

        "validation":
            val_metrics,

        "test_current_persistence":
            test_metrics_current,

        "test_daily_persistence":
            test_metrics_daily,

        "test_weekly_persistence":
            test_metrics_weekly,

        "model_path":
            str(model_path),

        "feature_path":
            str(feature_path),
    }

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    del (
        X_train,
        X_val,
        X_test,
        y_train,
        y_val,
        y_test,
        val_pred,
    )

    gc.collect()

    return (
        result,
        predictions,
        district_metrics,
        model,
    )


# =============================================================================
# FINAL VALIDATION
# =============================================================================

def final_validation_check(
    predictions
):

    print_header(
        "FINAL VALIDATION CHECK"
    )

    required = [
        "district_id",
        "timestamp",
        "horizon_label",
        "horizon_hours",
        "forecast_target_timestamp",
        "actual_p_kw_per_kwp",
        "predicted_p_kw_per_kwp",
        "residual_kw_per_kwp",
    ]

    missing = [
        c
        for c in required
        if c not in predictions.columns
    ]

    if missing:

        raise ValueError(
            "Missing prediction columns:\n"
            + "\n".join(missing)
        )

    # -------------------------------------------------------------------------
    # Timestamp alignment
    # -------------------------------------------------------------------------

    diff_hours = (
        (
            pd.to_datetime(
                predictions[
                    "forecast_target_timestamp"
                ]
            )
            -
            pd.to_datetime(
                predictions[
                    "timestamp"
                ]
            )
        )
        / pd.Timedelta(hours=1)
    ).to_numpy()

    expected = (
        predictions[
            "horizon_hours"
        ].to_numpy()
    )

    if not np.allclose(
        diff_hours,
        expected
    ):

        raise ValueError(
            "Target timestamp mismatch detected."
        )

    # -------------------------------------------------------------------------
    # NaN check
    # -------------------------------------------------------------------------

    nan_count = int(
        predictions.isna()
        .sum()
        .sum()
    )

    if nan_count > 0:

        raise ValueError(
            f"NaNs detected: "
            f"{nan_count:,}"
        )

    # -------------------------------------------------------------------------
    # Negative prediction check
    # -------------------------------------------------------------------------

    neg_count = int(
        (
            predictions[
                "predicted_p_kw_per_kwp"
            ] < 0
        ).sum()
    )

    if neg_count > 0:

        raise ValueError(
            f"Negative predictions detected: "
            f"{neg_count:,}"
        )

    # -------------------------------------------------------------------------
    # Horizon check
    # -------------------------------------------------------------------------

    actual_horizons = sorted(
        predictions[
            "horizon_hours"
        ].unique()
    )

    expected_horizons = sorted(
        HORIZONS.values()
    )

    if actual_horizons != expected_horizons:

        raise ValueError(
            f"Horizon mismatch.\n"
            f"Expected: {expected_horizons}\n"
            f"Found: {actual_horizons}"
        )

    print(
        f"Rows           : "
        f"{len(predictions):,}"
    )

    print(
        f"NaN count      : "
        f"{nan_count}"
    )

    print(
        f"Negative count : "
        f"{neg_count}"
    )

    print(
        f"Horizons       : "
        f"{actual_horizons}"
    )

    print(
        "PASS — prediction "
        "timestamps and outputs are valid."
    )


# =============================================================================
# MAIN
# =============================================================================

def main():

    overall_start = (
        time.perf_counter()
    )

    print_header(
        "PROSOL FORECAST — PHASE 5.1"
    )

    print(
        "DIRECT MULTI-HORIZON "
        "LIGHTGBM FORECASTING"
    )

    print()

    for label, hours in HORIZONS.items():

        print(
            f"  {label.upper():>5} "
            f"-> t + {hours}h"
        )

    print(
        f"\nTarget   : {TARGET}"
    )

    print(
        f"Features : {len(FEATURES)}"
    )

    print(
        f"\nTrain      : "
        f"{TRAIN_START} -> {TRAIN_END}"
    )

    print(
        f"Validation : "
        f"{VAL_START} -> {VAL_END}"
    )

    print(
        f"Test       : "
        f"{TEST_START} -> {TEST_END}"
    )

    # -------------------------------------------------------------------------
    # Load
    # -------------------------------------------------------------------------

    df = load_data()

    # -------------------------------------------------------------------------
    # Integrity
    # -------------------------------------------------------------------------

    check_hourly_integrity(
        df
    )

    # -------------------------------------------------------------------------
    # Containers
    # -------------------------------------------------------------------------

    all_results = []
    all_predictions = []
    all_district_metrics = []

    # -------------------------------------------------------------------------
    # Train every horizon
    # -------------------------------------------------------------------------

    for (
        horizon_label,
        horizon_hours
    ) in HORIZONS.items():

        horizon_start = (
            time.perf_counter()
        )

        print_header(
            f"STARTING "
            f"{horizon_label.upper()} "
            f"(t + {horizon_hours}h)"
        )

        train, val, test = (
            build_horizon_dataset(
                df=df,
                horizon_label=horizon_label,
                horizon_hours=horizon_hours,
            )
        )

        (
            result,
            predictions,
            district_metrics,
            _model,
        ) = train_one_horizon(
            train=train,
            val=val,
            test=test,
            horizon_label=horizon_label,
            horizon_hours=horizon_hours,
        )

        district_metrics[
            "horizon_label"
        ] = horizon_label

        district_metrics[
            "horizon_hours"
        ] = horizon_hours

        all_results.append(
            result
        )

        all_predictions.append(
            predictions
        )

        all_district_metrics.append(
            district_metrics
        )

        del (
            train,
            val,
            test,
            predictions,
            district_metrics,
            _model,
        )

        gc.collect()

        horizon_time = (
            time.perf_counter()
            - horizon_start
        )

        print(
            f"\n{horizon_label.upper()} "
            f"TOTAL TIME: "
            f"{horizon_time / 60:.2f} minutes"
        )

    # -------------------------------------------------------------------------
    # Combine predictions
    # -------------------------------------------------------------------------

    print_header(
        "COMBINING MULTI-HORIZON RESULTS"
    )

    predictions_df = pd.concat(
        all_predictions,
        ignore_index=True
    )

    district_metrics_df = pd.concat(
        all_district_metrics,
        ignore_index=True
    )

    # -------------------------------------------------------------------------
    # Final validation
    # -------------------------------------------------------------------------

    final_validation_check(
        predictions_df
    )

    # -------------------------------------------------------------------------
    # Save predictions
    # -------------------------------------------------------------------------

    predictions_path = (
        ML_DIR
        / "multihorizon_predictions.parquet"
    )

    print(
        f"\nSaving predictions:\n"
        f"{predictions_path}"
    )

    predictions_df.to_parquet(
        predictions_path,
        index=False
    )

    # -------------------------------------------------------------------------
    # Metrics table
    # -------------------------------------------------------------------------

    metrics_rows = []

    for result in all_results:

        v = result[
            "validation"
        ]

        tc = result[
            "test_current_persistence"
        ]

        td = result[
            "test_daily_persistence"
        ]

        tw = result[
            "test_weekly_persistence"
        ]

        metrics_rows.append(
            {
                "horizon_label":
                    result[
                        "horizon_label"
                    ],

                "horizon_hours":
                    result[
                        "horizon_hours"
                    ],

                "n_train":
                    result["n_train"],

                "n_validation":
                    result["n_validation"],

                "n_test":
                    result["n_test"],

                "best_iteration":
                    result["best_iteration"],

                "training_time_minutes":
                    result[
                        "training_time_minutes"
                    ],

                # Validation
                "val_mae":
                    v["mae"],

                "val_rmse":
                    v["rmse"],

                "val_r2":
                    v["r2"],

                "val_skill_vs_daily":
                    v[
                        "skill_vs_persistence"
                    ],

                # Test
                "test_mae":
                    td["mae"],

                "test_rmse":
                    td["rmse"],

                "test_r2":
                    td["r2"],

                "test_mape_percent":
                    td["mape_percent"],

                # Skill against primary daily benchmark
                "test_skill_vs_daily":
                    td[
                        "skill_vs_persistence"
                    ],

                # Additional current benchmark
                "test_skill_vs_current":
                    tc[
                        "skill_vs_persistence"
                    ],

                # Additional weekly benchmark
                "test_skill_vs_weekly":
                    tw[
                        "skill_vs_persistence"
                    ],

                "test_persistence_daily_rmse":
                    td[
                        "persistence_rmse"
                    ],

                "test_persistence_current_rmse":
                    tc[
                        "persistence_rmse"
                    ],

                "test_persistence_weekly_rmse":
                    tw[
                        "persistence_rmse"
                    ],
            }
        )

    metrics_df = pd.DataFrame(
        metrics_rows
    )

    # -------------------------------------------------------------------------
    # Save metrics
    # -------------------------------------------------------------------------

    metrics_csv_path = (
        ML_DIR
        / "multihorizon_metrics.csv"
    )

    metrics_df.to_csv(
        metrics_csv_path,
        index=False
    )

    district_csv_path = (
        ML_DIR
        / "multihorizon_district_metrics.csv"
    )

    district_metrics_df.to_csv(
        district_csv_path,
        index=False
    )

    # -------------------------------------------------------------------------
    # Save JSON
    # -------------------------------------------------------------------------

    metrics_json_path = (
        ML_DIR
        / "multihorizon_metrics.json"
    )

    json_output = {

        "project":
            "Prosol Forecast",

        "phase":
            "5.1",

        "description":
            (
                "Direct multi-horizon "
                "LightGBM forecasting "
                "without future observed "
                "weather."
            ),

        "target":
            TARGET,

        "horizons":
            HORIZONS,

        "n_features":
            len(FEATURES),

        "features":
            FEATURES,

        "future_deterministic_features":
            FUTURE_DETERMINISTIC_FEATURES,

        "train_period":
            [TRAIN_START, TRAIN_END],

        "validation_period":
            [VAL_START, VAL_END],

        "test_period":
            [TEST_START, TEST_END],

        "models":
            all_results,

        "primary_benchmark":
            {
                "h1":
                    "current-value",

                "h6":
                    "daily",

                "h12":
                    "daily",

                "h24":
                    "daily",

                "h72":
                    "daily",
            },

        "additional_benchmark":
            {
                "h72":
                    "weekly",
            },

        "output_files":
            {
                "predictions":
                    str(
                        predictions_path
                    ),

                "metrics_csv":
                    str(
                        metrics_csv_path
                    ),

                "district_metrics_csv":
                    str(
                        district_csv_path
                    ),

                "metrics_json":
                    str(
                        metrics_json_path
                    ),
            },

        "leakage_policy":
            {
                "future_actual_weather":
                    False,

                "future_actual_pv":
                    False,

                "future_actual_temperature":
                    False,

                "future_actual_wind":
                    False,

                "future_actual_ghi":
                    False,

                "future_deterministic_solar_geometry":
                    True,

                "future_calendar":
                    True,

                "historical_pv_lags":
                    True,

                "historical_kt_lags":
                    True,

                "historical_rolling_features":
                    True,

                "historical_spatial_features":
                    True,
            },

        "persistence_baselines":
            {
                "current_value":
                    "y_hat(t+h) = y(t)",

                "daily":
                    "y_hat(t+h) = y(t+h-24)",

                "weekly":
                    "y_hat(t+h) = y(t+h-168)",
            },

        "notes":
            [
                "Weather-independent multi-horizon baseline.",

                "Future observed weather is never used.",

                "Future deterministic solar geometry "
                "and calendar information are allowed.",

                "Daily persistence is the primary "
                "benchmark for H+6, H+12, H+24 and H+72.",

                "Weekly persistence is reported "
                "as an additional benchmark for H+72.",

                "Phase 5.2 will introduce genuine "
                "weather forecasts.",

                "MAPE excludes actual values <= 0.001 "
                "to avoid nighttime division instability.",
            ],
    }

    with open(
        metrics_json_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            json_output,
            f,
            indent=2
        )

    # -------------------------------------------------------------------------
    # Final report
    # -------------------------------------------------------------------------

    overall_time = (
        time.perf_counter()
        - overall_start
    )

    print_header(
        "PHASE 5.1 COMPLETE"
    )

    print()

    print(
        metrics_df.to_string(
            index=False
        )
    )

    print()
    print("=" * 80)
    print("OUTPUT FILES")
    print("=" * 80)

    for p in [
        predictions_path,
        metrics_csv_path,
        district_csv_path,
        metrics_json_path,
    ]:

        print(p)

    print()
    print(
        f"TOTAL RUNTIME: "
        f"{overall_time / 60:.2f} minutes"
    )

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    del (
        df,
        predictions_df,
        district_metrics_df,
        metrics_df,
    )

    gc.collect()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()

