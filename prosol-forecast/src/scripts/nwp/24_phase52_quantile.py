from pathlib import Path
import json

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import mean_pinball_loss, mean_absolute_error


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATASET_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "nwp"
    / "phase52_training_dataset.parquet"
)

FEATURES_FILE = (
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
    / "phase52"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PREDICTIONS_FILE = OUTPUT_DIR / "phase52_quantile_predictions.parquet"
METRICS_FILE = OUTPUT_DIR / "phase52_quantile_metrics.json"
IMPORTANCE_FILE = OUTPUT_DIR / "phase52_quantile_feature_importance.csv"


# ============================================================
# CONFIG
# ============================================================

HORIZONS = [12, 24, 72]
QUANTILES = [0.1, 0.5, 0.9]

TARGET = "p_pvgis_kw_per_kwp"

TRAIN_END = "2021-07-01"
VAL_END = "2022-01-01"


# ------------------------------------------------------------
# 52 safe features (Phase 5.1 exact list)
# ------------------------------------------------------------

SAFE_FEATURES = [
    "region_id",
    "ghi_w_m2", "beam_w_m2", "diffuse_w_m2", "reflected_w_m2",
    "solar_elevation_deg", "temperature_2m_c", "wind_speed_10m_ms",
    "solar_zenith_deg", "solar_azimuth_deg", "solar_elevation_calc_deg",
    "ghi_clearsky_w_m2", "dni_clearsky_w_m2", "dhi_clearsky_w_m2",
    "kt", "beam_fraction", "diffuse_fraction", "is_daylight",
    "hour", "day_of_week", "month", "day_of_year", "week_of_year",
    "is_weekend", "hour_sin", "hour_cos", "doy_sin", "doy_cos",
    "p_lag_1h", "kt_lag_1h", "p_lag_2h", "kt_lag_2h",
    "p_lag_3h", "kt_lag_3h", "p_lag_6h", "kt_lag_6h",
    "p_lag_12h", "kt_lag_12h", "p_lag_24h", "kt_lag_24h",
    "p_lag_48h", "kt_lag_48h", "p_lag_168h", "kt_lag_168h",
    "p_roll_mean_3h", "p_roll_std_3h", "kt_roll_mean_3h",
    "p_roll_mean_6h", "p_roll_std_6h", "kt_roll_mean_6h",
    "p_roll_mean_24h", "p_roll_std_24h", "kt_roll_mean_24h",
    "p_lag_diff_1h_24h", "p_lag_diff_24h_168h", "kt_lag_diff_1h_24h",
    "region_mean_p_lag", "region_mean_kt_lag",
    "national_mean_p_lag", "national_mean_kt_lag",
    "p_dev_from_region", "temp_effect_proxy", "wind_cooling_proxy",
    "kt_anomaly_24h",
]

NWP_FEATURES = [
    "nwp_temperature_2m_c",
    "nwp_wind_speed_10m_ms",
    "nwp_wind_direction_10m_deg",
    "nwp_cloud_cover_fraction",
]

ALL_FEATURES = SAFE_FEATURES + NWP_FEATURES


# ------------------------------------------------------------
# LightGBM parameters
# ------------------------------------------------------------

PARAMS = {
    "objective": "quantile",
    "metric": "quantile",
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
    "random_state": 42,
    "n_jobs": -1,
    "verbosity": -1,
    "force_col_wise": True,
}

EARLY_STOPPING = 50


# ============================================================
# LOAD DATA
# ============================================================

print("=" * 80)
print("STEP 24 — PHASE 5.2 QUANTILE MODELS (P10 / P50 / P90)")
print("=" * 80)

print()
print(f"Dataset:  {DATASET_FILE}")
print(f"Features: {FEATURES_FILE}")

# Load only needed columns from the large features file
features_df = pd.read_parquet(
    FEATURES_FILE,
    columns=["district_id", "timestamp"] + SAFE_FEATURES,
)
print()
print(f"Loaded features: {len(features_df):,} rows")

sample = pd.read_parquet(DATASET_FILE)
print(f"Loaded sample:   {len(sample):,} rows")


# ============================================================
# MERGE FEATURES INTO SAMPLE
# ============================================================

print()
print("Attaching features...")

# Parse features
features_df["timestamp"] = pd.to_datetime(features_df["timestamp"])
features_df["district_id"] = features_df["district_id"].astype(int)

# Parse sample
sample["forecast_issue_time_utc"] = pd.to_datetime(
    sample["forecast_issue_time_utc"], utc=True
)
sample["forecast_valid_time_utc"] = pd.to_datetime(
    sample["forecast_valid_time_utc"], utc=True
)
sample["district_id"] = sample["district_id"].astype(int)

# Derive valid_time_local from forecast_valid_time_utc
sample["valid_time_local"] = (
    sample["forecast_valid_time_utc"]
    .dt.tz_convert("Africa/Tunis")
    .dt.tz_localize(None)
)

# Derive issue_time_local for joining with features
sample["issue_time_local"] = (
    sample["forecast_issue_time_utc"]
    .dt.tz_convert("Africa/Tunis")
    .dt.tz_localize(None)
)

# Rename TIGGE columns to avoid collision with feature columns
NWP_RENAME = {
    "temperature_2m_c": "nwp_temperature_2m_c",
    "wind_speed_10m_ms": "nwp_wind_speed_10m_ms",
    "wind_direction_10m_deg": "nwp_wind_direction_10m_deg",
    "cloud_cover_fraction": "nwp_cloud_cover_fraction",
}
sample = sample.rename(columns=NWP_RENAME)

# Drop columns that will collide with features_df
sample = sample.drop(
    columns=[
        "region_id",
        "latitude",
        "longitude",
        "nwp_grid_latitude",
        "nwp_grid_longitude",
    ],
    errors="ignore",
)

# Merge
merged = sample.merge(
    features_df.rename(columns={"timestamp": "issue_time_local"}),
    on=["district_id", "issue_time_local"],
    how="inner",
)

print(f"Matched rows: {len(merged):,}")

missing = [c for c in ALL_FEATURES if c not in merged.columns]
print(f"Missing features: {missing if missing else 'NONE'}")

if missing:
    raise RuntimeError(f"Cannot train — missing features: {missing}")


# ============================================================
# SPLIT
# ============================================================

print()
print("Splitting on forecast_issue_time_utc...")

train = merged[merged["forecast_issue_time_utc"] < TRAIN_END]
val = merged[
    (merged["forecast_issue_time_utc"] >= TRAIN_END)
    & (merged["forecast_issue_time_utc"] < VAL_END)
]
test = merged[merged["forecast_issue_time_utc"] >= VAL_END]

print(f"Train: {len(train):,}")
print(f"Val:   {len(val):,}")
print(f"Test:  {len(test):,}")


# ============================================================
# TRAIN PER HORIZON × QUANTILE
# ============================================================

all_predictions = []
all_metrics = {}
all_importance = []

for h in HORIZONS:

    train_h = train[train["forecast_lead_hours"] == h]
    val_h = val[val["forecast_lead_hours"] == h]
    test_h = test[test["forecast_lead_hours"] == h]

    if len(train_h) == 0:
        print(f"\n[H+{h}] No training data — skipping")
        continue

    print()
    print("=" * 80)
    print(f"H+{h} — Quantile training")
    print("=" * 80)
    print(f"Train: {len(train_h):,}  Val: {len(val_h):,}  Test: {len(test_h):,}")

    X_train = train_h[ALL_FEATURES].fillna(0)
    y_train = train_h[TARGET]
    X_val = val_h[ALL_FEATURES].fillna(0)
    y_val = val_h[TARGET]
    X_test = test_h[ALL_FEATURES].fillna(0)
    y_test = test_h[TARGET]

    horizon_preds = test_h[
        ["district_id", "district_name",
         "forecast_issue_time_utc", "forecast_valid_time_utc",
         "forecast_lead_hours"]
    ].copy()
    horizon_preds["y_true"] = y_test.values
    horizon_preds["horizon"] = f"h{h}"

    horizon_metrics = {}

    for q in QUANTILES:

        q_int = int(q * 100)
        print()
        print(f"  Training P{q_int}...")

        params = {**PARAMS, "alpha": q}

        model = lgb.LGBMRegressor(**params)
        model.fit(
            X_train, y_train,
            eval_X=X_val,
            eval_y=y_val,
            callbacks=[
                lgb.early_stopping(EARLY_STOPPING),
                lgb.log_evaluation(200),
            ],
        )

        y_pred = np.clip(model.predict(X_test), 0, None)

        pinball = mean_pinball_loss(y_test, y_pred, alpha=q)
        mae = mean_absolute_error(y_test, y_pred)

        horizon_metrics[f"p{q_int}"] = {
            "pinball_loss": float(pinball),
            "mae": float(mae),
        }

        horizon_preds[f"y_pred_p{q_int}"] = y_pred

        # Feature importance
        imp_df = pd.DataFrame({
            "feature": ALL_FEATURES,
            "importance": model.feature_importances_,
        }).sort_values("importance", ascending=False)
        imp_df["horizon"] = f"h{h}"
        imp_df["quantile"] = f"p{q_int}"
        all_importance.append(imp_df)

        print(f"    Pinball: {pinball:.6f}  MAE: {mae:.6f}")

    # --------------------------------------------------------
    # Coverage and interval width
    # --------------------------------------------------------

    p10 = horizon_preds["y_pred_p10"]
    p50 = horizon_preds["y_pred_p50"]
    p90 = horizon_preds["y_pred_p90"]

    coverage = float(((y_test >= p10) & (y_test <= p90)).mean())
    interval_width = float((p90 - p10).mean())

    horizon_metrics["coverage_p10_p90"] = coverage
    horizon_metrics["mean_interval_width"] = interval_width

    # Crossings (quantile violations)
    crossings = int(
        (p10 > p50).sum() + (p50 > p90).sum() + (p10 > p90).sum()
    )
    horizon_metrics["crossings"] = crossings

    # Daylight-only coverage
    valid_hour = test_h["forecast_valid_time_utc"].dt.hour
    daylight_mask = valid_hour.between(6, 18)

    if daylight_mask.any():
        daylight_coverage = float(
            ((y_test[daylight_mask] >= p10[daylight_mask])
             & (y_test[daylight_mask] <= p90[daylight_mask])).mean()
        )
    else:
        daylight_coverage = None

    horizon_metrics["coverage_daylight"] = daylight_coverage

    all_metrics[f"h{h}"] = horizon_metrics
    all_predictions.append(horizon_preds)

    print()
    print(f"  Coverage (P10-P90): {coverage:.4f}")
    print(f"  Mean interval width: {interval_width:.6f}")
    print(f"  Crossings: {crossings}")
    if daylight_coverage is not None:
        print(f"  Daylight-only coverage: {daylight_coverage:.4f}")


# ============================================================
# SAVE
# ============================================================

print()
print("=" * 80)
print("SAVING")
print("=" * 80)

result = pd.concat(all_predictions, ignore_index=True)
result.to_parquet(PREDICTIONS_FILE, index=False)
print(f"Predictions: {PREDICTIONS_FILE}")
print(f"Rows: {len(result):,}")

with open(METRICS_FILE, "w") as f:
    json.dump(all_metrics, f, indent=2)
print(f"Metrics: {METRICS_FILE}")

imp = pd.concat(all_importance, ignore_index=True)
imp.to_csv(IMPORTANCE_FILE, index=False)
print(f"Importances: {IMPORTANCE_FILE}")


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 80)
print("QUANTILE SUMMARY")
print("=" * 80)
print()

header = (
    f"{'Horizon':<10} "
    f"{'P10 Pinball':>12} "
    f"{'P50 Pinball':>12} "
    f"{'P90 Pinball':>12} "
    f"{'Coverage':>10} "
    f"{'Width':>10} "
    f"{'Crossings':>10}"
)
print(header)
print("-" * len(header))

for h in HORIZONS:
    key = f"h{h}"
    if key not in all_metrics:
        continue
    m = all_metrics[key]
    print(
        f"H+{h:<7} "
        f"{m['p10']['pinball_loss']:>12.6f} "
        f"{m['p50']['pinball_loss']:>12.6f} "
        f"{m['p90']['pinball_loss']:>12.6f} "
        f"{m['coverage_p10_p90']:>10.4f} "
        f"{m['mean_interval_width']:>10.4f} "
        f"{m['crossings']:>10d}"
    )

print()
print("Nominal coverage target: 0.80")
print()
print("=" * 80)
print("QUANTILE MODELS COMPLETE")
print("=" * 80)