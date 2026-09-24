from pathlib import Path
import json

import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

TIGGE_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "nwp"
    / "tigge_district_forecasts.parquet"
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
    / "nwp"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "phase52_training_dataset.parquet"
REPORT_FILE = OUTPUT_DIR / "phase52_build_report.json"


# ============================================================
# CONFIG
# ============================================================

TARGET = "p_pvgis_kw_per_kwp"

NWP_FEATURE_COLUMNS = [
    "temperature_2m_c",
    "wind_speed_10m_ms",
    "wind_direction_10m_deg",
    "cloud_cover_fraction",
]

TIGGE_METADATA_COLUMNS = [
    "forecast_issue_time_utc",
    "forecast_valid_time_utc",
    "forecast_lead_hours",
    "district_id",
    "district_name",
    "region_id",
    "region_name",
    "latitude",
    "longitude",
    "nwp_grid_latitude",
    "nwp_grid_longitude",
    "nwp_distance_km",
]

OUTPUT_COLUMNS = (
    TIGGE_METADATA_COLUMNS
    + NWP_FEATURE_COLUMNS
    + [TARGET]
)


# ============================================================
# START
# ============================================================

print("=" * 80)
print("STEP 14 — BUILD PHASE 5.2 NWP + PVGIS TRAINING DATASET")
print("=" * 80)

print()
print(f"TIGGE input : {TIGGE_FILE}")
print(f"PVGIS input : {FEATURES_FILE}")


# ============================================================
# CHECK INPUT FILES
# ============================================================

if not TIGGE_FILE.exists():
    raise FileNotFoundError(f"TIGGE file not found: {TIGGE_FILE}")

if not FEATURES_FILE.exists():
    raise FileNotFoundError(f"Features file not found: {FEATURES_FILE}")


# ============================================================
# LOAD TIGGE
# ============================================================

print()
print("Loading TIGGE district forecasts...")

tigge = pd.read_parquet(TIGGE_FILE)

print(f"  Rows: {len(tigge):,}")
print(f"  Columns: {len(tigge.columns)}")


required_tigge_columns = (
    TIGGE_METADATA_COLUMNS
    + NWP_FEATURE_COLUMNS
)

missing_tigge_columns = [
    c for c in required_tigge_columns
    if c not in tigge.columns
]

if missing_tigge_columns:
    raise RuntimeError(
        "Missing TIGGE columns:\n"
        + "\n".join(f"  - {c}" for c in missing_tigge_columns)
    )


# ============================================================
# TIME NORMALIZATION
# ============================================================

print()
print("Normalizing TIGGE timestamps...")

tigge["forecast_issue_time_utc"] = pd.to_datetime(
    tigge["forecast_issue_time_utc"],
    utc=True,
)

tigge["forecast_valid_time_utc"] = pd.to_datetime(
    tigge["forecast_valid_time_utc"],
    utc=True,
)


# ============================================================
# VALIDATE TIGGE TIME RELATION
# ============================================================

print()
print("Checking forecast issue → valid time relation...")

expected_valid_time = (
    tigge["forecast_issue_time_utc"]
    + pd.to_timedelta(
        tigge["forecast_lead_hours"],
        unit="h",
    )
)

time_errors = (
    tigge["forecast_valid_time_utc"]
    != expected_valid_time
).sum()

print(f"  Time relation errors: {time_errors:,}")

if time_errors > 0:
    raise RuntimeError(
        f"TIGGE contains {time_errors:,} invalid "
        "issue_time + lead_time relationships."
    )


# ============================================================
# VALIDATE TIGGE LEADS
# ============================================================

expected_leads = {6, 12, 24, 72}

actual_leads = set(
    tigge["forecast_lead_hours"]
    .dropna()
    .astype(int)
    .unique()
)

print()
print(f"Expected leads: {sorted(expected_leads)}")
print(f"Actual leads:   {sorted(actual_leads)}")

if actual_leads != expected_leads:
    raise RuntimeError(
        f"Unexpected TIGGE lead times: {sorted(actual_leads)}"
    )


# ============================================================
# VALIDATE DISTRICTS
# ============================================================

district_count = tigge["district_id"].nunique()

print()
print(f"TIGGE districts: {district_count}")

if district_count != 50:
    raise RuntimeError(
        f"Expected 50 districts, found {district_count}."
    )


# ============================================================
# DUPLICATE TIGGE CHECK
# ============================================================

print()
print("Checking TIGGE duplicate forecast keys...")

tigge_key = [
    "district_id",
    "forecast_issue_time_utc",
    "forecast_valid_time_utc",
    "forecast_lead_hours",
]

duplicate_tigge = tigge.duplicated(tigge_key).sum()

print(f"  Duplicate rows: {duplicate_tigge:,}")

if duplicate_tigge > 0:
    raise RuntimeError(
        f"TIGGE contains {duplicate_tigge:,} duplicate forecast keys."
    )


# ============================================================
# CREATE LOCAL VALID TIME
# ============================================================

print()
print("Converting forecast valid time UTC → Africa/Tunis...")

tigge["valid_time_local"] = (
    tigge["forecast_valid_time_utc"]
    .dt.tz_convert("Africa/Tunis")
    .dt.tz_localize(None)
)

print(
    f"  UTC   : {tigge['forecast_valid_time_utc'].iloc[0]}"
)

print(
    f"  Local : {tigge['valid_time_local'].iloc[0]}"
)


# ============================================================
# LOAD PVGIS TARGET
# ============================================================

print()
print("Loading PVGIS target...")

target_df = pd.read_parquet(
    FEATURES_FILE,
    columns=[
        "district_id",
        "timestamp",
        TARGET,
    ],
)

target_df["timestamp"] = pd.to_datetime(
    target_df["timestamp"]
)

target_df = target_df.dropna(
    subset=[TARGET]
).copy()

print(f"  Rows:  {len(target_df):,}")
print(f"  Start: {target_df['timestamp'].min()}")
print(f"  End:   {target_df['timestamp'].max()}")


# ============================================================
# DUPLICATE TARGET CHECK
# ============================================================

print()
print("Checking PVGIS target duplicate keys...")

target_key = [
    "district_id",
    "timestamp",
]

duplicate_target = target_df.duplicated(
    target_key
).sum()

print(
    f"  Duplicate rows: {duplicate_target:,}"
)

if duplicate_target > 0:
    raise RuntimeError(
        f"PVGIS target contains {duplicate_target:,} "
        "duplicate district/timestamp keys."
    )


# ============================================================
# CHECK TARGET RANGE
# ============================================================

print()
print("Checking PVGIS target range...")

target_range_ok = target_df[TARGET].between(
    0,
    1.5,
).all()

print(
    f"  {TARGET}: "
    f"{'PASS' if target_range_ok else 'FAIL'}"
)

if not target_range_ok:
    raise RuntimeError(
        "PVGIS target contains values outside [0, 1.5]."
    )


# ============================================================
# MERGE
# ============================================================

print()
print("=" * 80)
print("MERGING TIGGE + PVGIS")
print("=" * 80)

target_for_merge = target_df.rename(
    columns={
        "timestamp": "valid_time_local"
    }
)

merged = tigge.merge(
    target_for_merge,
    on=[
        "district_id",
        "valid_time_local",
    ],
    how="inner",
    validate="many_to_one",
)

print()
print(f"TIGGE rows:   {len(tigge):,}")
print(f"Matched rows: {len(merged):,}")

match_rate = (
    100 * len(merged) / len(tigge)
)

print(
    f"Match rate:   {match_rate:.2f}%"
)


# ============================================================
# MATCH QUALITY
# ============================================================

if len(merged) == 0:
    raise RuntimeError(
        "Zero TIGGE/PVGIS rows matched."
    )

if match_rate < 90:
    raise RuntimeError(
        f"Match rate is only {match_rate:.2f}%. "
        "Investigate timezone or timestamp alignment."
    )


# ============================================================
# VALIDATE FINAL DATASET
# ============================================================

print()
print("=" * 80)
print("FINAL VALIDATION")
print("=" * 80)

print()
print(f"Shape: {merged.shape}")

print(
    f"Districts: "
    f"{merged['district_id'].nunique()}"
)

print(
    f"Leads: "
    f"{sorted(merged['forecast_lead_hours'].unique())}"
)

print()
print("Issue time range:")
print(
    f"  {merged['forecast_issue_time_utc'].min()}"
)
print(
    f"  {merged['forecast_issue_time_utc'].max()}"
)


# ============================================================
# NWP MISSING VALUES
# ============================================================

print()
print("NWP missing values:")

for col in NWP_FEATURE_COLUMNS:
    n = merged[col].isna().sum()

    print(
        f"  {col:30s}: {n:,}"
    )

    if n > 0:
        raise RuntimeError(
            f"NWP feature contains {n:,} missing values: {col}"
        )


# ============================================================
# TARGET MISSING VALUES
# ============================================================

target_missing = merged[TARGET].isna().sum()

print()
print(
    f"Target missing values: "
    f"{target_missing:,}"
)

if target_missing > 0:
    raise RuntimeError(
        "Target contains missing values."
    )


# ============================================================
# PHYSICAL RANGE CHECKS
# ============================================================

print()
print("Physical range checks:")

checks = {
    "temperature_2m_c":
        merged["temperature_2m_c"].between(
            -30,
            60,
        ).all(),

    "wind_speed_10m_ms":
        merged["wind_speed_10m_ms"].between(
            0,
            100,
        ).all(),

    "wind_direction_10m_deg":
        merged["wind_direction_10m_deg"].between(
            0,
            360,
        ).all(),

    "cloud_cover_fraction":
        merged["cloud_cover_fraction"].between(
            0,
            1,
        ).all(),

    "target":
        merged[TARGET].between(
            0,
            1.5,
        ).all(),
}

for name, ok in checks.items():

    print(
        f"  {name:30s}: "
        f"{'PASS' if ok else 'FAIL'}"
    )

    if not ok:
        raise RuntimeError(
            f"Physical range check failed: {name}"
        )


# ============================================================
# TARGET STATISTICS
# ============================================================

print()
print("Target statistics:")

print(
    merged[TARGET].describe()
)


print()
print("Target zeros / nighttime:")

zero_count = (
    merged[TARGET] == 0
).sum()

zero_share = (
    100 * zero_count / len(merged)
)

print(
    f"  Count: {zero_count:,}"
)

print(
    f"  Share: {zero_share:.2f}%"
)


# ============================================================
# PER-HORIZON STATISTICS
# ============================================================

print()
print("Per-horizon statistics:")

horizon_stats = {}

for lead in sorted(
    merged["forecast_lead_hours"].unique()
):

    sub = merged[
        merged["forecast_lead_hours"] == lead
    ]

    horizon_stats[str(int(lead))] = {
        "rows": int(len(sub)),
        "mean_target": float(
            sub[TARGET].mean()
        ),
        "max_target": float(
            sub[TARGET].max()
        ),
        "zero_share_pct": float(
            100 * (sub[TARGET] == 0).mean()
        ),
    }

    print(
        f"  H+{int(lead):<3d}: "
        f"n={len(sub):,} "
        f"mean={sub[TARGET].mean():.4f} "
        f"max={sub[TARGET].max():.4f} "
        f"zeros={100 * (sub[TARGET] == 0).mean():.1f}%"
    )


# ============================================================
# DAYLIGHT DIAGNOSTIC
# ============================================================

print()
print(
    "Daylight diagnostic "
    "(UTC hours 06–18):"
)

for lead in sorted(
    merged["forecast_lead_hours"].unique()
):

    sub = merged[
        (merged["forecast_lead_hours"] == lead)
        &
        (
            merged[
                "forecast_valid_time_utc"
            ].dt.hour.between(6, 18)
        )
    ]

    if len(sub) > 0:

        print(
            f"  H+{int(lead):<3d}: "
            f"n={len(sub):,} "
            f"mean={sub[TARGET].mean():.4f} "
            f"max={sub[TARGET].max():.4f}"
        )


# ============================================================
# SELECT FINAL MODEL COLUMNS
# ============================================================

print()
print("Selecting final modeling columns...")

merged = merged[
    OUTPUT_COLUMNS
].copy()


# ============================================================
# SORT
# ============================================================

merged = merged.sort_values(
    [
        "district_id",
        "forecast_issue_time_utc",
        "forecast_lead_hours",
    ]
).reset_index(drop=True)


# ============================================================
# FINAL DUPLICATE CHECK
# ============================================================

print()
print("Final duplicate check...")

final_key = [
    "district_id",
    "forecast_issue_time_utc",
    "forecast_lead_hours",
]

duplicate_final = merged.duplicated(
    final_key
).sum()

print(
    f"  Duplicate forecast rows: "
    f"{duplicate_final:,}"
)

if duplicate_final > 0:
    raise RuntimeError(
        "Final dataset contains duplicate forecast keys."
    )


# ============================================================
# SAVE
# ============================================================

print()
print("=" * 80)
print("SAVING")
print("=" * 80)

merged.to_parquet(
    OUTPUT_FILE,
    index=False,
)

print(
    f"Saved: {OUTPUT_FILE}"
)

print(
    f"Rows:  {len(merged):,}"
)

print(
    f"Size:  "
    f"{OUTPUT_FILE.stat().st_size / (1024 * 1024):.1f} MB"
)


# ============================================================
# REPORT
# ============================================================

report = {
    "step": "Phase 5.2 - Step 14",
    "tigge_rows": int(len(tigge)),
    "target_rows": int(len(target_df)),
    "matched_rows": int(len(merged)),
    "match_rate_pct": float(match_rate),

    "districts": int(
        merged["district_id"].nunique()
    ),

    "lead_times": [
        int(x)
        for x in sorted(
            merged[
                "forecast_lead_hours"
            ].unique()
        )
    ],

    "issue_time_min": str(
        merged[
            "forecast_issue_time_utc"
        ].min()
    ),

    "issue_time_max": str(
        merged[
            "forecast_issue_time_utc"
        ].max()
    ),

    "target_mean": float(
        merged[TARGET].mean()
    ),

    "target_max": float(
        merged[TARGET].max()
    ),

    "target_zero_share_pct": float(
        zero_share
    ),

    "nwp_feature_columns":
        NWP_FEATURE_COLUMNS,

    "timezone_conversion":
        "UTC -> Africa/Tunis",

    "output_file":
        str(OUTPUT_FILE),

    "horizon_statistics":
        horizon_stats,

    "validation": {
        "tigge_time_relation": "PASS",
        "lead_times": "PASS",
        "district_count": "PASS",
        "duplicate_tigge_keys": "PASS",
        "duplicate_target_keys": "PASS",
        "missing_nwp": "PASS",
        "missing_target": "PASS",
        "physical_ranges": "PASS",
        "final_duplicate_keys": "PASS",
    },
}


with open(
    REPORT_FILE,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        report,
        f,
        indent=2,
    )


print(
    f"Report: {REPORT_FILE}"
)

print()
print("=" * 80)
print("STEP 14 COMPLETE")
print("=" * 80)