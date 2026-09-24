"""
PHASE 3.2 + 3.3
Leakage-Safe Chronological LightGBM PV Forecasting

============================================================

PROJECT:
    Prosol Forecast — Tunisia Rooftop PV Forecasting

TARGET:
    p_pvgis_kw_per_kwp

TEMPORAL SPLIT:
    Train      : 2005-2018
    Validation : 2019
    Test       : 2020

MODEL:
    LightGBM Regressor

BASELINE:
    Persistence:
        prediction(t) = target(t - 1 hour)

IMPORTANT:
    This version is designed for a TRUE forecasting benchmark.

    It DOES NOT use:
        - current-hour actual GHI
        - current-hour actual beam irradiance
        - current-hour actual diffuse irradiance
        - current-hour actual reflected irradiance
        - current-hour actual temperature
        - current-hour actual wind
        - current-hour actual kt
        - current-hour target
        - any direct target difference

    It DOES use:
        - historical target lags
        - historical weather lags
        - historical kt lags
        - past rolling statistics
        - calendar features
        - solar geometry
        - clear-sky irradiance
        - historical spatial aggregates shifted into the past

NO:
    - random split
    - synthetic data
    - future actual weather
    - target leakage
    - test-set model selection

METRICS:
    MAE
    RMSE
    MAPE
    R2
    Skill Score vs Persistence

============================================================
"""

from pathlib import Path
import json
import warnings

import joblib
import numpy as np
import pandas as pd

from lightgbm import LGBMRegressor, early_stopping, log_evaluation

from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)


warnings.filterwarnings("ignore")


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "features"
    / "district_features.parquet"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
)

MODEL_DIR = PROJECT_ROOT / "models"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


MODEL_FILE = (
    MODEL_DIR
    / "lightgbm_pv_forecast_safe.pkl"
)

FEATURE_FILE = (
    MODEL_DIR
    / "lightgbm_forecast_safe_features.json"
)

METRICS_FILE = (
    OUTPUT_DIR
    / "lightgbm_forecast_safe_metrics.json"
)

PREDICTIONS_FILE = (
    OUTPUT_DIR
    / "lightgbm_forecast_safe_test_predictions.parquet"
)

DISTRICT_METRICS_FILE = (
    OUTPUT_DIR
    / "lightgbm_forecast_safe_district_metrics.csv"
)

FEATURE_IMPORTANCE_FILE = (
    OUTPUT_DIR
    / "lightgbm_forecast_safe_feature_importance.csv"
)


# ============================================================
# CONFIG
# ============================================================

TARGET = "p_pvgis_kw_per_kwp"

TRAIN_START = pd.Timestamp("2005-01-01")
TRAIN_END = pd.Timestamp("2018-12-31 23:59:59")

VALIDATION_START = pd.Timestamp("2019-01-01")
VALIDATION_END = pd.Timestamp("2019-12-31 23:59:59")

TEST_START = pd.Timestamp("2020-01-01")
TEST_END = pd.Timestamp("2020-12-31 23:59:59")

MAPE_THRESHOLD = 0.01

RANDOM_STATE = 42

N_ESTIMATORS = 3000

LEARNING_RATE = 0.03

NUM_LEAVES = 63

MAX_DEPTH = -1

MIN_CHILD_SAMPLES = 50

SUBSAMPLE = 0.85

COLSAMPLE_BYTREE = 0.85

REG_ALPHA = 0.1

REG_LAMBDA = 0.2

EARLY_STOPPING_ROUNDS = 100


# ============================================================
# FEATURES THAT ARE NOT AVAILABLE AT FORECAST ISSUE TIME
# ============================================================

CURRENT_WEATHER_FEATURES = {
    "ghi_w_m2",
    "beam_w_m2",
    "diffuse_w_m2",
    "reflected_w_m2",
    "temperature_2m_c",
    "wind_speed_10m_ms",
    "kt",
    "beam_fraction",
    "diffuse_fraction",
    "temp_effect_proxy",
    "wind_cooling_proxy",
    "kt_anomaly_24h",
}


# Additional potentially unsafe feature prefixes.

UNSAFE_PREFIXES = (
    "current_",
)


# ============================================================
# LOAD DATA
# ============================================================

def load_data():

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"""
Feature dataset not found:

{INPUT_FILE}

Run Phase 3.1 first.
"""
        )

    print("\nLoading feature dataset...")

    df = pd.read_parquet(INPUT_FILE)

    print(f"Raw rows: {len(df):,}")
    print(f"Raw columns: {len(df.columns)}")

    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="raise",
    )

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    df = (
        df
        .sort_values(
            [
                "district_id",
                "timestamp",
            ]
        )
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    required = {
        "district_id",
        "timestamp",
        TARGET,
    }

    missing = required - set(df.columns)

    if missing:

        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    # --------------------------------------------------------
    # District validation
    # --------------------------------------------------------

    district_count = df["district_id"].nunique()

    if district_count != 50:

        raise ValueError(
            f"Expected 50 districts, found {district_count}."
        )

    # --------------------------------------------------------
    # Duplicate validation
    # --------------------------------------------------------

    duplicates = df.duplicated(
        [
            "district_id",
            "timestamp",
        ]
    )

    if duplicates.any():

        raise ValueError(
            f"Found {duplicates.sum():,} duplicate "
            "district/timestamp rows."
        )

    # --------------------------------------------------------
    # Target validation
    # --------------------------------------------------------

    if df[TARGET].isna().any():

        raise ValueError(
            "Target contains missing values."
        )

    if not np.isfinite(
        df[TARGET].to_numpy()
    ).all():

        raise ValueError(
            "Target contains infinite values."
        )

    if (df[TARGET] < 0).any():

        raise ValueError(
            "Target contains negative values."
        )

    # --------------------------------------------------------
    # Print
    # --------------------------------------------------------

    print(f"Rows      : {len(df):,}")
    print(f"Districts : {district_count}")
    print(f"Start     : {df['timestamp'].min()}")
    print(f"End       : {df['timestamp'].max()}")

    return df


# ============================================================
# CHECK HOURLY STRUCTURE
# ============================================================

def validate_hourly_structure(df):

    print("\nValidating hourly structure...")

    expected_hours = len(
        pd.date_range(
            df["timestamp"].min(),
            df["timestamp"].max(),
            freq="h",
        )
    )

    counts = (
        df
        .groupby("district_id")
        .size()
    )

    invalid = counts[
        counts != expected_hours
    ]

    if len(invalid) > 0:

        print("\nWARNING:")
        print(
            "Some districts do not have the complete "
            "hourly timeline."
        )

        print(invalid)

        raise ValueError(
            "Hourly structure is incomplete. "
            "Do not create synthetic rows."
        )

    print(
        f"✓ Each district contains "
        f"{expected_hours:,} hourly rows."
    )


# ============================================================
# DATE RANGE CHECK
# ============================================================

def check_date_range(df):

    actual_start = df["timestamp"].min()

    actual_end = df["timestamp"].max()

    print("\nAvailable data:")
    print(f"Start: {actual_start}")
    print(f"End  : {actual_end}")

    if actual_start > TRAIN_START:

        raise ValueError(
            f"""
Dataset does not start early enough.

Required:
{TRAIN_START}

Actual:
{actual_start}

Do NOT create synthetic data.
"""
        )

    if actual_end < TEST_END:

        raise ValueError(
            f"""
Dataset does not contain the complete test period.

Required:
{TEST_END}

Actual:
{actual_end}

Do NOT create missing years.
"""
        )

    required_years = {
        2018,
        2019,
        2020,
    }

    available_years = set(
        df["timestamp"]
        .dt.year
        .unique()
    )

    missing = sorted(
        required_years - available_years
    )

    if missing:

        raise ValueError(
            f"Missing required years: {missing}"
        )

    print(
        "\n✓ Benchmark period 2005-2020 available."
    )


# ============================================================
# PERSISTENCE BASELINE
# ============================================================

def add_persistence_baseline(df):

    """
    Exact persistence:

        P(t) = target(t-1h)

    Created BEFORE temporal splitting.
    """

    print(
        "\nCreating exact 1-hour "
        "persistence baseline..."
    )

    previous = df[
        [
            "district_id",
            "timestamp",
            TARGET,
        ]
    ].copy()

    previous["timestamp"] = (
        previous["timestamp"]
        + pd.Timedelta(hours=1)
    )

    previous = previous.rename(
        columns={
            TARGET:
            "persistence_prediction"
        }
    )

    df = df.merge(
        previous,
        on=[
            "district_id",
            "timestamp",
        ],
        how="left",
        validate="one_to_one",
    )

    print(
        "Persistence valid rows:",
        df["persistence_prediction"]
        .notna()
        .sum(),
    )

    return df


# ============================================================
# TEMPORAL SPLIT
# ============================================================

def create_splits(df):

    train = df[
        (df["timestamp"] >= TRAIN_START)
        &
        (df["timestamp"] <= TRAIN_END)
    ].copy()

    validation = df[
        (df["timestamp"] >= VALIDATION_START)
        &
        (df["timestamp"] <= VALIDATION_END)
    ].copy()

    test = df[
        (df["timestamp"] >= TEST_START)
        &
        (df["timestamp"] <= TEST_END)
    ].copy()

    if train.empty:
        raise ValueError(
            "Training set is empty."
        )

    if validation.empty:
        raise ValueError(
            "Validation set is empty."
        )

    if test.empty:
        raise ValueError(
            "Test set is empty."
        )

    print("\n" + "=" * 70)
    print("CHRONOLOGICAL SPLIT")
    print("=" * 70)

    print(
        f"Train      : {len(train):,}"
    )

    print(
        f"Validation : {len(validation):,}"
    )

    print(
        f"Test       : {len(test):,}"
    )

    print(
        f"\nTrain:"
        f" {train['timestamp'].min()}"
        f" → "
        f"{train['timestamp'].max()}"
    )

    print(
        f"Validation:"
        f" {validation['timestamp'].min()}"
        f" → "
        f"{validation['timestamp'].max()}"
    )

    print(
        f"Test:"
        f" {test['timestamp'].min()}"
        f" → "
        f"{test['timestamp'].max()}"
    )

    # --------------------------------------------------------
    # Verify no overlap
    # --------------------------------------------------------

    if train["timestamp"].max() >= validation["timestamp"].min():

        raise ValueError(
            "Train/validation temporal overlap detected."
        )

    if validation["timestamp"].max() >= test["timestamp"].min():

        raise ValueError(
            "Validation/test temporal overlap detected."
        )

    print(
        "\n✓ No temporal overlap."
    )

    return train, validation, test


# ============================================================
# FEATURE SAFETY
# ============================================================

def is_forecast_safe_feature(feature):

    # --------------------------------------------------------
    # Direct target
    # --------------------------------------------------------

    if feature == TARGET:
        return False

    # --------------------------------------------------------
    # Current weather / irradiance
    # --------------------------------------------------------

    if feature in CURRENT_WEATHER_FEATURES:
        return False

    # --------------------------------------------------------
    # Unsafe prefixes
    # --------------------------------------------------------

    for prefix in UNSAFE_PREFIXES:

        if feature.startswith(prefix):
            return False

    # --------------------------------------------------------
    # Direct target-like features
    # --------------------------------------------------------

    forbidden_exact = {
        "p_diff_1h",
        "p_diff_24h",
        "kt_diff_1h",
        "target",
        "target_current",
        "actual_target",
    }

    if feature in forbidden_exact:
        return False

    # --------------------------------------------------------
    # Any direct current target construction
    # --------------------------------------------------------

    if feature.startswith("p_diff_"):
        return False

    return True


# ============================================================
# GET MODEL FEATURES
# ============================================================

def get_features(df):

    excluded_metadata = {
        TARGET,
        "estimated_power_mw",
        "timestamp",
        "district_name",
        "region_name",
        "capacity_source",
        "pv_reference",
        "district_id",
        "latitude",
        "longitude",
        "capacity_mw",
        "persistence_prediction",
    }

    candidates = []

    for column in df.columns:

        if column in excluded_metadata:
            continue

        if not pd.api.types.is_numeric_dtype(
            df[column]
        ):
            continue

        candidates.append(column)

    # --------------------------------------------------------
    # Forecast-safe filter
    # --------------------------------------------------------

    features = [
        column
        for column in candidates
        if is_forecast_safe_feature(column)
    ]

    if not features:

        raise ValueError(
            "No forecast-safe numeric features found."
        )

    # --------------------------------------------------------
    # Forbidden leakage check
    # --------------------------------------------------------

    forbidden = {
        TARGET,
        "p_diff_1h",
        "p_diff_24h",
        "kt_diff_1h",
        "persistence_prediction",
    }

    leakage = (
        set(features)
        &
        forbidden
    )

    if leakage:

        raise ValueError(
            f"LEAKAGE DETECTED in features: "
            f"{sorted(leakage)}"
        )

    # --------------------------------------------------------
    # Print removed columns
    # --------------------------------------------------------

    removed = sorted(
        set(candidates) - set(features)
    )

    print("\n" + "=" * 70)
    print("FEATURE SELECTION")
    print("=" * 70)

    print(
        f"Candidate numeric features : "
        f"{len(candidates)}"
    )

    print(
        f"Forecast-safe features     : "
        f"{len(features)}"
    )

    print(
        f"Removed unsafe features    : "
        f"{len(removed)}"
    )

    print("\nRemoved from forecasting:")

    for feature in removed:

        print(
            f"  ✗ {feature}"
        )

    print("\nForecast-safe features:")

    for feature in features:

        print(
            f"  ✓ {feature}"
        )

    return features


# ============================================================
# FINAL LEAKAGE AUDIT
# ============================================================

def leakage_audit(features):

    print("\n" + "=" * 70)
    print("LEAKAGE AUDIT")
    print("=" * 70)

    forbidden_patterns = [
        "p_diff_",
        "target_current",
        "actual_target",
    ]

    errors = []

    for feature in features:

        if feature == TARGET:

            errors.append(feature)

        for pattern in forbidden_patterns:

            if feature.startswith(pattern):

                errors.append(feature)

    if errors:

        raise ValueError(
            "Potential target leakage detected:\n"
            + "\n".join(
                f"  {x}" for x in sorted(set(errors))
            )
        )

    print(
        "✓ No direct target leakage detected."
    )

    print(
        "✓ Current target-difference features absent."
    )

    print(
        "✓ Persistence excluded from model features."
    )


# ============================================================
# PREPARE MATRICES
# ============================================================

def prepare_xy(
    train,
    validation,
    test,
    features,
):

    X_train = train[features]
    y_train = train[TARGET]

    X_validation = validation[features]
    y_validation = validation[TARGET]

    X_test = test[features]
    y_test = test[TARGET]

    return (
        X_train,
        y_train,
        X_validation,
        y_validation,
        X_test,
        y_test,
    )


# ============================================================
# MAPE
# ============================================================

def calculate_mape(
    y_true,
    y_pred,
    threshold=MAPE_THRESHOLD,
):

    y_true = np.asarray(
        y_true,
        dtype=float,
    )

    y_pred = np.asarray(
        y_pred,
        dtype=float,
    )

    mask = (
        np.isfinite(y_true)
        &
        np.isfinite(y_pred)
        &
        (np.abs(y_true) >= threshold)
    )

    if mask.sum() == 0:

        return np.nan

    return (
        np.mean(
            np.abs(
                (
                    y_true[mask]
                    - y_pred[mask]
                )
                /
                y_true[mask]
            )
        )
        * 100
    )


# ============================================================
# METRICS
# ============================================================

def calculate_metrics(
    y_true,
    y_pred,
):

    y_true = np.asarray(
        y_true,
        dtype=float,
    )

    y_pred = np.asarray(
        y_pred,
        dtype=float,
    )

    valid = (
        np.isfinite(y_true)
        &
        np.isfinite(y_pred)
    )

    y_true = y_true[valid]
    y_pred = y_pred[valid]

    if len(y_true) == 0:

        return {
            "MAE": None,
            "RMSE": None,
            "MAPE_percent": None,
            "R2": None,
            "n_samples": 0,
        }

    mae = mean_absolute_error(
        y_true,
        y_pred,
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_true,
            y_pred,
        )
    )

    mape = calculate_mape(
        y_true,
        y_pred,
    )

    r2 = r2_score(
        y_true,
        y_pred,
    )

    return {
        "MAE": float(mae),
        "RMSE": float(rmse),
        "MAPE_percent": (
            float(mape)
            if np.isfinite(mape)
            else None
        ),
        "R2": float(r2),
        "n_samples": int(len(y_true)),
    }


# ============================================================
# SKILL SCORE
# ============================================================

def skill_score(
    model_rmse,
    baseline_rmse,
):

    if (
        model_rmse is None
        or baseline_rmse is None
        or baseline_rmse == 0
    ):

        return np.nan

    return (
        1
        -
        (
            model_rmse
            /
            baseline_rmse
        )
    )


# ============================================================
# TRAIN LIGHTGBM
# ============================================================

def train_model(
    X_train,
    y_train,
    X_validation,
    y_validation,
):

    print("\n" + "=" * 70)
    print("TRAINING LIGHTGBM")
    print("=" * 70)

    print(
        f"Training rows   : {len(X_train):,}"
    )

    print(
        f"Validation rows : {len(X_validation):,}"
    )

    print(
        f"Features        : {X_train.shape[1]}"
    )

    model = LGBMRegressor(

        objective="regression",

        n_estimators=N_ESTIMATORS,

        learning_rate=LEARNING_RATE,

        num_leaves=NUM_LEAVES,

        max_depth=MAX_DEPTH,

        min_child_samples=MIN_CHILD_SAMPLES,

        subsample=SUBSAMPLE,

        subsample_freq=1,

        colsample_bytree=COLSAMPLE_BYTREE,

        reg_alpha=REG_ALPHA,

        reg_lambda=REG_LAMBDA,

        random_state=RANDOM_STATE,

        n_jobs=-1,

        verbosity=-1,

        force_col_wise=True,
    )

    model.fit(

        X_train,

        y_train,

        eval_set=[
            (
                X_validation,
                y_validation,
            )
        ],

        eval_names=[
            "validation"
        ],

        eval_metric="rmse",

        callbacks=[
            early_stopping(
                stopping_rounds=EARLY_STOPPING_ROUNDS,
                verbose=True,
            ),

            log_evaluation(
                period=100
            ),
        ],
    )

    print("\n" + "=" * 70)
    print("LIGHTGBM TRAINING COMPLETE")
    print("=" * 70)

    print(
        "Best iteration:",
        model.best_iteration_,
    )

    print(
        "Best validation RMSE:",
        model.best_score_[
            "validation"
        ][
            "rmse"
        ],
    )

    return model


# ============================================================
# PREDICTIONS
# ============================================================

def generate_predictions(
    model,
    validation,
    test,
    features,
):

    print("\nGenerating predictions...")

    validation_pred = model.predict(
        validation[features],
        num_iteration=model.best_iteration_,
    )

    test_pred = model.predict(
        test[features],
        num_iteration=model.best_iteration_,
    )

    # PV production cannot physically be negative.
    validation_pred = np.maximum(
        validation_pred,
        0,
    )

    test_pred = np.maximum(
        test_pred,
        0,
    )

    return (
        validation_pred,
        test_pred,
    )


# ============================================================
# EVALUATE
# ============================================================

def evaluate_model(
    validation,
    test,
    validation_pred,
    test_pred,
):

    print("\n" + "=" * 70)
    print("MODEL EVALUATION")
    print("=" * 70)

    # --------------------------------------------------------
    # Persistence
    # --------------------------------------------------------

    validation_persistence = (
        validation[
            "persistence_prediction"
        ]
    )

    test_persistence = (
        test[
            "persistence_prediction"
        ]
    )

    # --------------------------------------------------------
    # Valid persistence rows
    # --------------------------------------------------------

    validation_mask = (
        validation_persistence.notna()
    )

    test_mask = (
        test_persistence.notna()
    )

    # --------------------------------------------------------
    # Persistence metrics
    # --------------------------------------------------------

    validation_persistence_metrics = (
        calculate_metrics(
            validation.loc[
                validation_mask,
                TARGET,
            ],
            validation.loc[
                validation_mask,
                "persistence_prediction",
            ],
        )
    )

    test_persistence_metrics = (
        calculate_metrics(
            test.loc[
                test_mask,
                TARGET,
            ],
            test.loc[
                test_mask,
                "persistence_prediction",
            ],
        )
    )

    # --------------------------------------------------------
    # Model metrics
    # --------------------------------------------------------

    validation_model_metrics = (
        calculate_metrics(
            validation[TARGET],
            validation_pred,
        )
    )

    test_model_metrics = (
        calculate_metrics(
            test[TARGET],
            test_pred,
        )
    )

    # --------------------------------------------------------
    # Skill
    # --------------------------------------------------------

    validation_skill = skill_score(
        validation_model_metrics["RMSE"],
        validation_persistence_metrics["RMSE"],
    )

    test_skill = skill_score(
        test_model_metrics["RMSE"],
        test_persistence_metrics["RMSE"],
    )

    # --------------------------------------------------------
    # Validation output
    # --------------------------------------------------------

    print("\n" + "-" * 70)
    print("VALIDATION — 2019")
    print("-" * 70)

    print("\nPersistence:")

    for key, value in (
        validation_persistence_metrics.items()
    ):

        print(
            f"  {key}: {value}"
        )

    print("\nLightGBM:")

    for key, value in (
        validation_model_metrics.items()
    ):

        print(
            f"  {key}: {value}"
        )

    print(
        f"\nSkill Score vs Persistence: "
        f"{validation_skill:.6f}"
    )

    # --------------------------------------------------------
    # Test output
    # --------------------------------------------------------

    print("\n" + "-" * 70)
    print("FINAL TEST — 2020")
    print("-" * 70)

    print("\nPersistence:")

    for key, value in (
        test_persistence_metrics.items()
    ):

        print(
            f"  {key}: {value}"
        )

    print("\nLightGBM:")

    for key, value in (
        test_model_metrics.items()
    ):

        print(
            f"  {key}: {value}"
        )

    print(
        f"\nSkill Score vs Persistence: "
        f"{test_skill:.6f}"
    )

    return {
        "validation": {
            "persistence":
                validation_persistence_metrics,

            "lightgbm":
                validation_model_metrics,

            "skill_score_vs_persistence":
                float(validation_skill),
        },

        "test": {
            "persistence":
                test_persistence_metrics,

            "lightgbm":
                test_model_metrics,

            "skill_score_vs_persistence":
                float(test_skill),
        },

        "test_persistence":
            test_persistence.to_numpy(),
    }


# ============================================================
# DISTRICT METRICS
# ============================================================

def calculate_district_metrics(
    test,
    predictions,
    persistence,
):

    rows = []

    evaluation = test[
        [
            "district_id",
            "district_name",
            TARGET,
        ]
    ].copy()

    evaluation[
        "prediction"
    ] = predictions

    evaluation[
        "persistence_prediction"
    ] = persistence

    for district_id, group in (
        evaluation.groupby(
            "district_id"
        )
    ):

        model_metrics = calculate_metrics(
            group[TARGET],
            group["prediction"],
        )

        persistence_metrics = calculate_metrics(
            group[TARGET],
            group["persistence_prediction"],
        )

        skill = skill_score(
            model_metrics["RMSE"],
            persistence_metrics["RMSE"],
        )

        rows.append(
            {
                "district_id":
                    int(district_id),

                "district_name":
                    group[
                        "district_name"
                    ].iloc[0],

                "MAE":
                    model_metrics["MAE"],

                "RMSE":
                    model_metrics["RMSE"],

                "MAPE_percent":
                    model_metrics[
                        "MAPE_percent"
                    ],

                "R2":
                    model_metrics["R2"],

                "persistence_RMSE":
                    persistence_metrics[
                        "RMSE"
                    ],

                "skill_score_vs_persistence":
                    (
                        float(skill)
                        if np.isfinite(skill)
                        else None
                    ),
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# SAVE FEATURE IMPORTANCE
# ============================================================

def save_feature_importance(
    model,
    features,
):

    importance = pd.DataFrame(
        {
            "feature": features,
            "importance_gain":
                model.booster_.feature_importance(
                    importance_type="gain"
                ),
            "importance_split":
                model.booster_.feature_importance(
                    importance_type="split"
                ),
        }
    )

    importance = (
        importance
        .sort_values(
            "importance_gain",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    importance.to_csv(
        FEATURE_IMPORTANCE_FILE,
        index=False,
    )

    print(
        f"\nFeature importance saved:"
        f"\n{FEATURE_IMPORTANCE_FILE}"
    )

    print("\nTop 20 features:")

    print(
        importance.head(20).to_string(
            index=False
        )
    )

    return importance


# ============================================================
# SAVE PREDICTIONS
# ============================================================

def save_predictions(
    test,
    predictions,
    persistence,
):

    output = test[
        [
            "timestamp",
            "district_id",
            "district_name",
            "region_id",
            "region_name",
            TARGET,
        ]
    ].copy()

    output[
        "lightgbm_prediction"
    ] = predictions

    output[
        "persistence_prediction"
    ] = persistence

    output.to_parquet(
        PREDICTIONS_FILE,
        index=False,
    )

    print(
        f"\nTest predictions saved:"
        f"\n{PREDICTIONS_FILE}"
    )


# ============================================================
# SAVE METRICS
# ============================================================

def save_metrics(
    model,
    features,
    results,
):

    metrics_to_save = {

        "experiment":
            "forecast_safe_lightgbm",

        "target":
            TARGET,

        "model":
            "LightGBMRegressor",

        "best_iteration":
            int(
                model.best_iteration_
            ),

        "split": {

            "train":
                "2005-2018",

            "validation":
                "2019",

            "test":
                "2020",
        },

        "features":
            features,

        "n_features":
            len(features),

        "mape_threshold":
            MAPE_THRESHOLD,

        "results":
            results,

        "baseline":
            "Persistence: target(t-1h)",

        "random_split":
            False,

        "synthetic_data":
            False,

        "test_used_for_model_selection":
            False,

        "forecast_safe":
            True,

        "current_actual_weather_used":
            False,

        "current_target_used":
            False,

        "target_difference_leakage":
            False,

        "note":
            (
                "This is a historical "
                "PV-only forecasting benchmark "
                "using information available "
                "before the prediction timestamp. "
                "Genuine NWP/weather forecast "
                "variables are not yet included. "
                "The final operational model should "
                "replace/add weather lag variables "
                "with genuine forecast weather "
                "available at forecast issue time."
            ),
    }

    with open(
        METRICS_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            metrics_to_save,
            f,
            indent=2,
        )

    print(
        f"\nMetrics saved:"
        f"\n{METRICS_FILE}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)

    print(
        "PHASE 3.2 + 3.3"
    )

    print(
        "LEAKAGE-SAFE LIGHTGBM "
        "PV FORECASTING"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    df = load_data()

    # --------------------------------------------------------
    # HOURLY STRUCTURE
    # --------------------------------------------------------

    validate_hourly_structure(df)

    # --------------------------------------------------------
    # DATE RANGE
    # --------------------------------------------------------

    check_date_range(df)

    # --------------------------------------------------------
    # PERSISTENCE BEFORE SPLIT
    # --------------------------------------------------------

    df = add_persistence_baseline(
        df
    )

    # --------------------------------------------------------
    # SPLIT
    # --------------------------------------------------------

    train, validation, test = (
        create_splits(df)
    )

    # --------------------------------------------------------
    # FEATURES
    # --------------------------------------------------------

    features = get_features(df)

    # --------------------------------------------------------
    # LEAKAGE AUDIT
    # --------------------------------------------------------

    leakage_audit(features)

    # --------------------------------------------------------
    # PREPARE
    # --------------------------------------------------------

    (
        X_train,
        y_train,
        X_validation,
        y_validation,
        X_test,
        y_test,
    ) = prepare_xy(
        train,
        validation,
        test,
        features,
    )

    # --------------------------------------------------------
    # TRAIN
    # --------------------------------------------------------

    model = train_model(
        X_train,
        y_train,
        X_validation,
        y_validation,
    )

    # --------------------------------------------------------
    # PREDICTIONS
    # --------------------------------------------------------

    (
        validation_pred,
        test_pred,
    ) = generate_predictions(
        model,
        validation,
        test,
        features,
    )

    # --------------------------------------------------------
    # EVALUATE
    # --------------------------------------------------------

    results = evaluate_model(
        validation,
        test,
        validation_pred,
        test_pred,
    )

    # ========================================================
    # SAVE MODEL
    # ========================================================

    print("\nSaving model...")

    joblib.dump(
        model,
        MODEL_FILE,
    )

    print(
        f"Model saved:"
        f"\n{MODEL_FILE}"
    )

    # ========================================================
    # SAVE FEATURES
    # ========================================================

    feature_metadata = {

        "target":
            TARGET,

        "features":
            features,

        "n_features":
            len(features),

        "forecast_safe":
            True,

        "current_actual_weather_used":
            False,

        "current_target_used":
            False,

        "persistence_used_as_feature":
            False,

        "split": {

            "train":
                "2005-2018",

            "validation":
                "2019",

            "test":
                "2020",
        },
    }

    with open(
        FEATURE_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            feature_metadata,
            f,
            indent=2,
        )

    print(
        f"\nFeature list saved:"
        f"\n{FEATURE_FILE}"
    )

    # ========================================================
    # TEST PREDICTIONS
    # ========================================================

    save_predictions(
        test,
        test_pred,
        results["test_persistence"],
    )

    # ========================================================
    # DISTRICT METRICS
    # ========================================================

    district_metrics = (
        calculate_district_metrics(
            test,
            test_pred,
            results["test_persistence"],
        )
    )

    district_metrics.to_csv(
        DISTRICT_METRICS_FILE,
        index=False,
    )

    print(
        f"\nDistrict metrics saved:"
        f"\n{DISTRICT_METRICS_FILE}"
    )

    # ========================================================
    # FEATURE IMPORTANCE
    # ========================================================

    save_feature_importance(
        model,
        features,
    )

    # ========================================================
    # METRICS
    # ========================================================

    save_metrics(
        model,
        features,
        {
            "validation":
                results["validation"],

            "test":
                results["test"],
        },
    )

    # ========================================================
    # FINAL
    # ========================================================

    print("\n" + "=" * 70)

    print(
        "PHASE 3.2 + 3.3 COMPLETE"
    )

    print("=" * 70)

    print(
        "\n✓ Chronological split"
    )

    print(
        "✓ 2005-2018 training"
    )

    print(
        "✓ 2019 validation"
    )

    print(
        "✓ 2020 final test"
    )

    print(
        "✓ Exact t-1h persistence"
    )

    print(
        "✓ Validation early stopping"
    )

    print(
        "✓ No random split"
    )

    print(
        "✓ No synthetic data"
    )

    print(
        "✓ No current target leakage"
    )

    print(
        "✓ No current actual weather leakage"
    )

    print(
        "✓ Forecast-safe features"
    )

    print(
        "✓ MAE"
    )

    print(
        "✓ RMSE"
    )

    print(
        "✓ MAPE"
    )

    print(
        "✓ R²"
    )

    print(
        "✓ Skill score vs persistence"
    )

    print(
        "✓ District-level evaluation"
    )

    print(
        "✓ Feature importance"
    )

    print(
        "\nNext phase:"
    )

    print(
        "Probabilistic forecasting:"
    )

    print(
        "P10 / P50 / P90"
    )

    print(
        "\nAfter that:"
    )

    print(
        "Genuine weather/NWP forecast integration"
    )

    print(
        "→ district forecast"
    )

    print(
        "→ regional aggregation"
    )

    print(
        "→ national PV forecast"
    )


if __name__ == "__main__":

    main()