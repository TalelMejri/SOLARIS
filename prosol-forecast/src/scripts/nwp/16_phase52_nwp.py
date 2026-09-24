from pathlib import Path
import json

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATASET_FILE = (
    PROJECT_ROOT / "data" / "processed" / "nwp" / "phase52_training_dataset.parquet"
)

FEATURES_FILE = (
    PROJECT_ROOT / "data" / "processed" / "features" / "district_features.parquet"
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "ml" / "phase52"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PREDICTIONS_FILE = OUTPUT_DIR / "phase52_nwp_predictions.parquet"
METRICS_FILE = OUTPUT_DIR / "phase52_nwp_metrics.json"
DISTRICT_METRICS_FILE = OUTPUT_DIR / "phase52_nwp_district_metrics.csv"
IMPORTANCE_FILE = OUTPUT_DIR / "phase52_nwp_feature_importance.csv"


# ============================================================
# CONFIG
# ============================================================

HORIZONS = [12, 24, 72]

TARGET = "p_pvgis_kw_per_kwp"

TRAIN_END = "2021-07-01"
VAL_END = "2022-01-01"


# ------------------------------------------------------------
# 52 SAFE FEATURES (same as Phase 5.1-R)
# ------------------------------------------------------------

SAFE_FEATURES = [
    "region_id",
    "ghi_w_m2",
    "beam_w_m2",
    "diffuse_w_m2",
    "reflected_w_m2",
    "solar_elevation_deg",
    "temperature_2m_c",
    "wind_speed_10m_ms",
    "solar_zenith_deg",
    "solar_azimuth_deg",
    "solar_elevation_calc_deg",
    "ghi_clearsky_w_m2",
    "dni_clearsky_w_m2",
    "dhi_clearsky_w_m2",
    "kt",
    "beam_fraction",
    "diffuse_fraction",
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
    "temp_effect_proxy",
    "wind_cooling_proxy",
    "kt_anomaly_24h",
]


# ------------------------------------------------------------
# TIGGE NWP FEATURES (renamed with nwp_ prefix)
# ------------------------------------------------------------

NWP_FEATURES = [
    "nwp_temperature_2m_c",
    "nwp_wind_speed_10m_ms",
    "nwp_wind_direction_10m_deg",
    "nwp_cloud_cover_fraction",
]


# ------------------------------------------------------------
# PARAMETERS (Phase 5.1 exact)
# ------------------------------------------------------------

PARAMS = {
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
print("STEP 16 — PHASE 5.2 (WITH TIGGE NWP)")
print("=" * 80)

print()
print(f"Dataset: {DATASET_FILE}")

features_df = pd.read_parquet(
    FEATURES_FILE,
    columns=["district_id", "timestamp"] + SAFE_FEATURES,
)
print(f"Loaded features: {len(features_df):,} rows")

sample = pd.read_parquet(DATASET_FILE)

features_df["timestamp"] = pd.to_datetime(features_df["timestamp"])
features_df["district_id"] = features_df["district_id"].astype(int)

sample["forecast_issue_time_utc"] = pd.to_datetime(
    sample["forecast_issue_time_utc"], utc=True
)
sample["valid_time_local"] = pd.to_datetime(sample["valid_time_local"])
sample["district_id"] = sample["district_id"].astype(int)


# ============================================================
# MERGE
# ============================================================

print()
print("Attaching 52 safe features + 4 NWP features...")

sample["issue_time_local"] = (
    sample["forecast_issue_time_utc"].dt.tz_convert("Africa/Tunis").dt.tz_localize(None)
)

# Rename TIGGE features to nwp_* to avoid collision
NWP_RENAME = {
    "temperature_2m_c": "nwp_temperature_2m_c",
    "wind_speed_10m_ms": "nwp_wind_speed_10m_ms",
    "wind_direction_10m_deg": "nwp_wind_direction_10m_deg",
    "cloud_cover_fraction": "nwp_cloud_cover_fraction",
}
sample = sample.rename(columns=NWP_RENAME)

# Drop sample columns that features_df provides
sample = sample.drop(
    columns=["region_id", "latitude", "longitude"],
    errors="ignore",
)

merged = sample.merge(
    features_df.rename(columns={"timestamp": "issue_time_local"}),
    on=["district_id", "issue_time_local"],
    how="inner",
)

print(f"Sample rows:     {len(sample):,}")
print(f"Matched rows:    {len(merged):,}")
print(f"Match rate:      {100 * len(merged) / len(sample):.2f}%")

# Verify all features present
ALL_FEATURES = SAFE_FEATURES + NWP_FEATURES
missing = [c for c in ALL_FEATURES if c not in merged.columns]
print(f"Missing features: {missing if missing else 'NONE'}")


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
# TRAIN PER HORIZON
# ============================================================

results = {}
predictions = []
district_metrics = []
importances = []

for h in HORIZONS:
    print()
    print("=" * 80)
    print(f"H+{h} — Phase 5.2 (with TIGGE NWP)")
    print("=" * 80)

    train_h = train[train["forecast_lead_hours"] == h]
    val_h = val[val["forecast_lead_hours"] == h]
    test_h = test[test["forecast_lead_hours"] == h]

    print(f"Train rows: {len(train_h):,}")
    print(f"Val rows:   {len(val_h):,}")
    print(f"Test rows:  {len(test_h):,}")

    X_train = train_h[ALL_FEATURES].fillna(0)
    y_train = train_h[TARGET]
    X_val = val_h[ALL_FEATURES].fillna(0)
    y_val = val_h[TARGET]
    X_test = test_h[ALL_FEATURES].fillna(0)
    y_test = test_h[TARGET]

    persistence_daily = test_h["p_lag_24h"].fillna(0)

    model = lgb.LGBMRegressor(**PARAMS)
    model.fit(
        X_train,
        y_train,
        eval_X=X_val,
        eval_y=y_val,
        callbacks=[lgb.early_stopping(EARLY_STOPPING), lgb.log_evaluation(200)],
    )

    y_pred = np.clip(model.predict(X_test), 0, None)

    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)

    mae_p = mean_absolute_error(y_test, persistence_daily)
    rmse_p = np.sqrt(mean_squared_error(y_test, persistence_daily))

    skill_daily = 1 - (rmse / rmse_p) if rmse_p > 0 else np.nan

    print()
    print(f"Model:   MAE={mae:.6f}  RMSE={rmse:.6f}  R²={r2:.6f}")
    print(f"Persist: MAE={mae_p:.6f}  RMSE={rmse_p:.6f}")
    print(f"Skill vs daily persistence: {skill_daily:.6f}")

    results[f"h{h}"] = {
        "horizon": h,
        "model": "phase52_nwp",
        "train_rows": int(len(train_h)),
        "val_rows": int(len(val_h)),
        "test_rows": int(len(test_h)),
        "mae": float(mae),
        "rmse": float(rmse),
        "r2": float(r2),
        "mae_persistence": float(mae_p),
        "rmse_persistence": float(rmse_p),
        "skill_vs_daily": float(skill_daily),
    }

    pred_df = test_h[
        [
            "district_id",
            "district_name",
            "forecast_issue_time_utc",
            "forecast_valid_time_utc",
            "forecast_lead_hours",
        ]
    ].copy()
    pred_df["y_true"] = y_test.values
    pred_df["y_pred"] = y_pred
    pred_df["persistence_daily"] = persistence_daily.values
    pred_df["horizon"] = f"h{h}"
    predictions.append(pred_df)

    test_h_copy = test_h.copy()
    test_h_copy["y_true"] = y_test.values
    test_h_copy["y_pred"] = y_pred

    for did, grp in test_h_copy.groupby("district_id"):
        if len(grp) > 1:
            district_metrics.append(
                {
                    "horizon": f"h{h}",
                    "district_id": int(did),
                    "district_name": grp["district_name"].iloc[0],
                    "n": int(len(grp)),
                    "mae": float(mean_absolute_error(grp["y_true"], grp["y_pred"])),
                    "rmse": float(
                        np.sqrt(mean_squared_error(grp["y_true"], grp["y_pred"]))
                    ),
                    "r2": float(r2_score(grp["y_true"], grp["y_pred"])),
                }
            )

    # Feature importance
    imp_df = pd.DataFrame(
        {
            "feature": ALL_FEATURES,
            "importance": model.feature_importances_,
        }
    ).sort_values("importance", ascending=False)
    imp_df["horizon"] = f"h{h}"
    importances.append(imp_df)


# ============================================================
# SAVE
# ============================================================

print()
print("=" * 80)
print("SAVING")
print("=" * 80)

pd.concat(predictions, ignore_index=True).to_parquet(PREDICTIONS_FILE, index=False)
pd.DataFrame(district_metrics).to_csv(DISTRICT_METRICS_FILE, index=False)
pd.concat(importances, ignore_index=True).to_csv(IMPORTANCE_FILE, index=False)

with open(METRICS_FILE, "w") as f:
    json.dump(results, f, indent=2)

print(f"Predictions: {PREDICTIONS_FILE}")
print(f"Metrics:     {METRICS_FILE}")
print(f"Importances: {IMPORTANCE_FILE}")


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 80)
print("PHASE 5.2 (NWP) — SUMMARY")
print("=" * 80)
print()
print(f"{'Horizon':<10} {'MAE':>10} {'RMSE':>10} {'R²':>10} {'Skill':>10}")
print("-" * 55)
for h in HORIZONS:
    r = results[f"h{h}"]
    print(
        f"H+{h:<7} {r['mae']:>10.6f} {r['rmse']:>10.6f} "
        f"{r['r2']:>10.6f} {r['skill_vs_daily']:>10.6f}"
    )
print()
print("=" * 80)
