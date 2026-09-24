# """
# PHASE 5.2 - STEP 5: SINGLE-DISTRICT NWP TEST
# ==============================================

# Purpose
# -------
# Test the Open-Meteo SINGLE RUNS API on ONE district (Tunis Ville) before
# touching the other 49. This is a genuine forecast archive query: we ask
# for one specific model run, identified by its initialisation ("issue")
# time, and inspect the full forecast horizon it produced.

# This script does NOT use:
#   - ERA5 / Historical Weather API (reanalysis, not a forecast)
#   - Historical Forecast API (stitched "freshest available" series,
#     does not preserve issue-time/valid-time structure)

# It DOES use:
#   - Single Runs API (https://single-runs-api.open-meteo.com/v1/forecast)
#   - Model: ECMWF IFS HRES 9km ("ecmwf_ifs"), the only model with a
#     meaningfully long Single Runs archive (from 2024-03-14; all other
#     models only from 2026-04-02, which is too short for a real
#     train/val/test split).

# IMPORTANT
# ---------
# This script has NOT been executed against the live API from inside the
# Claude container - this environment's network allowlist blocks
# open-meteo.com entirely. Run this script yourself in an environment with
# real internet access (the same one the rest of the Prosol project lives
# in), then share stdout / the saved files back so the results can be
# verified and interpreted honestly, per the project's no-fabrication rule.

# Usage
# -----
#     pip install requests pandas
#     python step5_single_district_test.py --run 2024-06-01T00:00
#     python step5_single_district_test.py --run 2024-06-01T00:00 --run 2026-06-01T00:00
#         (second example straddles the 2026-05-12 IFS Cycle 49R1 -> 50R1
#         switch mentioned in Open-Meteo's docs - worth testing both sides
#         if your final training window crosses that date)
# """

# import argparse
# import json
# import sys
# from pathlib import Path

# import pandas as pd
# import requests

# # ---------------------------------------------------------------------------
# # District under test: TUNIS VILLE (district_id=1), from the real
# # district_coordinates.csv row provided for this project.
# # ---------------------------------------------------------------------------
# DISTRICT = {
#     "district_id": 1,
#     "district_name": "TUNIS VILLE",
#     "region_id": 1,
#     "region_name": "TUNIS",
#     "latitude": 36.788353,
#     "longitude": 10.186666,
# }

# SINGLE_RUNS_ENDPOINT = "https://single-runs-api.open-meteo.com/v1/forecast"

# # Candidate NWP feature set (from PROJECT_HANDOFF section 43), restricted to
# # variables actually offered by the Single Runs API's hourly parameter list.
# HOURLY_VARS = [
#     "temperature_2m",
#     "relative_humidity_2m",
#     "cloud_cover",
#     "cloud_cover_low",
#     "cloud_cover_mid",
#     "cloud_cover_high",
#     "wind_speed_10m",
#     "wind_direction_10m",
#     "wind_gusts_10m",
#     "precipitation",
#     "surface_pressure",
#     "shortwave_radiation",
#     "direct_radiation",
#     "diffuse_radiation",
#     "direct_normal_irradiance",
# ]

# MODEL = "ecmwf_ifs"  # ECMWF IFS HRES 9km, per Single Runs API docs
# EARLIEST_VALID_RUN = "2024-03-14T00:00"  # documented archive start for ecmwf_ifs


# def fetch_single_run(run_iso: str, forecast_days: int = 10) -> dict:
#     """Query the Single Runs API for one run of one district. Returns raw JSON."""
#     params = {
#         "latitude": DISTRICT["latitude"],
#         "longitude": DISTRICT["longitude"],
#         "run": run_iso,
#         "hourly": ",".join(HOURLY_VARS),
#         "models": MODEL,
#         "forecast_days": forecast_days,
#         "timezone": "UTC",  # keep raw response in UTC; convert to Africa/Tunis after
#     }
#     resp = requests.get(SINGLE_RUNS_ENDPOINT, params=params, timeout=30)
#     if resp.status_code != 200:
#         raise RuntimeError(
#             f"Open-Meteo returned HTTP {resp.status_code} for run={run_iso}: {resp.text[:500]}"
#         )
#     return resp.json()


# def to_dataframe(raw: dict, run_iso: str) -> pd.DataFrame:
#     """Convert raw JSON into a tidy dataframe with issue_time / valid_time / lead_hours."""
#     if "hourly" not in raw:
#         raise RuntimeError(f"No 'hourly' block in response. Keys present: {list(raw.keys())}")

#     hourly = raw["hourly"]
#     df = pd.DataFrame(hourly)
#     df["valid_time"] = pd.to_datetime(df["time"], utc=True)
#     df = df.drop(columns=["time"])

#     issue_time = pd.to_datetime(run_iso, utc=True)
#     df["issue_time"] = issue_time
#     df["lead_hours"] = (df["valid_time"] - issue_time).dt.total_seconds() / 3600.0

#     df["district_id"] = DISTRICT["district_id"]
#     df["model"] = MODEL

#     cols = ["district_id", "model", "issue_time", "valid_time", "lead_hours"] + HOURLY_VARS
#     return df[[c for c in cols if c in df.columns]]


# def verify(df: pd.DataFrame, run_iso: str) -> list[str]:
#     """
#     Independent sanity checks on the returned run. Mirrors the spirit of
#     verified/diagnostic.py from Phase 5.1: check, don't assume.
#     """
#     findings = []

#     # 1. hourly cadence with no gaps
#     diffs = df["valid_time"].diff().dropna()
#     if not (diffs == pd.Timedelta(hours=1)).all():
#         findings.append("FAIL: valid_time is not a continuous 1-hour series.")
#     else:
#         findings.append("PASS: valid_time is continuous hourly.")

#     # 2. first row should correspond to lead_hours == 0 (or very close to it)
#     first_lead = df["lead_hours"].iloc[0]
#     if first_lead != 0:
#         findings.append(
#             f"NOTE: first row lead_hours = {first_lead} (expected 0). "
#             f"Confirm whether the API returns data starting exactly at issue_time."
#         )
#     else:
#         findings.append("PASS: first row lead_hours == 0 (forecast starts at issue time).")

#     # 3. required horizons for Phase 5.1-matching multi-horizon setup
#     required_leads = [1, 6, 12, 24, 72]
#     available_leads = set(df["lead_hours"].astype(int))
#     missing = [h for h in required_leads if h not in available_leads]
#     if missing:
#         findings.append(f"FAIL: missing required lead times (hours): {missing}")
#     else:
#         findings.append(f"PASS: all required horizons present: {required_leads}")

#     # 4. max lead time / horizon length
#     findings.append(f"NOTE: max lead_hours returned = {df['lead_hours'].max()}")

#     # 5. null check per variable
#     null_counts = df[HOURLY_VARS].isna().sum()
#     nonzero_nulls = null_counts[null_counts > 0]
#     if len(nonzero_nulls) > 0:
#         findings.append(f"NOTE: null values present -> {nonzero_nulls.to_dict()}")
#     else:
#         findings.append("PASS: no null values in requested variables.")

#     # 6. archive-window sanity
#     run_dt = pd.to_datetime(run_iso, utc=True)
#     earliest = pd.to_datetime(EARLIEST_VALID_RUN, utc=True)
#     if run_dt < earliest:
#         findings.append(
#             f"FAIL: run={run_iso} is before documented ECMWF IFS HRES archive start "
#             f"({EARLIEST_VALID_RUN}). This run should not have returned data - "
#             f"if it did, treat the result with suspicion and re-check the docs."
#         )
#     else:
#         findings.append("PASS: requested run is within documented archive coverage.")

#     return findings


# def main():
#     parser = argparse.ArgumentParser(description="Phase 5.2 Step 5: single-district NWP test")
#     parser.add_argument(
#         "--run",
#         action="append",
#         required=True,
#         help="Run initialisation time(s), ISO 8601 no-seconds, e.g. 2024-06-01T00:00. "
#         "Repeat --run to test multiple runs in one call.",
#     )
#     parser.add_argument(
#         "--outdir",
#         default="./phase5_2_step5_output",
#         help="Where to save raw JSON and processed CSV.",
#     )
#     args = parser.parse_args()

#     outdir = Path(args.outdir)
#     outdir.mkdir(parents=True, exist_ok=True)

#     all_frames = []
#     for run_iso in args.run:
#         print(f"\n{'='*70}\nFetching run={run_iso} for district_id={DISTRICT['district_id']} "
#               f"({DISTRICT['district_name']})\n{'='*70}")
#         try:
#             raw = fetch_single_run(run_iso)
#         except Exception as e:
#             print(f"ERROR fetching run={run_iso}: {e}", file=sys.stderr)
#             continue

#         raw_path = outdir / f"raw_district{DISTRICT['district_id']:02d}_run_{run_iso.replace(':', '')}.json"
#         raw_path.write_text(json.dumps(raw, indent=2))
#         print(f"Saved raw response -> {raw_path}")

#         df = to_dataframe(raw, run_iso)
#         all_frames.append(df)

#         print("\n--- Data preview (first 5 rows) ---")
#         print(df.head().to_string())

#         print("\n--- Data preview (rows near lead_hours = 1, 6, 12, 24, 72) ---")
#         for h in [1, 6, 12, 24, 72]:
#             row = df[df["lead_hours"] == h]
#             if not row.empty:
#                 print(f"\nlead_hours={h}:")
#                 print(row.to_string(index=False))
#             else:
#                 print(f"\nlead_hours={h}: NOT FOUND")

#         print("\n--- Verification checks ---")
#         for line in verify(df, run_iso):
#             print(f"  {line}")

#     if all_frames:
#         combined = pd.concat(all_frames, ignore_index=True)
#         csv_path = outdir / f"processed_district{DISTRICT['district_id']:02d}.csv"
#         combined.to_csv(csv_path, index=False)
#         print(f"\nSaved combined processed CSV -> {csv_path}")
#         print(f"Total rows: {len(combined)}")
#     else:
#         print("\nNo runs succeeded - nothing to save.")


# if __name__ == "__main__":
#     main()


# from pathlib import Path
# import cdsapi

# PROJECT_ROOT = Path(__file__).resolve().parents[3]
# OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "nwp" / "tigge"
# OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# client = cdsapi.Client()

# request = {
#     "origin": "ecmwf",
#     "level_type": "single_level",
#     "variable": [
#         "10_m_u_component_of_wind",
#         "10_m_v_component_of_wind",
#         "2_m_temperature",
#         "total_cloud_cover",
#     ],
#     "year": "2019",
#     "month": "02",
#     "day": ["01"],  # Test only one day
#     "time": "00:00",
#     "forecast_type": "control_forecast",
#     "leadtime_hour": ["6", "12", "24", "72"],
#     "data_format": "grib",
#     "area": [37.6, 7.5, 30.0, 12.5],
# }

# output_file = OUTPUT_DIR / "test_feb2019_day01.grib"

# print("Requesting 2019-02-01...")
# try:
#     client.retrieve("tigge-forecasts", request, str(output_file))
#     print(f"SUCCESS: {output_file.stat().st_size / 1024:.1f} KB")
# except Exception as exc:
#     print(f"FAILED: {type(exc).__name__}")
#     print(f"Error: {exc}")


from pathlib import Path
from datetime import date
import calendar
import cdsapi
import time


PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "nwp"
    / "tigge_2019_02_diagnostic"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

client = cdsapi.Client()

YEAR = 2019
MONTH = 2

VARIABLES = [
    "10_m_u_component_of_wind",
    "10_m_v_component_of_wind",
    "2_m_temperature",
    "total_cloud_cover",
]

LEAD_TIMES = [
    "6",
    "12",
    "24",
    "72",
]

AREA = [
    37.6,
    7.5,
    30.0,
    12.5,
]

successful = []
failed = []


days_in_month = calendar.monthrange(YEAR, MONTH)[1]

print("=" * 90)
print("DIAGNOSTIC: TIGGE FEBRUARY 2019")
print("=" * 90)
print(f"Testing {days_in_month} individual 00 UTC runs")
print()


for day in range(1, days_in_month + 1):

    day_str = f"{day:02d}"

    date_str = (
        f"{YEAR}-{MONTH:02d}-{day_str}"
    )

    output_file = (
        OUTPUT_DIR
        / f"ecmwf_tigge_{date_str}_00.grib"
    )

    print()
    print("-" * 90)
    print(f"TESTING {date_str} 00:00 UTC")
    print("-" * 90)

    if (
        output_file.exists()
        and output_file.stat().st_size > 0
    ):

        print("ALREADY EXISTS")
        successful.append(date_str)
        continue


    request = {
        "origin": "ecmwf",
        "level_type": "single_level",
        "variable": VARIABLES,
        "year": str(YEAR),
        "month": f"{MONTH:02d}",
        "day": day_str,
        "time": "00:00",
        "forecast_type": "control_forecast",
        "leadtime_hour": LEAD_TIMES,
        "data_format": "grib",
        "area": AREA,
    }


    try:

        client.retrieve(
            "tigge-forecasts",
            request,
            str(output_file),
        )

        if (
            output_file.exists()
            and output_file.stat().st_size > 0
        ):

            size_mb = (
                output_file.stat().st_size
                / (1024 * 1024)
            )

            print(
                f"SUCCESS → {size_mb:.2f} MB"
            )

            successful.append(date_str)

        else:

            print("FAILED → empty file")

            failed.append(date_str)

            if output_file.exists():
                output_file.unlink()

    except Exception as exc:

        print("FAILED")

        print(
            f"Error type: {type(exc).__name__}"
        )

        print(str(exc))

        failed.append(date_str)

        if output_file.exists():

            try:
                output_file.unlink()
            except Exception:
                pass


    time.sleep(2)


print()
print("=" * 90)
print("FEBRUARY 2019 DIAGNOSTIC SUMMARY")
print("=" * 90)

print(f"Total dates: {days_in_month}")
print(f"Successful:  {len(successful)}")
print(f"Failed:      {len(failed)}")

if days_in_month:

    coverage = (
        100 * len(successful) / days_in_month
    )

    print(
        f"Coverage:    {coverage:.2f}%"
    )


print()
print("=" * 90)
print("SUCCESSFUL DATES")
print("=" * 90)

for item in successful:
    print(item)


print()
print("=" * 90)
print("FAILED DATES")
print("=" * 90)

for item in failed:
    print(item)