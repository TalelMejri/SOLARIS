"""
PHASE 4.2 — Probabilistic PV forecasting (P10 / P50 / P90)

Chronological LightGBM quantile regression with split-conformal
calibration for well-calibrated prediction intervals.

SPLIT:
    Train      : 2005-2018
    Validation : 2019
    Test       : 2020

TARGET:
    p_pvgis_kw_per_kwp

MODELS:
    Three LightGBM quantile regressors (P10, P50, P90)
    + split-conformal calibration on validation residuals

OUTPUTS:
    models/lightgbm_p10.pkl, lightgbm_p50.pkl, lightgbm_p90.pkl
    data/processed/ml/lightgbm_quantile_test_predictions.parquet
    data/processed/ml/lightgbm_quantile_district_metrics.csv
    data/processed/ml/lightgbm_quantile_metrics.json
    data/processed/ml/lightgbm_quantile_feature_importance.csv
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FEATURES_PATH = (
    PROJECT_ROOT / "data" / "processed" / "features" / "district_features.parquet"
)

MODEL_DIR = PROJECT_ROOT / "models"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "ml"

MODEL_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- FIX 1: correct target name ----
TARGET = "p_pvgis_kw_per_kwp"

TIME_COL = "timestamp"
DISTRICT_COL = "district_id"

TRAIN_START = "2005-01-01"
TRAIN_END = "2018-12-31 23:00:00"

VALID_START = "2019-01-01"
VALID_END = "2019-12-31 23:00:00"

TEST_START = "2020-01-01"
TEST_END = "2020-12-31 23:00:00"

EXPECTED_DISTRICTS = 50
EXPECTED_HOURS_PER_DISTRICT = 166_536

QUANTILES = {"p10": 0.10, "p50": 0.50, "p90": 0.90}


# ============================================================
# FORECAST-SAFE FEATURES
# ============================================================

FORECAST_SAFE_FEATURES = [
    "region_id",
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
    "p_roll_mean_3h",
    "p_roll_std_3h",
    "kt_roll_mean_3h",
    "p_roll_mean_6h",
    "p_roll_std_6h",
    "kt_roll_mean_6h",
    "p_roll_mean_24h",
    "p_roll_std_24h",
    "kt_roll_mean_24h",
    "p_lag_diff_1h_24h",
    "p_lag_diff_24h_168h",
    "kt_lag_diff_1h_24h",
    "region_mean_p_lag",
    "region_mean_kt_lag",
    "national_mean_p_lag",
    "national_mean_kt_lag",
    "p_dev_from_region",
]


# ============================================================
# HELPERS
# ============================================================


def print_section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def pinball_loss(y_true, y_pred, alpha):
    error = y_true - y_pred
    return float(np.mean(np.maximum(alpha * error, (alpha - 1.0) * error)))


def coverage(y_true, lower, upper):
    inside = (y_true >= lower) & (y_true <= upper)
    return float(np.mean(inside))


def mean_interval_width(lower, upper):
    return float(np.mean(upper - lower))


def normalized_interval_width(lower, upper, y_true):
    denom = np.mean(np.abs(y_true))
    if denom <= 1e-12:
        return np.nan
    return float(np.mean(upper - lower) / denom)


def check_required_columns(df, columns):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError("Missing required columns:\n" + "\n".join(missing))


def regression_metrics(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2 = r2_score(y_true, y_pred)
    nonzero = np.abs(y_true) > 1e-6
    if nonzero.any():
        mape = float(
            np.mean(np.abs((y_true[nonzero] - y_pred[nonzero]) / y_true[nonzero]))
            * 100.0
        )
    else:
        mape = np.nan
    return {"MAE": float(mae), "RMSE": rmse, "MAPE_percent": mape, "R2": float(r2)}


def save_pickle(obj, path):
    with open(path, "wb") as f:
        pickle.dump(obj, f)


# ============================================================
# LOAD DATA
# ============================================================

print_section("LOADING DATA")

if not FEATURES_PATH.exists():
    raise FileNotFoundError(f"Features file not found:\n{FEATURES_PATH}")

df = pd.read_parquet(FEATURES_PATH)

print(f"Features path : {FEATURES_PATH}")
print(f"Rows          : {len(df):,}")
print(f"Columns       : {len(df.columns)}")


# ============================================================
# VALIDATION
# ============================================================

print_section("VALIDATING DATA")

check_required_columns(df, [TIME_COL, DISTRICT_COL, TARGET, *FORECAST_SAFE_FEATURES])

df[TIME_COL] = pd.to_datetime(df[TIME_COL])
df = df.sort_values([DISTRICT_COL, TIME_COL]).reset_index(drop=True)

districts = sorted(df[DISTRICT_COL].dropna().unique())
print(f"Districts     : {len(districts)}")
if len(districts) != EXPECTED_DISTRICTS:
    raise ValueError(
        f"Expected {EXPECTED_DISTRICTS} districts, found {len(districts)}."
    )

dup = df.duplicated(subset=[DISTRICT_COL, TIME_COL]).sum()
print(f"Duplicate district/timestamp rows: {dup:,}")
if dup > 0:
    raise ValueError("Duplicate district/timestamp rows detected.")

null_target = df[TARGET].isna().sum()
print(f"Null target rows: {null_target:,}")
if null_target > 0:
    raise ValueError("Target contains NaN values.")

neg_target = (df[TARGET] < 0).sum()
print(f"Negative target rows: {neg_target:,}")
if neg_target > 0:
    raise ValueError("Negative target values detected.")


# ============================================================
# TEMPORAL STRUCTURE
# ============================================================

print_section("CHECKING TEMPORAL STRUCTURE")

district_counts = df.groupby(DISTRICT_COL)[TIME_COL].nunique()
bad = district_counts[district_counts != EXPECTED_HOURS_PER_DISTRICT]

print(f"Expected hours/district : {EXPECTED_HOURS_PER_DISTRICT:,}")
print(f"Actual min              : {district_counts.min():,}")
print(f"Actual max              : {district_counts.max():,}")

if len(bad) > 0:
    print("Districts with invalid hour counts:")
    print(bad)
    raise ValueError("Temporal completeness validation failed.")

print("Temporal structure: OK")


# ============================================================
# LEAKAGE AUDIT
# ============================================================

print_section("LEAKAGE AUDIT")

UNSAFE = {
    "beam_fraction",
    "beam_w_m2",
    "diffuse_fraction",
    "diffuse_w_m2",
    "ghi_w_m2",
    "kt",
    "kt_anomaly_24h",
    "reflected_w_m2",
    "temp_effect_proxy",
    "temperature_2m_c",
    "wind_cooling_proxy",
    "wind_speed_10m_ms",
}

for f in UNSAFE:
    if f in FORECAST_SAFE_FEATURES:
        raise ValueError(f"LEAKAGE: unsafe current feature included: {f}")

if TARGET in FORECAST_SAFE_FEATURES:
    raise ValueError(f"LEAKAGE: target itself is included: {TARGET}")

print("Leakage audit: PASSED")


# ============================================================
# SPLIT
# ============================================================

print_section("CREATING CHRONOLOGICAL SPLIT")

train_df = df[(df[TIME_COL] >= TRAIN_START) & (df[TIME_COL] <= TRAIN_END)].copy()
valid_df = df[(df[TIME_COL] >= VALID_START) & (df[TIME_COL] <= VALID_END)].copy()
test_df = df[(df[TIME_COL] >= TEST_START) & (df[TIME_COL] <= TEST_END)].copy()

print(f"Train      : {len(train_df):,}")
print(f"Validation : {len(valid_df):,}")
print(f"Test       : {len(test_df):,}")

if len(train_df) == 0 or len(valid_df) == 0 or len(test_df) == 0:
    raise ValueError("One or more splits are empty.")

if train_df[TIME_COL].max() >= valid_df[TIME_COL].min():
    raise ValueError("Train/validation overlap detected.")
if valid_df[TIME_COL].max() >= test_df[TIME_COL].min():
    raise ValueError("Validation/test overlap detected.")

print("Chronological separation: OK")


# ============================================================
# FEATURE MATRICES
# ============================================================

X_train = train_df[FORECAST_SAFE_FEATURES].copy()
y_train = train_df[TARGET].to_numpy(dtype=np.float32)

X_valid = valid_df[FORECAST_SAFE_FEATURES].copy()
y_valid = valid_df[TARGET].to_numpy(dtype=np.float32)

X_test = test_df[FORECAST_SAFE_FEATURES].copy()
y_test = test_df[TARGET].to_numpy(dtype=np.float32)

print(f"\nNumber of features: {len(FORECAST_SAFE_FEATURES)}")


# ============================================================
# TRAIN QUANTILE MODELS
# ============================================================

COMMON_PARAMS = {
    "n_estimators": 3000,
    "learning_rate": 0.03,
    "num_leaves": 63,
    "min_child_samples": 50,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "reg_alpha": 0.1,
    "reg_lambda": 0.2,
    "random_state": 42,
    "n_jobs": -1,
    "force_col_wise": True,
    "verbosity": -1,
}

models = {}
predictions = {}

for name, alpha in QUANTILES.items():
    print_section(f"TRAINING {name.upper()} (alpha={alpha:.2f})")

    model = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **COMMON_PARAMS)
    model.fit(
        X_train,
        y_train,
        eval_X=X_valid,
        eval_y=y_valid,
        eval_metric="quantile",
        callbacks=[lgb.early_stopping(stopping_rounds=100, verbose=True)],
    )

    print(f"\n{name.upper()} best iteration: {model.best_iteration_}")

    valid_pred = np.clip(
        model.predict(X_valid, num_iteration=model.best_iteration_), 0.0, None
    )
    test_pred = np.clip(
        model.predict(X_test, num_iteration=model.best_iteration_), 0.0, None
    )

    models[name] = model
    predictions[name] = {"validation": valid_pred, "test": test_pred}


# ============================================================
# QUANTILE CROSSING CHECK
# ============================================================

print_section("QUANTILE CROSSING CHECK")

p10_test_raw = predictions["p10"]["test"]
p50_test_raw = predictions["p50"]["test"]
p90_test_raw = predictions["p90"]["test"]

cross_any = (p10_test_raw > p50_test_raw) | (p50_test_raw > p90_test_raw)
print(f"Raw crossing rows: {cross_any.sum():,}")
print(f"Raw crossing rate: {cross_any.mean()*100:.6f}%")


# ============================================================
# FIX 2: MONOTONICITY VIA CLAMPING (preserves P50)
# ============================================================

print_section("ENFORCING MONOTONICITY (P10 ≤ P50 ≤ P90)")

p10_valid_raw = predictions["p10"]["validation"]
p50_valid_raw = predictions["p50"]["validation"]
p90_valid_raw = predictions["p90"]["validation"]

# Test
p50_test_calculated = p50_test_raw.copy()
p10_test_calculated = np.minimum(p10_test_raw, p50_test_calculated)
p90_test_calculated = np.maximum(p90_test_raw, p50_test_calculated)

# Validation
p50_valid_calculated = p50_valid_raw.copy()
p10_valid_calculated = np.minimum(p10_valid_raw, p50_valid_calculated)
p90_valid_calculated = np.maximum(p90_valid_raw, p50_valid_calculated)

resid = (
    (p10_test_calculated > p50_test_calculated)
    | (p50_test_calculated > p90_test_calculated)
).sum()
print(f"Remaining crossings after monotonicity: {resid}")


# ============================================================
# FIX 3: SPLIT-CONFORMAL CALIBRATION
# ============================================================

print_section("SPLIT-CONFORMAL CALIBRATION")

resid_lower = y_valid - p10_valid_calculated
resid_upper = y_valid - p90_valid_calculated

offset_p10 = float(np.quantile(resid_lower, 0.10))
offset_p90 = float(np.quantile(resid_upper, 0.90))

print(f"P10 conformal offset : {offset_p10:+.6f}")
print(f"P90 conformal offset : {offset_p90:+.6f}")

# Apply to test
p10_test_calculated = np.clip(p10_test_calculated + offset_p10, 0, None)
p90_test_calculated = np.clip(p90_test_calculated + offset_p90, 0, None)
p10_test_calculated = np.minimum(p10_test_calculated, p50_test_calculated)
p90_test_calculated = np.maximum(p90_test_calculated, p50_test_calculated)

# Apply to validation
p10_valid_calculated = np.clip(p10_valid_calculated + offset_p10, 0, None)
p90_valid_calculated = np.clip(p90_valid_calculated + offset_p90, 0, None)
p10_valid_calculated = np.minimum(p10_valid_calculated, p50_valid_calculated)
p90_valid_calculated = np.maximum(p90_valid_calculated, p50_valid_calculated)

val_cov_after = coverage(y_valid, p10_valid_calculated, p90_valid_calculated)
print(f"Validation coverage AFTER calibration : {val_cov_after*100:.2f}%")


# ============================================================
# VALIDATION METRICS
# ============================================================

print_section("VALIDATION METRICS — 2019")
validation_metrics = {}

for name, alpha in QUANTILES.items():
    pred = {
        "p10": p10_valid_calculated,
        "p50": p50_valid_calculated,
        "p90": p90_valid_calculated,
    }[name]
    m = regression_metrics(y_valid, pred)
    m["pinball_loss"] = pinball_loss(y_valid, pred, alpha)
    validation_metrics[name] = m
    print(f"\n{name.upper()}")
    for k, v in m.items():
        print(f"{k:20s}: {v:.8f}")


# ============================================================
# TEST METRICS
# ============================================================

print_section("TEST METRICS — 2020")
test_metrics = {}

for name, alpha in QUANTILES.items():
    pred = {
        "p10": p10_test_calculated,
        "p50": p50_test_calculated,
        "p90": p90_test_calculated,
    }[name]
    m = regression_metrics(y_test, pred)
    m["pinball_loss"] = pinball_loss(y_test, pred, alpha)
    test_metrics[name] = m
    print(f"\n{name.upper()}")
    for k, v in m.items():
        print(f"{k:20s}: {v:.8f}")


# ============================================================
# COVERAGE
# ============================================================

print_section("P10/P90 COVERAGE — 2020")

test_coverage = coverage(y_test, p10_test_calculated, p90_test_calculated)
test_width = mean_interval_width(p10_test_calculated, p90_test_calculated)
test_norm_width = normalized_interval_width(
    p10_test_calculated, p90_test_calculated, y_test
)

print(f"Nominal coverage       : 80.00%")
print(f"Observed coverage      : {test_coverage*100:.4f}%")
print(f"Coverage error         : {(test_coverage-0.80)*100:.4f} pp")
print(f"Mean interval width    : {test_width:.8f}")
print(f"Normalized width       : {test_norm_width:.8f}")


# ============================================================
# DISTRICT METRICS
# ============================================================

print_section("DISTRICT-LEVEL METRICS")

test_eval = test_df[[DISTRICT_COL, TIME_COL]].copy()
test_eval["actual"] = y_test
test_eval["p10"] = p10_test_calculated
test_eval["p50"] = p50_test_calculated
test_eval["p90"] = p90_test_calculated

rows = []
for did, g in test_eval.groupby(DISTRICT_COL):
    a = g["actual"].to_numpy()
    p10 = g["p10"].to_numpy()
    p50 = g["p50"].to_numpy()
    p90 = g["p90"].to_numpy()
    m = regression_metrics(a, p50)
    cov = coverage(a, p10, p90)
    rows.append(
        {
            DISTRICT_COL: did,
            "n": len(g),
            "MAE_P50": m["MAE"],
            "RMSE_P50": m["RMSE"],
            "MAPE_P50_percent": m["MAPE_percent"],
            "R2_P50": m["R2"],
            "pinball_P10": pinball_loss(a, p10, 0.10),
            "pinball_P50": pinball_loss(a, p50, 0.50),
            "pinball_P90": pinball_loss(a, p90, 0.90),
            "coverage_P10_P90": cov,
            "coverage_error_pp": (cov - 0.80) * 100.0,
            "mean_interval_width": mean_interval_width(p10, p90),
        }
    )

district_metrics_df = (
    pd.DataFrame(rows).sort_values(DISTRICT_COL).reset_index(drop=True)
)
print(district_metrics_df.to_string(index=False))


# ============================================================
# SUMMARY
# ============================================================

print_section("OVERALL PROBABILISTIC SUMMARY")

summary = {
    "test_period": "2020",
    "n_test": int(len(test_df)),
    "n_districts": int(len(districts)),
    "p10_pinball_loss": float(test_metrics["p10"]["pinball_loss"]),
    "p50_pinball_loss": float(test_metrics["p50"]["pinball_loss"]),
    "p90_pinball_loss": float(test_metrics["p90"]["pinball_loss"]),
    "p50_MAE": float(test_metrics["p50"]["MAE"]),
    "p50_RMSE": float(test_metrics["p50"]["RMSE"]),
    "p50_R2": float(test_metrics["p50"]["R2"]),
    "p10_p90_nominal_coverage": 0.80,
    "p10_p90_observed_coverage": float(test_coverage),
    "coverage_error_pp": float((test_coverage - 0.80) * 100.0),
    "mean_interval_width": float(test_width),
    "normalized_interval_width": float(test_norm_width),
    "conformal_offsets": {"p10": offset_p10, "p90": offset_p90},
    "calibration_method": "split_conformal",
}
print(json.dumps(summary, indent=2))


# ============================================================
# SAVE
# ============================================================

print_section("SAVING OUTPUTS")

prediction_df = test_df[[DISTRICT_COL, TIME_COL]].copy()
prediction_df["actual_p_kw_per_kwp"] = y_test
prediction_df["p10_kw_per_kwp"] = p10_test_calculated
prediction_df["p50_kw_per_kwp"] = p50_test_calculated
prediction_df["p90_kw_per_kwp"] = p90_test_calculated
prediction_df["interval_width_kw_per_kwp"] = (
    prediction_df["p90_kw_per_kwp"] - prediction_df["p10_kw_per_kwp"]
)

prediction_path = OUTPUT_DIR / "lightgbm_quantile_test_predictions.parquet"
prediction_df.to_parquet(prediction_path, index=False)
print(f"Saved: {prediction_path}")

district_path = OUTPUT_DIR / "lightgbm_quantile_district_metrics.csv"
district_metrics_df.to_csv(district_path, index=False)
print(f"Saved: {district_path}")

metrics_path = OUTPUT_DIR / "lightgbm_quantile_metrics.json"
with open(metrics_path, "w") as f:
    json.dump(
        {
            "configuration": {
                "target": TARGET,
                "features": FORECAST_SAFE_FEATURES,
                "train_period": [TRAIN_START, TRAIN_END],
                "validation_period": [VALID_START, VALID_END],
                "test_period": [TEST_START, TEST_END],
                "quantiles": QUANTILES,
            },
            "validation": validation_metrics,
            "test": test_metrics,
            "probabilistic_summary": summary,
        },
        f,
        indent=2,
    )
print(f"Saved: {metrics_path}")

importance_frames = []
for name, model in models.items():
    imp = pd.DataFrame(
        {
            "feature": FORECAST_SAFE_FEATURES,
            "gain": model.booster_.feature_importance(importance_type="gain"),
            "split": model.booster_.feature_importance(importance_type="split"),
        }
    )
    imp["quantile"] = name
    importance_frames.append(imp)

importance_df = pd.concat(importance_frames, ignore_index=True)
importance_path = OUTPUT_DIR / "lightgbm_quantile_feature_importance.csv"
importance_df.to_csv(importance_path, index=False)
print(f"Saved: {importance_path}")

model_paths = {}
for name, model in models.items():
    p = MODEL_DIR / f"lightgbm_{name}.pkl"
    save_pickle(model, p)
    model_paths[name] = str(p)
    print(f"Model saved: {p}")

feature_list_path = MODEL_DIR / "lightgbm_quantile_features.json"
with open(feature_list_path, "w") as f:
    json.dump(FORECAST_SAFE_FEATURES, f, indent=2)
print(f"Saved: {feature_list_path}")


# ============================================================
# FINAL SUMMARY
# ============================================================

print_section("PHASE 4.2 COMPLETE")

print(f"2020 P50 R²                : {summary['p50_R2']:.6f}")
print(f"2020 P50 RMSE              : {summary['p50_RMSE']:.6f} kW/kWp")
print(
    f"P10-P90 observed coverage  : {summary['p10_p90_observed_coverage']*100:.4f}% (target 80%)"
)
print(f"Mean interval width        : {summary['mean_interval_width']:.6f}")
print(f"Residual crossings         : {resid}")
print()
print("Output files:")
for p in [
    prediction_path,
    district_path,
    metrics_path,
    importance_path,
    feature_list_path,
]:
    print(f"  {p}")
for name, p in model_paths.items():
    print(f"  {name}: {p}")
