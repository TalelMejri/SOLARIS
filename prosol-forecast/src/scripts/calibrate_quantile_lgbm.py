"""
Phase 4.2 — Conformal calibration for QUANTILE intervals.

Handles both:
  - Undercoverage (rare) → widen via additive offset
  - Overcoverage (common here) → shrink via scale factor

Uses validation set only. No test-set leakage.
"""
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FEATURE_FILE = (
    PROJECT_ROOT / "data" / "processed" / "features" / "district_features.parquet"
)

MODEL_DIR = PROJECT_ROOT / "models"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "ml"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# CONFIG
# ============================================================

TARGET = "p_pvgis_kw_per_kwp"

CALIB_START = "2019-01-01 00:00:00"
CALIB_END   = "2019-12-31 23:00:00"
TEST_START  = "2020-01-01 00:00:00"
TEST_END    = "2020-12-31 23:00:00"

NOMINAL_COVERAGE = 0.80


# ============================================================
# LOAD
# ============================================================

print("=" * 80)
print("PROSOL FORECAST — QUANTILE CALIBRATION (SCALE-BASED)")
print("=" * 80)

df = pd.read_parquet(FEATURE_FILE)
df["timestamp"] = pd.to_datetime(df["timestamp"])

print(f"\nRows    : {len(df):,}")
print(f"Columns : {len(df.columns)}")

with open(MODEL_DIR / "lightgbm_quantile_features.json") as f:
    features = json.load(f)
print(f"Features: {len(features)}")

# Verify features present
missing = [f for f in features if f not in df.columns]
if missing:
    raise ValueError(f"Missing features: {missing}")

model_p10 = joblib.load(MODEL_DIR / "lightgbm_p10.pkl")
model_p50 = joblib.load(MODEL_DIR / "lightgbm_p50.pkl")
model_p90 = joblib.load(MODEL_DIR / "lightgbm_p90.pkl")
print("Models loaded: P10, P50, P90")


# ============================================================
# SPLITS
# ============================================================

calib = df[(df["timestamp"] >= CALIB_START) & (df["timestamp"] <= CALIB_END)].copy()
test  = df[(df["timestamp"] >= TEST_START)  & (df["timestamp"] <= TEST_END)].copy()

print(f"\nCalibration rows: {len(calib):,}")
print(f"Test rows       : {len(test):,}")


# ============================================================
# PREDICT
# ============================================================

print("\nGenerating predictions...")

calib["p10_raw"] = model_p10.predict(calib[features])
calib["p50_raw"] = model_p50.predict(calib[features])
calib["p90_raw"] = model_p90.predict(calib[features])

test["p10_raw"] = model_p10.predict(test[features])
test["p50_raw"] = model_p50.predict(test[features])
test["p90_raw"] = model_p90.predict(test[features])


# ============================================================
# MONOTONICITY VIA CLAMPING (preserves P50)
# ============================================================

def clamp(frame):
    for c in ["p10_raw", "p50_raw", "p90_raw"]:
        frame[c] = frame[c].clip(0.0, 1.0)
    p50 = frame["p50_raw"].to_numpy()
    frame["p10_raw"] = np.minimum(frame["p10_raw"].to_numpy(), p50)
    frame["p90_raw"] = np.maximum(frame["p90_raw"].to_numpy(), p50)
    return frame

calib = clamp(calib)
test  = clamp(test)


# ============================================================
# COVERAGE HELPER
# ============================================================

def coverage(y, lo, hi):
    return float(((y >= lo) & (y <= hi)).mean())


# ============================================================
# GRID SEARCH FOR OPTIMAL SCALE FACTOR
# ============================================================
# Interval shape is preserved; only width is scaled.
#
# P10_scaled = P50 - s * (P50 - P10_raw)
# P90_scaled = P50 + s * (P90_raw - P50)
#
# We search over s in a range and pick the value that makes
# validation coverage closest to the target (0.80).
# ============================================================

print("\n" + "=" * 80)
print("SCALE-BASED CALIBRATION (using 2019 validation ONLY)")
print("=" * 80)

y_calib = calib[TARGET].to_numpy()
p50_c = calib["p50_raw"].to_numpy()
p10_c = calib["p10_raw"].to_numpy()
p90_c = calib["p90_raw"].to_numpy()

target = NOMINAL_COVERAGE

best_scale = 1.0
best_err = float("inf")
results = []

for s in np.linspace(0.1, 1.5, 71):
    p10s = np.clip(p50_c - s * (p50_c - p10_c), 0, None)
    p90s = np.clip(p50_c + s * (p90_c - p50_c), 0, None)
    cov = coverage(y_calib, p10s, p90s)
    err = abs(cov - target)
    results.append((s, cov, err))
    if err < best_err:
        best_err = err
        best_scale = s

print(f"Grid search range       : [0.10, 1.50]")
print(f"Best scale factor       : {best_scale:.4f}")
print(f"Best validation coverage: {results[int(np.argmin([r[2] for r in results]))][1]*100:.4f}%")

# Sanity check: coverage at chosen scale on validation
p10v = np.clip(p50_c - best_scale * (p50_c - p10_c), 0, None)
p90v = np.clip(p50_c + best_scale * (p90_c - p50_c), 0, None)
val_cov = coverage(y_calib, p10v, p90v)
print(f"Validation coverage at chosen scale : {val_cov*100:.4f}%")


# ============================================================
# APPLY TO TEST
# ============================================================

print("\nApplying to test set...")

test_p50 = test["p50_raw"].to_numpy()
test_p10 = test["p10_raw"].to_numpy()
test_p90 = test["p90_raw"].to_numpy()

test["p10_calibrated"] = np.clip(
    test_p50 - best_scale * (test_p50 - test_p10), 0, None
)
test["p50_calibrated"] = test_p50.copy()
test["p90_calibrated"] = np.clip(
    test_p50 + best_scale * (test_p90 - test_p50), 0, None
)

# Re-enforce monotonicity after scaling
test["p10_calibrated"] = np.minimum(test["p10_calibrated"], test["p50_calibrated"])
test["p90_calibrated"] = np.maximum(test["p90_calibrated"], test["p50_calibrated"])


# ============================================================
# METRICS
# ============================================================

def calc_metrics(frame, lo, mid, hi):
    y = frame[TARGET].to_numpy()
    l = frame[lo].to_numpy()
    m = frame[mid].to_numpy()
    u = frame[hi].to_numpy()

    cov  = coverage(y, l, u)
    w    = float((u - l).mean())
    mae  = float(np.mean(np.abs(y - m)))
    rmse = float(np.sqrt(np.mean((y - m) ** 2)))
    ss_res = float(np.sum((y - m) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {"coverage": cov, "width": w, "mae": mae, "rmse": rmse, "r2": r2}

raw = calc_metrics(test, "p10_raw", "p50_raw", "p90_raw")
cal = calc_metrics(test, "p10_calibrated", "p50_calibrated", "p90_calibrated")


# ============================================================
# PRINT
# ============================================================

print("\n" + "=" * 80)
print("2020 TEST RESULTS")
print("=" * 80)

print(f"\n{'Metric':28s}{'RAW':>15s}{'CALIBRATED':>15s}")
print("-" * 58)
print(f"{'Coverage':28s}{raw['coverage']:>15.6f}{cal['coverage']:>15.6f}")
print(f"{'Mean interval width':28s}{raw['width']:>15.6f}{cal['width']:>15.6f}")
print(f"{'P50 MAE':28s}{raw['mae']:>15.6f}{cal['mae']:>15.6f}")
print(f"{'P50 RMSE':28s}{raw['rmse']:>15.6f}{cal['rmse']:>15.6f}")
print(f"{'P50 R²':28s}{raw['r2']:>15.6f}{cal['r2']:>15.6f}")

cross = {
    "p10_gt_p50": int((test["p10_calibrated"] > test["p50_calibrated"]).sum()),
    "p50_gt_p90": int((test["p50_calibrated"] > test["p90_calibrated"]).sum()),
    "p10_gt_p90": int((test["p10_calibrated"] > test["p90_calibrated"]).sum()),
}
print("\nCrossings after calibration:")
for k, v in cross.items():
    print(f"  {k}: {v}")


# ============================================================
# SAVE
# ============================================================

out = test[[
    "district_id", "timestamp", TARGET,
    "p10_raw", "p50_raw", "p90_raw",
    "p10_calibrated", "p50_calibrated", "p90_calibrated",
]].rename(columns={
    TARGET: "actual_p_kw_per_kwp",
    "p10_raw": "p10_raw_kw_per_kwp",
    "p50_raw": "p50_raw_kw_per_kwp",
    "p90_raw": "p90_raw_kw_per_kwp",
    "p10_calibrated": "p10_calibrated_kw_per_kwp",
    "p50_calibrated": "p50_calibrated_kw_per_kwp",
    "p90_calibrated": "p90_calibrated_kw_per_kwp",
})

out["raw_interval_width_kw_per_kwp"] = (
    out["p90_raw_kw_per_kwp"] - out["p10_raw_kw_per_kwp"]
)
out["calibrated_interval_width_kw_per_kwp"] = (
    out["p90_calibrated_kw_per_kwp"] - out["p10_calibrated_kw_per_kwp"]
)

pred_path = OUTPUT_DIR / "lightgbm_quantile_calibrated_test_predictions.parquet"
out.to_parquet(pred_path, index=False)

metrics = {
    "target": TARGET,
    "nominal_coverage": NOMINAL_COVERAGE,
    "calibration_period": [CALIB_START, CALIB_END],
    "test_period": [TEST_START, TEST_END],
    "calibration_method": "scale_based_conformal",
    "scale_factor": float(best_scale),
    "validation_coverage_at_scale": float(val_cov),
    "raw_2020": raw,
    "calibrated_2020": cal,
    "quantile_crossings": cross,
}

metrics_path = OUTPUT_DIR / "lightgbm_quantile_calibration_metrics.json"
with open(metrics_path, "w") as f:
    json.dump(metrics, f, indent=2)

print("\n" + "=" * 80)
print("SAVED")
print("=" * 80)
print(pred_path)
print(metrics_path)
print("\nCalibration complete.")