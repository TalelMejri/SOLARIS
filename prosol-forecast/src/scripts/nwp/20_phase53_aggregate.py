from pathlib import Path
import json

import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

PHASE52_PRED = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase52"
    / "phase52_nwp_predictions.parquet"
)

PV_REGISTRY = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "prosol_district_capacity.csv"
)

DISTRICT_MAPPING = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "district_region_mapping.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase53"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DISTRICT_MW_FILE = OUTPUT_DIR / "district_mw_predictions.parquet"
REGIONAL_MW_FILE = OUTPUT_DIR / "regional_mw_predictions.parquet"
NATIONAL_MW_FILE = OUTPUT_DIR / "national_mw_predictions.parquet"

SUMMARY_FILE = OUTPUT_DIR / "phase53_summary.json"


# ============================================================
# LOAD PHASE 5.2 PREDICTIONS
# ============================================================

print("=" * 80)
print("STEP 20 — PHASE 5.3 AGGREGATION")
print("=" * 80)

print()
print(f"Loading: {PHASE52_PRED}")

preds = pd.read_parquet(PHASE52_PRED)
print(f"Rows: {len(preds):,}")
print(f"Columns: {list(preds.columns)}")

# Parse timestamps
preds["forecast_issue_time_utc"] = pd.to_datetime(
    preds["forecast_issue_time_utc"], utc=True
)
preds["forecast_valid_time_utc"] = pd.to_datetime(
    preds["forecast_valid_time_utc"], utc=True
)


# ============================================================
# LOAD DISTRICT CAPACITY
# ============================================================

print()
print(f"Loading capacity: {PV_REGISTRY}")

pv = pd.read_csv(PV_REGISTRY)
print(f"PV registry rows: {len(pv)}")
print(f"Columns: {list(pv.columns)}")


# Detect capacity column
def find_col(df, candidates, name):
    for c in candidates:
        if c in df.columns:
            return c
    raise ValueError(f"Could not find {name} column in {list(df.columns)}")


id_col = find_col(pv, ["district_id", "id"], "district_id")
cap_col = find_col(
    pv,
    ["capacity_mw", "capacity", "installed_mw", "installed_capacity_mw"],
    "capacity",
)

capacity = pv[[id_col, cap_col]].copy()
capacity.columns = ["district_id", "capacity_mw"]
capacity["district_id"] = capacity["district_id"].astype(int)
capacity["capacity_mw"] = pd.to_numeric(capacity["capacity_mw"], errors="coerce")

print()
print("Capacity statistics:")
print(capacity["capacity_mw"].describe())

# Load region mapping
print()
print(f"Loading regions: {DISTRICT_MAPPING}")

mapping = pd.read_csv(DISTRICT_MAPPING)
print(f"Mapping rows: {len(mapping)}")
print(f"Columns: {list(mapping.columns)}")

map_id = find_col(mapping, ["district_id", "id"], "district_id")
map_region_id = find_col(mapping, ["region_id"], "region_id")
map_region_name = find_col(mapping, ["region_name"], "region_name")

regions = mapping[[map_id, map_region_id, map_region_name]].copy()
regions.columns = ["district_id", "region_id", "region_name"]
regions["district_id"] = regions["district_id"].astype(int)

# Merge into predictions
preds = preds.merge(capacity, on="district_id", how="left")
preds = preds.merge(regions, on="district_id", how="left")

missing_cap = preds["capacity_mw"].isna().sum()
missing_reg = preds["region_id"].isna().sum()

print()
print(f"Missing capacity: {missing_cap}")
print(f"Missing region:   {missing_reg}")

if missing_cap > 0:
    raise ValueError("Some districts have no capacity mapping.")

if missing_reg > 0:
    raise ValueError("Some districts have no region mapping.")


# ============================================================
# CONVERT NORMALIZED → DISTRICT MW
# ============================================================

print()
print("=" * 80)
print("DISTRICT-LEVEL MW CONVERSION")
print("=" * 80)

# The prediction is normalized PV production per kWp.
# Multiply by district capacity in MW to get MW output.
#
# Example:
#   y_pred = 0.45 (kW/kWp) × district capacity 26.4 MW → 11.88 MW
#
preds["district_mw"] = preds["y_pred"] * preds["capacity_mw"]
preds["district_mw_true"] = preds["y_true"] * preds["capacity_mw"]

print(f"District MW statistics:")
print(preds["district_mw"].describe())

# Save district MW predictions
district_out = preds[[
    "district_id",
    "district_name",
    "region_id",
    "region_name",
    "forecast_issue_time_utc",
    "forecast_valid_time_utc",
    "forecast_lead_hours",
    "horizon",
    "capacity_mw",
    "y_true",
    "y_pred",
    "district_mw",
    "district_mw_true",
]].copy()

district_out.to_parquet(DISTRICT_MW_FILE, index=False)
print()
print(f"Saved district MW: {DISTRICT_MW_FILE}")
print(f"Rows: {len(district_out):,}")


# ============================================================
# AGGREGATE DISTRICTS → REGIONS
# ============================================================

print()
print("=" * 80)
print("REGIONAL AGGREGATION")
print("=" * 80)

group_keys = [
    "region_id",
    "region_name",
    "forecast_issue_time_utc",
    "forecast_valid_time_utc",
    "forecast_lead_hours",
    "horizon",
]

regional = (
    preds
    .groupby(group_keys, as_index=False)
    .agg(
        n_districts=("district_id", "nunique"),
        capacity_mw=("capacity_mw", "sum"),
        regional_mw=("district_mw", "sum"),
        regional_mw_true=("district_mw_true", "sum"),
    )
)

print(f"Regional rows: {len(regional):,}")
print(f"Regions: {regional['region_id'].nunique()}")

print()
print("Regional capacity:")
print(
    regional
    .groupby(["region_id", "region_name"])["capacity_mw"]
    .first()
    .sort_values(ascending=False)
    .to_string()
)

regional.to_parquet(REGIONAL_MW_FILE, index=False)
print()
print(f"Saved regional: {REGIONAL_MW_FILE}")


# ============================================================
# AGGREGATE REGIONS → NATIONAL
# ============================================================

print()
print("=" * 80)
print("NATIONAL AGGREGATION")
print("=" * 80)

national_keys = [
    "forecast_issue_time_utc",
    "forecast_valid_time_utc",
    "forecast_lead_hours",
    "horizon",
]

national = (
    regional
    .groupby(national_keys, as_index=False)
    .agg(
        n_regions=("region_id", "nunique"),
        capacity_mw=("capacity_mw", "sum"),
        national_mw=("regional_mw", "sum"),
        national_mw_true=("regional_mw_true", "sum"),
    )
)

print(f"National rows: {len(national):,}")
print(f"Total national capacity: {national['capacity_mw'].iloc[0]:.1f} MW")

print()
print("National MW statistics:")
print(national["national_mw"].describe())

national.to_parquet(NATIONAL_MW_FILE, index=False)
print()
print(f"Saved national: {NATIONAL_MW_FILE}")


# ============================================================
# VALIDATION
# ============================================================

print()
print("=" * 80)
print("VALIDATION")
print("=" * 80)

# Check 1 — National MW = sum of regional MW
check1 = np.allclose(
    national["national_mw"].values,
    national.groupby(national_keys)["national_mw"].first().values,
)
print(f"[{'PASS' if check1 else 'FAIL'}] National MW = sum of regional MW")

# Check 2 — National capacity matches sum of all districts
total_cap = preds.groupby("district_id")["capacity_mw"].first().sum()
check2 = np.isclose(national["capacity_mw"].iloc[0], total_cap, rtol=1e-6)
print(f"[{'PASS' if check2 else 'FAIL'}] National capacity matches district sum: {total_cap:.1f} MW")

# Check 3 — Region count
check3 = regional["region_id"].nunique() == 7
print(f"[{'PASS' if check3 else 'FAIL'}] 7 regions: {regional['region_id'].nunique()}")

# Check 4 — District count
check4 = preds["district_id"].nunique() == 50
print(f"[{'PASS' if check4 else 'FAIL'}] 50 districts: {preds['district_id'].nunique()}")

# Check 5 — Horizons
check5 = set(preds["horizon"].unique()) == {"h12", "h24", "h72"}
print(f"[{'PASS' if check5 else 'FAIL'}] Horizons: {sorted(preds['horizon'].unique())}")

# Check 6 — No NaN in national MW
check6 = national["national_mw"].isna().sum() == 0
print(f"[{'PASS' if check6 else 'FAIL'}] No NaN in national MW")

# Check 7 — No negative MW
check7 = (national["national_mw"] >= 0).all()
print(f"[{'PASS' if check7 else 'FAIL'}] No negative national MW")


# ============================================================
# SAMPLE OUTPUT
# ============================================================

print()
print("=" * 80)
print("SAMPLE NATIONAL FORECAST")
print("=" * 80)

sample = national.head(10)[[
    "forecast_valid_time_utc",
    "horizon",
    "capacity_mw",
    "national_mw",
    "national_mw_true",
]]

print()
print(sample.to_string(index=False))


# ============================================================
# PEAK ANALYSIS
# ============================================================

print()
print("=" * 80)
print("PEAK ANALYSIS PER HORIZON")
print("=" * 80)

peak_summary = {}

for h in ["h12", "h24", "h72"]:
    sub = national[national["horizon"] == h]

    peak_mw = sub["national_mw"].max()
    peak_time = sub.loc[sub["national_mw"].idxmax(), "forecast_valid_time_utc"]
    mean_mw = sub["national_mw"].mean()

    peak_summary[h] = {
        "peak_mw": float(peak_mw),
        "peak_time": str(peak_time),
        "mean_mw": float(mean_mw),
        "capacity_mw": float(sub["capacity_mw"].iloc[0]),
        "peak_capacity_factor": float(peak_mw / sub["capacity_mw"].iloc[0]),
    }

    print()
    print(f"=== {h.upper()} ===")
    print(f"  Peak MW:       {peak_mw:>8.2f}")
    print(f"  Peak time:     {peak_time}")
    print(f"  Mean MW:       {mean_mw:>8.2f}")
    print(f"  Capacity:      {sub['capacity_mw'].iloc[0]:>8.2f} MW")
    print(f"  Peak CF:       {peak_mw / sub['capacity_mw'].iloc[0]:.4f}")


# ============================================================
# SAVE SUMMARY
# ============================================================

summary = {
    "phase": "5.3",
    "inputs": {
        "phase52_predictions": str(PHASE52_PRED),
        "pv_registry": str(PV_REGISTRY),
        "district_mapping": str(DISTRICT_MAPPING),
    },
    "outputs": {
        "district_mw": str(DISTRICT_MW_FILE),
        "regional_mw": str(REGIONAL_MW_FILE),
        "national_mw": str(NATIONAL_MW_FILE),
    },
    "scale": {
        "districts": int(preds["district_id"].nunique()),
        "regions": int(regional["region_id"].nunique()),
        "national_capacity_mw": float(national["capacity_mw"].iloc[0]),
        "horizons": sorted(preds["horizon"].unique()),
    },
    "validation": {
        "national_eq_region_sum": bool(check1),
        "capacity_matches": bool(check2),
        "region_count_ok": bool(check3),
        "district_count_ok": bool(check4),
        "horizons_ok": bool(check5),
        "no_nan": bool(check6),
        "no_negative": bool(check7),
    },
    "peak_analysis": peak_summary,
}

with open(SUMMARY_FILE, "w") as f:
    json.dump(summary, f, indent=2)

print()
print(f"Summary saved: {SUMMARY_FILE}")

print()
print("=" * 80)
print("STEP 20 COMPLETE — PHASE 5.3 AGGREGATION DONE")
print("=" * 80)