from pathlib import Path
import json

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

ML_DIR = PROJECT_ROOT / "data" / "processed" / "ml" / "phase52"

BASELINE_PRED = ML_DIR / "phase51r_baseline_predictions.parquet"
NWP_PRED = ML_DIR / "phase52_nwp_predictions.parquet"

OUTPUT_DIR = ML_DIR
OUTPUT_FILE = OUTPUT_DIR / "district_improvement.csv"
SUMMARY_FILE = OUTPUT_DIR / "district_improvement_summary.json"


# ============================================================
# LOAD
# ============================================================

print("=" * 80)
print("STEP 19 — DISTRICT-LEVEL IMPROVEMENT ANALYSIS")
print("=" * 80)

base = pd.read_parquet(BASELINE_PRED)
nwp = pd.read_parquet(NWP_PRED)

print()
print(f"Baseline predictions: {len(base):,}")
print(f"NWP predictions:      {len(nwp):,}")

# Merge on (district_id, horizon, valid_time)
KEYS = ["district_id", "horizon", "forecast_valid_time_utc"]
merged = base[KEYS + ["y_true", "y_pred", "district_name", "forecast_lead_hours"]].merge(
    nwp[KEYS + ["y_pred"]],
    on=KEYS,
    suffixes=("_baseline", "_nwp"),
)

print(f"Merged rows: {len(merged):,}")


# ============================================================
# PER-DISTRICT METRICS
# ============================================================

rows = []

for h in ["h12", "h24", "h72"]:
    h_merged = merged[merged["horizon"] == h]

    for did, grp in h_merged.groupby("district_id"):
        if len(grp) < 2:
            continue

        y_true = grp["y_true"]
        y_base = grp["y_pred_baseline"]
        y_nwp = grp["y_pred_nwp"]

        base_rmse = np.sqrt(mean_squared_error(y_true, y_base))
        nwp_rmse = np.sqrt(mean_squared_error(y_true, y_nwp))
        base_mae = mean_absolute_error(y_true, y_base)
        nwp_mae = mean_absolute_error(y_true, y_nwp)

        rows.append({
            "horizon": h,
            "district_id": int(did),
            "district_name": grp["district_name"].iloc[0],
            "n": int(len(grp)),
            "baseline_rmse": base_rmse,
            "nwp_rmse": nwp_rmse,
            "rmse_improvement_pct": 100 * (base_rmse - nwp_rmse) / base_rmse if base_rmse > 0 else np.nan,
            "baseline_mae": base_mae,
            "nwp_mae": nwp_mae,
            "mae_improvement_pct": 100 * (base_mae - nwp_mae) / base_mae if base_mae > 0 else np.nan,
        })

df = pd.DataFrame(rows)
df.to_csv(OUTPUT_FILE, index=False)

print()
print(f"Saved: {OUTPUT_FILE}")


# ============================================================
# SUMMARY PER HORIZON
# ============================================================

print()
print("=" * 80)
print("DISTRICT-LEVEL IMPROVEMENT SUMMARY")
print("=" * 80)

summary = {}

for h in ["h12", "h24", "h72"]:
    sub = df[df["horizon"] == h]

    summary[h] = {
        "districts_total": int(len(sub)),
        "districts_improved_rmse": int((sub["rmse_improvement_pct"] > 0).sum()),
        "districts_improved_mae": int((sub["mae_improvement_pct"] > 0).sum()),
        "mean_rmse_improvement_pct": float(sub["rmse_improvement_pct"].mean()),
        "median_rmse_improvement_pct": float(sub["rmse_improvement_pct"].median()),
        "min_rmse_improvement_pct": float(sub["rmse_improvement_pct"].min()),
        "max_rmse_improvement_pct": float(sub["rmse_improvement_pct"].max()),
        "std_rmse_improvement_pct": float(sub["rmse_improvement_pct"].std()),
        "mean_mae_improvement_pct": float(sub["mae_improvement_pct"].mean()),
        "median_mae_improvement_pct": float(sub["mae_improvement_pct"].median()),
    }

    print()
    print(f"=== {h.upper()} ===")
    print(f"  Districts:              {summary[h]['districts_total']}")
    print(f"  Improved (RMSE):        {summary[h]['districts_improved_rmse']}/{summary[h]['districts_total']}")
    print(f"  Improved (MAE):         {summary[h]['districts_improved_mae']}/{summary[h]['districts_total']}")
    print(f"  Mean RMSE improvement:  {summary[h]['mean_rmse_improvement_pct']:.2f}%")
    print(f"  Median RMSE improvement:{summary[h]['median_rmse_improvement_pct']:.2f}%")
    print(f"  Best district RMSE:     {summary[h]['max_rmse_improvement_pct']:.2f}%")
    print(f"  Worst district RMSE:    {summary[h]['min_rmse_improvement_pct']:.2f}%")


# ============================================================
# TOP 5 / BOTTOM 5 DISTRICTS PER HORIZON
# ============================================================

print()
print("=" * 80)
print("TOP 5 / BOTTOM 5 DISTRICTS BY RMSE IMPROVEMENT")
print("=" * 80)

for h in ["h12", "h24", "h72"]:
    sub = df[df["horizon"] == h].sort_values("rmse_improvement_pct", ascending=False)

    print()
    print(f"=== {h.upper()} — Top 5 improved ===")
    for _, row in sub.head(5).iterrows():
        print(f"  {row['district_name']:<20} {row['rmse_improvement_pct']:>7.2f}%")

    print()
    print(f"=== {h.upper()} — Bottom 5 ===")
    for _, row in sub.tail(5).iterrows():
        print(f"  {row['district_name']:<20} {row['rmse_improvement_pct']:>7.2f}%")


# ============================================================
# SAVE SUMMARY
# ============================================================

with open(SUMMARY_FILE, "w") as f:
    json.dump(summary, f, indent=2)

print()
print(f"Summary saved: {SUMMARY_FILE}")
print()
print("=" * 80)
print("STEP 19 COMPLETE")
print("=" * 80)