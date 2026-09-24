from pathlib import Path
import json

import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

PHASE53_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase53"
)

NATIONAL_FILE = PHASE53_DIR / "national_mw_predictions.parquet"
REGIONAL_FILE = PHASE53_DIR / "regional_mw_predictions.parquet"

OUTPUT_DIR = PHASE53_DIR
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DAILY_FILE = OUTPUT_DIR / "national_daily_profile.parquet"
DIURNAL_FILE = OUTPUT_DIR / "national_diurnal_analysis.parquet"
SUMMARY_FILE = OUTPUT_DIR / "phase61_grid_impact_summary.json"


# ============================================================
# LOAD
# ============================================================

print("=" * 80)
print("STEP 21 — PHASE 6.1 GRID IMPACT ANALYSIS (CORRECTED)")
print("=" * 80)

national = pd.read_parquet(NATIONAL_FILE)
national["forecast_valid_time_utc"] = pd.to_datetime(
    national["forecast_valid_time_utc"], utc=True
)

print()
print(f"Rows: {len(national):,}")
print(f"Horizons: {sorted(national['horizon'].unique())}")
print(f"Valid UTC hours present: {sorted(national['forecast_valid_time_utc'].dt.hour.unique())}")


# ============================================================
# SEPARATE BY TIME OF DAY
# ============================================================

# Because TIGGE samples only give us 00:00 and 12:00 UTC,
# we separate by time of day to avoid computing ramps across
# mismatched intervals.

national["valid_hour"] = national["forecast_valid_time_utc"].dt.hour
national["valid_date"] = national["forecast_valid_time_utc"].dt.date

print()
print("Sample distribution by valid hour and horizon:")
print(national.groupby(["horizon", "valid_hour"]).size().unstack(fill_value=0).to_string())


# ============================================================
# DIURNAL ANALYSIS
# ============================================================

print()
print("=" * 80)
print("DIURNAL ANALYSIS (night vs peak)")
print("=" * 80)

diurnal_summary = {}

for h in ["h12", "h24", "h72"]:
    sub = national[national["horizon"] == h]

    night = sub[sub["valid_hour"] == 0]["national_mw"]
    noon = sub[sub["valid_hour"] == 12]["national_mw"]

    night_mean = float(night.mean())
    noon_mean = float(noon.mean())
    diurnal_swing = noon_mean - night_mean

    diurnal_summary[h] = {
        "night_mean_mw": night_mean,
        "night_max_mw": float(night.max()),
        "noon_mean_mw": noon_mean,
        "noon_max_mw": float(noon.max()),
        "diurnal_swing_mw": float(diurnal_swing),
        "sample_count_night": int(len(night)),
        "sample_count_noon": int(len(noon)),
    }

    print()
    print(f"=== {h.upper()} ===")
    print(f"  Night (00:00 UTC): mean={night_mean:>7.2f} MW  max={night.max():>7.2f} MW  n={len(night)}")
    print(f"  Noon  (12:00 UTC): mean={noon_mean:>7.2f} MW  max={noon.max():>7.2f} MW  n={len(noon)}")
    print(f"  Diurnal swing:     {diurnal_swing:>7.2f} MW")


# ============================================================
# DAILY PEAK ANALYSIS (using 12:00 UTC samples only)
# ============================================================

print()
print("=" * 80)
print("DAILY PEAK ANALYSIS (12:00 UTC samples)")
print("=" * 80)

daily_peaks = national[national["valid_hour"] == 12].copy()
daily_peaks = daily_peaks.sort_values(["horizon", "forecast_valid_time_utc"])

# Compute day-to-day change for each horizon
daily_peaks["daily_ramp_mw"] = (
    daily_peaks.groupby("horizon")["national_mw"].diff()
)
daily_peaks["abs_daily_ramp_mw"] = daily_peaks["daily_ramp_mw"].abs()

daily_summary = {}

for h in ["h12", "h24", "h72"]:
    sub = daily_peaks[daily_peaks["horizon"] == h]
    ramps = sub["abs_daily_ramp_mw"].dropna()

    daily_summary[h] = {
        "n": int(len(sub)),
        "mean_peak_mw": float(sub["national_mw"].mean()),
        "max_peak_mw": float(sub["national_mw"].max()),
        "std_peak_mw": float(sub["national_mw"].std()),
        "mean_daily_ramp_mw": float(ramps.mean()),
        "max_daily_ramp_mw": float(ramps.max()),
        "p95_daily_ramp_mw": float(ramps.quantile(0.95)),
        "p99_daily_ramp_mw": float(ramps.quantile(0.99)),
    }

    print()
    print(f"=== {h.upper()} ===")
    print(f"  Mean peak:        {sub['national_mw'].mean():>7.2f} MW")
    print(f"  Max peak:         {sub['national_mw'].max():>7.2f} MW")
    print(f"  Std of peaks:     {sub['national_mw'].std():>7.2f} MW")
    print(f"  Mean daily ramp:  {ramps.mean():>7.2f} MW/day")
    print(f"  Max daily ramp:   {ramps.max():>7.2f} MW/day")
    print(f"  p95 daily ramp:   {ramps.quantile(0.95):>7.2f} MW/day")
    print(f"  p99 daily ramp:   {ramps.quantile(0.99):>7.2f} MW/day")


# ============================================================
# RESERVE PROXY (based on daily peak variability)
# ============================================================

print()
print("=" * 80)
print("RESERVE PROXY")
print("=" * 80)

reserve_summary = {}

for h in ["h12", "h24", "h72"]:
    sub = daily_peaks[daily_peaks["horizon"] == h]

    mean_peak = sub["national_mw"].mean()
    std_peak = sub["national_mw"].std()
    p95_peak = sub["national_mw"].quantile(0.95)

    # Reserve proxy: cover forecast variability
    # Very rough — not actual STEG reserve requirements
    reserve_p95 = p95_peak - mean_peak

    reserve_summary[h] = {
        "mean_peak_mw": float(mean_peak),
        "p95_peak_mw": float(p95_peak),
        "reserve_proxy_mw": float(reserve_p95),
    }

    print()
    print(f"=== {h.upper()} ===")
    print(f"  Mean peak:         {mean_peak:>7.2f} MW")
    print(f"  P95 peak:          {p95_peak:>7.2f} MW")
    print(f"  Reserve proxy:     {reserve_p95:>7.2f} MW (p95 − mean)")


print()
print("NOTE: Reserve proxy is a decision-support indicator, NOT an actual")
print("      STEG reserve requirement. For operational use, train quantile")
print("      models and use (P90 - P10) at the national level.")


# ============================================================
# SAVE
# ============================================================

print()
print("=" * 80)
print("SAVING")
print("=" * 80)

daily_peaks.to_parquet(DAILY_FILE, index=False)
print(f"Saved: {DAILY_FILE}")

national.to_parquet(DIURNAL_FILE, index=False)
print(f"Saved: {DIURNAL_FILE}")

summary = {
    "phase": "6.1",
    "data_limitation": (
        "TIGGE 6-hourly samples give only 00:00 and 12:00 UTC valid times. "
        "Hourly ramp rates cannot be computed. Daily ramp rates and diurnal "
        "swings are reported instead."
    ),
    "diurnal_analysis": diurnal_summary,
    "daily_peak_analysis": daily_summary,
    "reserve_proxy": reserve_summary,
}

with open(SUMMARY_FILE, "w") as f:
    json.dump(summary, f, indent=2)

print(f"Summary: {SUMMARY_FILE}")

print()
print("=" * 80)
print("STEP 21 COMPLETE — PHASE 6.1 GRID IMPACT DONE (CORRECTED)")
print("=" * 80)