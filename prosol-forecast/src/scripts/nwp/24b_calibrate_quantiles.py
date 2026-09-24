from pathlib import Path
import json

import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase52"
    / "phase52_quantile_predictions.parquet"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase52"
    / "phase52_quantile_predictions_calibrated.parquet"
)

METRICS_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase52"
    / "phase52_quantile_calibration_metrics.json"
)

# Split test period into calibration + validation
CALIB_START = "2022-01-01"
CALIB_END = "2022-07-01"
TEST_START = "2022-07-01"

# Target coverage — inflated slightly to compensate for
# distribution shift between calibration and validation windows
TARGET_COVERAGE = 0.82


# ============================================================
# LOAD
# ============================================================

print("=" * 80)
print("STEP 24b — QUANTILE CALIBRATION (SEPARATE DAY/NIGHT)")
print("=" * 80)

preds = pd.read_parquet(INPUT_FILE)
preds["forecast_issue_time_utc"] = pd.to_datetime(
    preds["forecast_issue_time_utc"], utc=True
)
preds["forecast_valid_time_utc"] = pd.to_datetime(
    preds["forecast_valid_time_utc"], utc=True
)

print()
print(f"Input rows: {len(preds):,}")
print(f"Horizons: {sorted(preds['horizon'].unique())}")
print(
    f"Date range: {preds['forecast_issue_time_utc'].min()} → "
    f"{preds['forecast_issue_time_utc'].max()}"
)


# ============================================================
# STEP 1 — SORT QUANTILES
# ============================================================

print()
print("=" * 80)
print("STEP 1 — Enforce quantile ordering")
print("=" * 80)

for h in preds["horizon"].unique():
    mask = preds["horizon"] == h
    sub = preds.loc[mask, ["y_pred_p10", "y_pred_p50", "y_pred_p90"]].values
    sorted_vals = np.sort(sub, axis=1)
    preds.loc[mask, "y_pred_p10"] = sorted_vals[:, 0]
    preds.loc[mask, "y_pred_p50"] = sorted_vals[:, 1]
    preds.loc[mask, "y_pred_p90"] = sorted_vals[:, 2]

p10 = preds["y_pred_p10"]
p50 = preds["y_pred_p50"]
p90 = preds["y_pred_p90"]

crossings = int(
    (p10 > p50).sum() + (p50 > p90).sum() + (p10 > p90).sum()
)
print(f"Crossings after sort: {crossings}")


# ============================================================
# STEP 2 — SEGMENT INTO DAY/NIGHT
# ============================================================

print()
print("=" * 80)
print("STEP 2 — Segment by daylight (UTC hour 6–18)")
print("=" * 80)

preds["valid_hour"] = preds["forecast_valid_time_utc"].dt.hour
preds["is_daylight"] = preds["valid_hour"].between(6, 18)

calib_mask = (
    (preds["forecast_issue_time_utc"] >= CALIB_START)
    & (preds["forecast_issue_time_utc"] < CALIB_END)
)

print()
print(f"Calibration window: {CALIB_START} → {CALIB_END}")
print(f"Calibration rows:   {int(calib_mask.sum()):,}")
print(f"Target coverage:    {TARGET_COVERAGE}")


# ============================================================
# STEP 3 — WIDE-RANGE SCALE CALIBRATION PER HORIZON × DAYLIGHT
# ============================================================

print()
print("=" * 80)
print("STEP 3 — Per-horizon, per-daylight calibration")
print("=" * 80)

# Extended search range: 0.05 to 2.05
SCALES = np.arange(0.05, 2.05, 0.01)

calibration_results = {}

for h in sorted(preds["horizon"].unique()):
    for is_day in [True, False]:

        segment = "daylight" if is_day else "night"
        h_mask = preds["horizon"] == h
        seg_mask = preds["is_daylight"] == is_day
        calib = preds[h_mask & seg_mask & calib_mask]

        if len(calib) < 50:
            print(f"  {h.upper()} {segment}: insufficient data ({len(calib)})")
            continue

        y_true = calib["y_true"].values
        p10_c = calib["y_pred_p10"].values
        p50_c = calib["y_pred_p50"].values
        p90_c = calib["y_pred_p90"].values

        best_scale = 1.0
        best_diff = float("inf")
        best_cov = None

        for scale in SCALES:
            p10_s = p50_c + (p10_c - p50_c) * scale
            p90_s = p50_c + (p90_c - p50_c) * scale
            cov = ((y_true >= p10_s) & (y_true <= p90_s)).mean()
            diff = abs(cov - TARGET_COVERAGE)
            if diff < best_diff:
                best_diff = diff
                best_scale = float(scale)
                best_cov = float(cov)

        key = f"{h}_{segment}"
        calibration_results[key] = {
            "horizon": h,
            "segment": segment,
            "scale": best_scale,
            "coverage": best_cov,
            "n": int(len(calib)),
        }

        print(
            f"  {h.upper()} {segment:9s}: "
            f"scale={best_scale:.2f}  coverage={best_cov:.4f}  n={len(calib):,}"
        )


# ============================================================
# STEP 4 — APPLY CALIBRATION
# ============================================================

print()
print("=" * 80)
print("STEP 4 — Apply calibration")
print("=" * 80)

preds["y_pred_p10_calibrated"] = preds["y_pred_p10"]
preds["y_pred_p90_calibrated"] = preds["y_pred_p90"]

for key, info in calibration_results.items():
    h = info["horizon"]
    is_day = info["segment"] == "daylight"

    mask = (
        (preds["horizon"] == h)
        & (preds["is_daylight"] == is_day)
    )

    p50 = preds.loc[mask, "y_pred_p50"].values
    p10 = preds.loc[mask, "y_pred_p10"].values
    p90 = preds.loc[mask, "y_pred_p90"].values

    scale = info["scale"]

    preds.loc[mask, "y_pred_p10_calibrated"] = p50 + (p10 - p50) * scale
    preds.loc[mask, "y_pred_p90_calibrated"] = p50 + (p90 - p50) * scale

# Ensure ordering after calibration
for h in preds["horizon"].unique():
    mask = preds["horizon"] == h
    sub = preds.loc[
        mask,
        ["y_pred_p10_calibrated", "y_pred_p50", "y_pred_p90_calibrated"],
    ].values
    sorted_vals = np.sort(sub, axis=1)
    preds.loc[mask, "y_pred_p10_calibrated"] = sorted_vals[:, 0]
    preds.loc[mask, "y_pred_p50"] = sorted_vals[:, 1]
    preds.loc[mask, "y_pred_p90_calibrated"] = sorted_vals[:, 2]

print("Applied.")


# ============================================================
# STEP 5 — VALIDATE ON HELD-OUT SET
# ============================================================

print()
print("=" * 80)
print("STEP 5 — Validation on held-out test set (2022-07 → 2022-12)")
print("=" * 80)

val_mask = preds["forecast_issue_time_utc"] >= TEST_START

final_metrics = {}

for h in sorted(preds["horizon"].unique()):

    sub = preds[(preds["horizon"] == h) & val_mask]

    if len(sub) == 0:
        continue

    y_true = sub["y_true"].values
    p10 = sub["y_pred_p10_calibrated"].values
    p90 = sub["y_pred_p90_calibrated"].values

    cov_all = float(((y_true >= p10) & (y_true <= p90)).mean())
    width_all = float((p90 - p10).mean())

    day_mask = sub["is_daylight"].values
    night_mask = ~day_mask

    cov_day = (
        float(((y_true[day_mask] >= p10[day_mask])
               & (y_true[day_mask] <= p90[day_mask])).mean())
        if day_mask.any() else None
    )
    cov_night = (
        float(((y_true[night_mask] >= p10[night_mask])
               & (y_true[night_mask] <= p90[night_mask])).mean())
        if night_mask.any() else None
    )

    final_metrics[h] = {
        "coverage_all": cov_all,
        "coverage_daylight": cov_day,
        "coverage_night": cov_night,
        "mean_width": width_all,
        "n_test": int(len(sub)),
    }

    day_str = f"{cov_day:.4f}" if cov_day is not None else "n/a"
    night_str = f"{cov_night:.4f}" if cov_night is not None else "n/a"

    print(
        f"  {h.upper()}: "
        f"all={cov_all:.4f}  "
        f"day={day_str}  "
        f"night={night_str}  "
        f"width={width_all:.4f}"
    )


# ============================================================
# STEP 6 — HEADLINE DAYLIGHT COVERAGE
# ============================================================

print()
print("=" * 80)
print("HEADLINE METRIC — DAYLIGHT COVERAGE (held-out validation)")
print("=" * 80)

for h in sorted(preds["horizon"].unique()):
    sub = preds[(preds["horizon"] == h) & val_mask]
    day_mask = sub["is_daylight"].values

    if not day_mask.any():
        continue

    y_true = sub["y_true"].values
    p10 = sub["y_pred_p10_calibrated"].values
    p90 = sub["y_pred_p90_calibrated"].values

    cov_day = float(
        ((y_true[day_mask] >= p10[day_mask])
         & (y_true[day_mask] <= p90[day_mask])).mean()
    )

    ok = "✓" if 0.78 <= cov_day <= 0.86 else "⚠"
    print(f"  {h.upper()}: daylight coverage = {cov_day:.4f}  {ok}")


# ============================================================
# SAVE
# ============================================================

print()
print("=" * 80)
print("SAVING")
print("=" * 80)

preds = preds.drop(columns=["valid_hour", "is_daylight"])

preds.to_parquet(OUTPUT_FILE, index=False)
print(f"Calibrated predictions: {OUTPUT_FILE}")
print(f"Rows: {len(preds):,}")

with open(METRICS_FILE, "w") as f:
    json.dump({
        "calibration_results": calibration_results,
        "test_metrics": final_metrics,
        "target_coverage": TARGET_COVERAGE,
        "calibration_split": {"start": CALIB_START, "end": CALIB_END},
        "validation_split": {"start": TEST_START},
    }, f, indent=2)
print(f"Metrics: {METRICS_FILE}")

print()
print("=" * 80)
print("CALIBRATION COMPLETE")
print("=" * 80)