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
BASELINE_METRICS = ML_DIR / "phase51r_baseline_metrics.json"
NWP_METRICS = ML_DIR / "phase52_nwp_metrics.json"
COMPARISON = ML_DIR / "phase51r_vs_phase52.csv"


# ============================================================
# DIAGNOSTIC
# ============================================================

print("=" * 80)
print("PHASE 5.2 — INDEPENDENT VERIFICATION")
print("=" * 80)

checks = []


# ------------------------------------------------------------
# CHECK 1 — Required horizons
# ------------------------------------------------------------
base = pd.read_parquet(BASELINE_PRED)
nwp = pd.read_parquet(NWP_PRED)

expected_horizons = {"h12", "h24", "h72"}
base_h = set(base["horizon"].unique())
nwp_h = set(nwp["horizon"].unique())

ok = base_h == expected_horizons and nwp_h == expected_horizons
checks.append(("Required horizons (H+12, H+24, H+72)", ok))
print(f"[{'PASS' if ok else 'FAIL'}] Required horizons present")


# ------------------------------------------------------------
# CHECK 2 — All 50 districts
# ------------------------------------------------------------
base_d = base["district_id"].nunique()
nwp_d = nwp["district_id"].nunique()

ok = base_d == 50 and nwp_d == 50
checks.append(("50 districts present", ok))
print(f"[{'PASS' if ok else 'FAIL'}] Districts: baseline={base_d}, nwp={nwp_d}")


# ------------------------------------------------------------
# CHECK 3 — No duplicate rows
# ------------------------------------------------------------
KEYS = ["district_id", "horizon", "forecast_issue_time_utc", "forecast_lead_hours"]

base_dups = base.duplicated(subset=KEYS).sum()
nwp_dups = nwp.duplicated(subset=KEYS).sum()

ok = base_dups == 0 and nwp_dups == 0
checks.append(("No duplicate rows", ok))
print(f"[{'PASS' if ok else 'FAIL'}] Duplicates: baseline={base_dups}, nwp={nwp_dups}")


# ------------------------------------------------------------
# CHECK 4 — No NaN predictions
# ------------------------------------------------------------
base_nan = base["y_pred"].isna().sum()
nwp_nan = nwp["y_pred"].isna().sum()

ok = base_nan == 0 and nwp_nan == 0
checks.append(("No NaN predictions", ok))
print(f"[{'PASS' if ok else 'FAIL'}] NaNs: baseline={base_nan}, nwp={nwp_nan}")


# ------------------------------------------------------------
# CHECK 5 — No negative predictions
# ------------------------------------------------------------
base_neg = (base["y_pred"] < 0).sum()
nwp_neg = (nwp["y_pred"] < 0).sum()

ok = base_neg == 0 and nwp_neg == 0
checks.append(("No negative predictions", ok))
print(f"[{'PASS' if ok else 'FAIL'}] Negatives: baseline={base_neg}, nwp={nwp_neg}")


# ------------------------------------------------------------
# CHECK 6 — Issue time precedes valid time
# ------------------------------------------------------------
base_ok = (
    pd.to_datetime(base["forecast_issue_time_utc"])
    < pd.to_datetime(base["forecast_valid_time_utc"])
).all()
nwp_ok = (
    pd.to_datetime(nwp["forecast_issue_time_utc"])
    < pd.to_datetime(nwp["forecast_valid_time_utc"])
).all()

ok = bool(base_ok) and bool(nwp_ok)
checks.append(("Issue time precedes valid time", ok))
print(f"[{'PASS' if ok else 'FAIL'}] Issue < valid time")


# ------------------------------------------------------------
# CHECK 7 — valid_time == issue_time + lead
# ------------------------------------------------------------
for name, df in [("baseline", base), ("nwp", nwp)]:
    issue = pd.to_datetime(df["forecast_issue_time_utc"])
    lead = pd.to_timedelta(df["forecast_lead_hours"], unit="h")
    valid = pd.to_datetime(df["forecast_valid_time_utc"])
    diff = (valid - (issue + lead)).abs()
    mismatches = (diff > pd.Timedelta(seconds=1)).sum()

    ok = mismatches == 0
    checks.append((f"valid_time = issue_time + lead ({name})", ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {mismatches} mismatches")


# ------------------------------------------------------------
# CHECK 8 — Metrics reproduce
# ------------------------------------------------------------
with open(BASELINE_METRICS) as f:
    base_metrics = json.load(f)
with open(NWP_METRICS) as f:
    nwp_metrics = json.load(f)

for key, pred_df in [("phase51r", base), ("phase52", nwp)]:
    metrics = base_metrics if key == "phase51r" else nwp_metrics

    for h_key, m in metrics.items():
        h_num = int(m["horizon"])
        sub = pred_df[pred_df["forecast_lead_hours"] == h_num]

        if len(sub) == 0:
            continue

        rmse_recomputed = np.sqrt(
            mean_squared_error(sub["y_true"], sub["y_pred"])
        )

        diff = abs(rmse_recomputed - m["rmse"])
        ok = diff < 1e-6
        checks.append((f"RMSE reproduces ({key} H+{h_num})", ok))
        print(
            f"[{'PASS' if ok else 'FAIL'}] {key} H+{h_num}: "
            f"stored={m['rmse']:.6f}, recomputed={rmse_recomputed:.6f}, "
            f"diff={diff:.2e}"
        )


# ------------------------------------------------------------
# CHECK 9 — No target leakage (nwp features not identical to target)
# ------------------------------------------------------------
# Sample check: NWP predictions at H+72 should NOT be perfectly correlated
# with observed target (would indicate leakage)
h72 = nwp[nwp["forecast_lead_hours"] == 72]
corr = h72["y_true"].corr(h72["y_pred"])
ok = corr < 0.999
checks.append(("No perfect target correlation (no leakage)", ok))
print(f"[{'PASS' if ok else 'FAIL'}] H+72 correlation: {corr:.6f}")


# ------------------------------------------------------------
# CHECK 10 — NWP improves over baseline
# ------------------------------------------------------------
comp = pd.read_csv(COMPARISON)

all_improved = (comp["RMSE Improvement %"] > 0).all()
checks.append(("NWP improves RMSE at all horizons", all_improved))
print(
    f"[{'PASS' if all_improved else 'FAIL'}] "
    f"All horizons improved: {list(comp['RMSE Improvement %'])}"
)


# ------------------------------------------------------------
# CHECK 11 — Train/val/test no overlap
# ------------------------------------------------------------
# The split is defined by issue time. Verify:
# test issue times are all > validation end
TRAIN_END = pd.Timestamp("2021-07-01", tz="UTC")
VAL_END = pd.Timestamp("2022-01-01", tz="UTC")

nwp_issue = pd.to_datetime(nwp["forecast_issue_time_utc"])
test_min = nwp_issue.min()

ok = nwp_issue.min() >= VAL_END
checks.append(("Test period starts after validation end", ok))
print(f"[{'PASS' if ok else 'FAIL'}] Test min issue: {nwp_issue.min()}")


# ------------------------------------------------------------
# CHECK 12 — District count per horizon
# ------------------------------------------------------------
ok = True
for h in ["h12", "h24", "h72"]:
    n = nwp[nwp["horizon"] == h]["district_id"].nunique()
    if n != 50:
        ok = False
        print(f"[FAIL] H+{h}: only {n} districts")

checks.append(("50 districts per horizon", ok))
print(f"[{'PASS' if ok else 'FAIL'}] 50 districts per horizon")


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 80)
print("VERIFICATION SUMMARY")
print("=" * 80)
print()

passed = sum(1 for _, ok in checks if ok)
total = len(checks)

for name, ok in checks:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")

print()
print(f"Passed: {passed}/{total}")

if passed == total:
    print()
    print("=" * 80)
    print("PHASE 5.2 — VERIFIED")
    print("=" * 80)
else:
    print()
    print("=" * 80)
    print("PHASE 5.2 — VERIFICATION FAILED")
    print("=" * 80)
    raise SystemExit(1)