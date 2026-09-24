from pathlib import Path
import json

import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

BASELINE_DIR = PROJECT_ROOT / "data" / "processed" / "ml" / "phase52"

BASELINE_METRICS = BASELINE_DIR / "phase51r_baseline_metrics.json"
NWP_METRICS = BASELINE_DIR / "phase52_nwp_metrics.json"

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "ml" / "phase52"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

COMPARISON_CSV = OUTPUT_DIR / "phase51r_vs_phase52.csv"
COMPARISON_JSON = OUTPUT_DIR / "phase51r_vs_phase52.json"


# ============================================================
# LOAD
# ============================================================

print("=" * 80)
print("STEP 17 — PHASE 5.1-R vs PHASE 5.2 COMPARISON")
print("=" * 80)

with open(BASELINE_METRICS) as f:
    baseline = json.load(f)

with open(NWP_METRICS) as f:
    nwp = json.load(f)


# ============================================================
# BUILD COMPARISON TABLE
# ============================================================

rows = []

for key in sorted(baseline.keys()):
    b = baseline[key]
    n = nwp[key]

    h = b["horizon"]

    # Improvement percentages
    mae_imp = 100 * (b["mae"] - n["mae"]) / b["mae"]
    rmse_imp = 100 * (b["rmse"] - n["rmse"]) / b["rmse"]
    r2_delta = n["r2"] - b["r2"]
    skill_delta = n["skill_vs_daily"] - b["skill_vs_daily"]

    rows.append({
        "Horizon": f"H+{h}",
        "Phase 5.1-R MAE": b["mae"],
        "Phase 5.2 MAE": n["mae"],
        "MAE Improvement %": mae_imp,
        "Phase 5.1-R RMSE": b["rmse"],
        "Phase 5.2 RMSE": n["rmse"],
        "RMSE Improvement %": rmse_imp,
        "Phase 5.1-R R²": b["r2"],
        "Phase 5.2 R²": n["r2"],
        "R² Delta": r2_delta,
        "Phase 5.1-R Skill": b["skill_vs_daily"],
        "Phase 5.2 Skill": n["skill_vs_daily"],
        "Skill Delta (pp)": skill_delta * 100,
    })

df = pd.DataFrame(rows)
df.to_csv(COMPARISON_CSV, index=False)

with open(COMPARISON_JSON, "w") as f:
    json.dump(rows, f, indent=2)


# ============================================================
# DISPLAY
# ============================================================

print()
print("=" * 80)
print("COMPARISON — Phase 5.1-R (no NWP) vs Phase 5.2 (with TIGGE NWP)")
print("=" * 80)
print()

print(f"{'Horizon':<10} {'RMSE 5.1-R':>12} {'RMSE 5.2':>12} {'Improv %':>10} {'R² 5.1-R':>10} {'R² 5.2':>10} {'ΔR²':>10}")
print("-" * 80)
for _, r in df.iterrows():
    print(
        f"{r['Horizon']:<10} "
        f"{r['Phase 5.1-R RMSE']:>12.6f} "
        f"{r['Phase 5.2 RMSE']:>12.6f} "
        f"{r['RMSE Improvement %']:>9.2f}% "
        f"{r['Phase 5.1-R R²']:>10.6f} "
        f"{r['Phase 5.2 R²']:>10.6f} "
        f"{r['R² Delta']:>10.6f}"
    )

print()
print(f"{'Horizon':<10} {'MAE 5.1-R':>12} {'MAE 5.2':>12} {'Improv %':>10} {'Skill 5.1-R':>12} {'Skill 5.2':>12} {'ΔSkill (pp)':>12}")
print("-" * 80)
for _, r in df.iterrows():
    print(
        f"{r['Horizon']:<10} "
        f"{r['Phase 5.1-R MAE']:>12.6f} "
        f"{r['Phase 5.2 MAE']:>12.6f} "
        f"{r['MAE Improvement %']:>9.2f}% "
        f"{r['Phase 5.1-R Skill']:>12.6f} "
        f"{r['Phase 5.2 Skill']:>12.6f} "
        f"{r['Skill Delta (pp)']:>11.2f}"
    )

print()
print(f"Saved: {COMPARISON_CSV}")
print(f"Saved: {COMPARISON_JSON}")
print()
print("=" * 80)
print("STEP 17 COMPLETE")
print("=" * 80)