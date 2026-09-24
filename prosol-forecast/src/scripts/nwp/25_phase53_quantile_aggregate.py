from pathlib import Path
import json

import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

QUANTILE_PRED = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase52"
    / "phase52_quantile_predictions_calibrated.parquet"
)

CAPACITY_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "prosol_district_capacity.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase53"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DISTRICT_Q_FILE = OUTPUT_DIR / "district_quantile_mw.parquet"
REGIONAL_Q_FILE = OUTPUT_DIR / "regional_quantile_mw.parquet"
NATIONAL_Q_FILE = OUTPUT_DIR / "national_quantile_mw.parquet"
SUMMARY_FILE = OUTPUT_DIR / "phase53_quantile_summary.json"


# ============================================================
# LOAD
# ============================================================

print("=" * 80)
print("STEP 25 — PHASE 5.3 QUANTILE AGGREGATION")
print("=" * 80)

if not QUANTILE_PRED.exists():
    raise FileNotFoundError(
        f"Missing calibrated quantile predictions:\n{QUANTILE_PRED}"
    )

preds = pd.read_parquet(QUANTILE_PRED)
preds["forecast_issue_time_utc"] = pd.to_datetime(
    preds["forecast_issue_time_utc"], utc=True
)
preds["forecast_valid_time_utc"] = pd.to_datetime(
    preds["forecast_valid_time_utc"], utc=True
)

print()
print(f"Quantile predictions: {len(preds):,} rows")

required = ["y_pred_p10_calibrated", "y_pred_p50", "y_pred_p90_calibrated", "y_true"]
missing_cols = [c for c in required if c not in preds.columns]
if missing_cols:
    raise ValueError(f"Missing required columns: {missing_cols}")


# ============================================================
# LOAD CAPACITY
# ============================================================

capacity = pd.read_csv(CAPACITY_FILE)
capacity = capacity[
    ["district_id", "district_name", "region_name", "capacity_mw"]
].copy()
capacity["district_id"] = capacity["district_id"].astype(int)
capacity["capacity_mw"] = pd.to_numeric(capacity["capacity_mw"], errors="coerce")

print(f"Capacity file: {len(capacity)} districts")
print(f"Total capacity: {capacity['capacity_mw'].sum():.1f} MW")


# ============================================================
# MERGE
# ============================================================

preds = preds.merge(
    capacity[["district_id", "capacity_mw", "region_name"]],
    on="district_id",
    how="left",
)

if preds["capacity_mw"].isna().sum() > 0:
    raise ValueError("Some districts have no capacity.")

region_lookup = (
    capacity[["region_name"]]
    .drop_duplicates()
    .sort_values("region_name")
    .reset_index(drop=True)
)
region_lookup["region_id"] = region_lookup.index + 1
preds = preds.merge(region_lookup, on="region_name", how="left")


# ============================================================
# DISTRICT MW CONVERSION (clip to zero)
# ============================================================

print()
print("=" * 80)
print("DISTRICT MW CONVERSION (clipped to zero)")
print("=" * 80)

preds["district_mw_p10"] = np.maximum(
    0, preds["y_pred_p10_calibrated"] * preds["capacity_mw"]
)
preds["district_mw_p50"] = np.maximum(
    0, preds["y_pred_p50"] * preds["capacity_mw"]
)
preds["district_mw_p90"] = np.maximum(
    0, preds["y_pred_p90_calibrated"] * preds["capacity_mw"]
)
preds["district_mw_true"] = preds["y_true"] * preds["capacity_mw"]

district_out = preds[[
    "district_id", "district_name",
    "region_id", "region_name",
    "forecast_issue_time_utc", "forecast_valid_time_utc",
    "forecast_lead_hours", "horizon",
    "capacity_mw",
    "y_true",
    "y_pred_p10_calibrated", "y_pred_p50", "y_pred_p90_calibrated",
    "district_mw_p10", "district_mw_p50", "district_mw_p90",
    "district_mw_true",
]].copy()

district_out.to_parquet(DISTRICT_Q_FILE, index=False)
print(f"District rows: {len(district_out):,}")
print(f"Saved: {DISTRICT_Q_FILE}")


# ============================================================
# REGIONAL AGGREGATION
# ============================================================

print()
print("=" * 80)
print("REGIONAL AGGREGATION")
print("=" * 80)

group_keys = [
    "region_id", "region_name",
    "forecast_issue_time_utc", "forecast_valid_time_utc",
    "forecast_lead_hours", "horizon",
]

regional = (
    preds
    .groupby(group_keys, as_index=False)
    .agg(
        n_districts=("district_id", "nunique"),
        capacity_mw=("capacity_mw", "sum"),
        regional_mw_p10=("district_mw_p10", "sum"),
        regional_mw_p50=("district_mw_p50", "sum"),
        regional_mw_p90=("district_mw_p90", "sum"),
        regional_mw_true=("district_mw_true", "sum"),
    )
)

print(f"Regional rows: {len(regional):,}")
regional.to_parquet(REGIONAL_Q_FILE, index=False)
print(f"Saved: {REGIONAL_Q_FILE}")


# ============================================================
# NATIONAL AGGREGATION
# ============================================================

print()
print("=" * 80)
print("NATIONAL AGGREGATION")
print("=" * 80)

national_keys = [
    "forecast_issue_time_utc", "forecast_valid_time_utc",
    "forecast_lead_hours", "horizon",
]

national = (
    regional
    .groupby(national_keys, as_index=False)
    .agg(
        n_regions=("region_id", "nunique"),
        capacity_mw=("capacity_mw", "sum"),
        national_mw_p10=("regional_mw_p10", "sum"),
        national_mw_p50=("regional_mw_p50", "sum"),
        national_mw_p90=("regional_mw_p90", "sum"),
        national_mw_true=("regional_mw_true", "sum"),
    )
)

print(f"National rows: {len(national):,}")
print(f"Capacity: {national['capacity_mw'].iloc[0]:.1f} MW")


# ============================================================
# NATIONAL EMPIRICAL QUANTILE CONSTRUCTION
# ============================================================

print()
print("=" * 80)
print("NATIONAL EMPIRICAL QUANTILE CONSTRUCTION")
print("=" * 80)

nat_calib_mask = national["forecast_issue_time_utc"] < "2022-07-01"

error_quantiles = {}

for h in sorted(national["horizon"].unique()):

    sub = national[(national["horizon"] == h) & nat_calib_mask]

    if len(sub) < 30:
        continue

    y_true = sub["national_mw_true"].values
    p50 = sub["national_mw_p50"].values

    errors = y_true - p50

    p10_err = float(np.percentile(errors, 10))
    p90_err = float(np.percentile(errors, 90))

    error_quantiles[h] = {
        "p10_error": p10_err,
        "p90_error": p90_err,
        "n_calibration": int(len(sub)),
    }

    print(
        f"  {h.upper()}: P10 error={p10_err:+.2f} MW   "
        f"P90 error={p90_err:+.2f} MW   n={len(sub)}"
    )

# Apply
national["national_mw_p10_calibrated"] = national["national_mw_p10"]
national["national_mw_p90_calibrated"] = national["national_mw_p90"]

for h, info in error_quantiles.items():
    mask = national["horizon"] == h
    p50 = national.loc[mask, "national_mw_p50"].values

    p10 = np.maximum(0, p50 + info["p10_error"])
    p90 = np.maximum(p50, p50 + info["p90_error"])

    national.loc[mask, "national_mw_p10_calibrated"] = p10
    national.loc[mask, "national_mw_p90_calibrated"] = p90

# Enforce ordering
for h in national["horizon"].unique():
    mask = national["horizon"] == h
    sub = national.loc[
        mask,
        ["national_mw_p10_calibrated", "national_mw_p50",
         "national_mw_p90_calibrated"],
    ].values
    sorted_vals = np.sort(sub, axis=1)
    national.loc[mask, "national_mw_p10_calibrated"] = sorted_vals[:, 0]
    national.loc[mask, "national_mw_p50"] = sorted_vals[:, 1]
    national.loc[mask, "national_mw_p90_calibrated"] = sorted_vals[:, 2]

national.to_parquet(NATIONAL_Q_FILE, index=False)
print()
print(f"Saved national: {NATIONAL_Q_FILE}")


# ============================================================
# VALIDATION
# ============================================================

print()
print("=" * 80)
print("VALIDATION")
print("=" * 80)

checks = []

for q in ["p10", "p50", "p90"]:
    reg_sum = (
        regional
        .groupby(national_keys)[f"regional_mw_{q}"]
        .sum()
        .reset_index()
        .rename(columns={f"regional_mw_{q}": f"regional_mw_{q}_recomputed"})
    )
    merged_check = national.merge(reg_sum, on=national_keys, how="left")
    ok = bool(np.allclose(
        merged_check[f"national_mw_{q}"],
        merged_check[f"regional_mw_{q}_recomputed"],
        rtol=1e-6,
    ))
    checks.append((f"National {q.upper()} = Σ regional", ok))
    print(f"[{'PASS' if ok else 'FAIL'}] National {q.upper()} = Σ regional")

for q_lo, q_hi in [("p10", "p50"), ("p50", "p90"), ("p10", "p90")]:
    violations = int(
        (national[f"national_mw_{q_lo}"] > national[f"national_mw_{q_hi}"]).sum()
    )
    ok = violations == 0
    checks.append((f"{q_lo.upper()} ≤ {q_hi.upper()}", ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {q_lo.upper()} ≤ {q_hi.upper()}: {violations}")

ok = regional["region_id"].nunique() == 7
checks.append(("7 regions", ok))
print(f"[{'PASS' if ok else 'FAIL'}] 7 regions")

ok = preds["district_id"].nunique() == 50
checks.append(("50 districts", ok))
print(f"[{'PASS' if ok else 'FAIL'}] 50 districts")

ok = set(national["horizon"].unique()) == {"h12", "h24", "h72"}
checks.append(("3 horizons", ok))
print(f"[{'PASS' if ok else 'FAIL'}] Horizons: {sorted(national['horizon'].unique())}")

nan_count = int(
    national[[
        "national_mw_p10_calibrated",
        "national_mw_p50",
        "national_mw_p90_calibrated",
    ]].isna().sum().sum()
)
ok = nan_count == 0
checks.append(("No NaN", ok))
print(f"[{'PASS' if ok else 'FAIL'}] NaN count: {nan_count}")

neg_count = int(
    (national[[
        "national_mw_p10_calibrated",
        "national_mw_p50",
        "national_mw_p90_calibrated",
    ]] < 0).sum().sum()
)
ok = neg_count == 0
checks.append(("No negatives", ok))
print(f"[{'PASS' if ok else 'FAIL'}] Negative count: {neg_count}")


# ============================================================
# COVERAGE
# ============================================================

print()
print("=" * 80)
print("COVERAGE — Held-out validation (2022-07 → 2022-12)")
print("=" * 80)

val_mask = national["forecast_issue_time_utc"] >= "2022-07-01"
coverage_report = {}

for h in sorted(national["horizon"].unique()):
    sub = national[(national["horizon"] == h) & val_mask]
    if len(sub) == 0:
        continue

    in_interval = (
        (sub["national_mw_true"] >= sub["national_mw_p10_calibrated"])
        & (sub["national_mw_true"] <= sub["national_mw_p90_calibrated"])
    )
    coverage = float(in_interval.mean())
    mean_width = float(
        (sub["national_mw_p90_calibrated"]
         - sub["national_mw_p10_calibrated"]).mean()
    )

    coverage_report[h] = {
        "coverage": coverage,
        "mean_width_mw": mean_width,
        "n_samples": int(len(sub)),
    }

    ok = 0.70 <= coverage <= 0.90
    checks.append((f"{h.upper()} coverage near 0.80", ok))

    print(
        f"  {h.upper()}: coverage={coverage:.4f}  "
        f"mean_width={mean_width:.2f} MW  n={len(sub)}  "
        f"[{'PASS' if ok else 'WARN'}]"
    )


# ============================================================
# SUMMARY
# ============================================================

summary = {
    "phase": "5.3-quantile",
    "method": "national empirical error quantiles",
    "district_rows": int(len(district_out)),
    "regional_rows": int(len(regional)),
    "national_rows": int(len(national)),
    "capacity_mw": float(national["capacity_mw"].iloc[0]),
    "horizons": sorted(national["horizon"].unique().tolist()),
    "national_error_quantiles": error_quantiles,
    "coverage_report": coverage_report,
}

with open(SUMMARY_FILE, "w") as f:
    json.dump(summary, f, indent=2)

print()
print(f"Summary: {SUMMARY_FILE}")


# ============================================================
# FINAL
# ============================================================

failed = [name for name, ok in checks if not ok]

print()
print("=" * 80)
if failed:
    print("VALIDATION ISSUES")
    print("=" * 80)
    for name in failed:
        print(f"  FAIL: {name}")
else:
    print("ALL QUANTILE CHECKS PASSED")
    print("=" * 80)
    print()
    print("Outputs:")
    print(f"  {DISTRICT_Q_FILE.name}")
    print(f"  {REGIONAL_Q_FILE.name}")
    print(f"  {NATIONAL_Q_FILE.name}")
    print(f"  {SUMMARY_FILE.name}")

print()
print("=" * 80)
print("STEP 25 COMPLETE")
print("=" * 80)