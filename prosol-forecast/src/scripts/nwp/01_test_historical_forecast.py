from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import requests


# ============================================================
# PROSOL FORECAST — PHASE 5.2
# STEP 2 — HISTORICAL ECMWF FORECAST TEST
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

COORDS_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "district_coordinates.csv"
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
    / "raw"
    / "nwp"
    / "historical_forecast_test"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# TEST CONFIGURATION
# ============================================================

DISTRICT_ID = 1

START_DATE = "2023-06-01"
END_DATE = "2023-06-04"

HORIZONS = [1, 6, 12, 24, 72]

TARGET = "p_pvgis_kw_per_kwp"

API_URL = (
    "https://historical-forecast-api.open-meteo.com/v1/forecast"
)

TIMEOUT = 120


# ============================================================
# WEATHER VARIABLES
# ============================================================

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "showers",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
]


# ============================================================
# HEADER
# ============================================================

print()
print("=" * 72)
print("PROSOL FORECAST — PHASE 5.2")
print("STEP 2 — HISTORICAL ECMWF FORECAST TEST")
print("=" * 72)

print()
print("Project root:")
print(f"  {PROJECT_ROOT}")

print()
print("Test district:")
print(f"  {DISTRICT_ID}")

print()
print("Period:")
print(f"  {START_DATE} → {END_DATE}")

print()
print("Model:")
print("  ECMWF IFS HRES")


# ============================================================
# CHECK FILES
# ============================================================

if not COORDS_FILE.exists():
    print(f"[ERROR] Missing: {COORDS_FILE}")
    sys.exit(1)

if not FEATURES_FILE.exists():
    print(f"[ERROR] Missing: {FEATURES_FILE}")
    sys.exit(1)


# ============================================================
# LOAD COORDINATES
# ============================================================

print()
print("[INFO] Loading district coordinates...")

coords = pd.read_csv(COORDS_FILE)

required_coord_columns = [
    "district_id",
    "district_name",
    "latitude",
    "longitude",
]

missing = [
    c for c in required_coord_columns
    if c not in coords.columns
]

if missing:
    print(
        "[ERROR] Missing coordinate columns:",
        missing,
    )
    sys.exit(1)

district = coords[
    coords["district_id"].astype(str)
    == str(DISTRICT_ID)
]

if district.empty:
    print(
        f"[ERROR] District {DISTRICT_ID} not found."
    )
    sys.exit(1)

district = district.iloc[0]

district_name = district["district_name"]
latitude = float(district["latitude"])
longitude = float(district["longitude"])

print("[PASS] District found.")

print(f"  Name:      {district_name}")
print(f"  Latitude:  {latitude}")
print(f"  Longitude: {longitude}")


# ============================================================
# LOAD PVGIS TARGET
# ============================================================

print()
print("[INFO] Loading PVGIS target...")

df_target = pd.read_parquet(
    FEATURES_FILE,
    columns=[
        "district_id",
        "timestamp",
        TARGET,
    ],
)

df_target = df_target[
    df_target["district_id"].astype(str)
    == str(DISTRICT_ID)
].copy()

df_target["timestamp"] = pd.to_datetime(
    df_target["timestamp"],
    errors="coerce",
)

df_target = df_target.dropna(
    subset=["timestamp", TARGET]
)

# Existing project timestamps are local Africa/Tunis
# and are stored as naive timestamps.
df_target = df_target[
    (df_target["timestamp"] >= START_DATE)
    &
    (
        df_target["timestamp"]
        < pd.Timestamp(END_DATE)
        + pd.Timedelta(days=1)
    )
].copy()

print(
    f"[PASS] PVGIS target rows: "
    f"{len(df_target):,}"
)

print(
    f"[PASS] Target start: "
    f"{df_target['timestamp'].min()}"
)

print(
    f"[PASS] Target end: "
    f"{df_target['timestamp'].max()}"
)


# ============================================================
# REQUEST HISTORICAL FORECAST
# ============================================================

print()
print("[INFO] Requesting ECMWF IFS HRES historical forecast...")

params = {
    "latitude": latitude,
    "longitude": longitude,

    "hourly": ",".join(
        HOURLY_VARIABLES
    ),

    "start_date": START_DATE,
    "end_date": END_DATE,

    "models": "ecmwf_ifs",

    "timezone": "UTC",
}

print()
print("Request:")
print(f"  URL: {API_URL}")
print(f"  Model: {params['models']}")
print(f"  Start: {START_DATE}")
print(f"  End:   {END_DATE}")
print("  Timezone: UTC")


try:

    response = requests.get(
        API_URL,
        params=params,
        timeout=TIMEOUT,
    )

except requests.RequestException as exc:

    print()
    print("[ERROR] HTTP request failed:")
    print(exc)
    sys.exit(1)


print()
print(
    f"[INFO] HTTP status: "
    f"{response.status_code}"
)

if not response.ok:

    print()
    print("[ERROR] API request failed.")
    print(response.text[:4000])
    sys.exit(1)


print("[PASS] API request successful.")


# ============================================================
# SAVE RAW JSON
# ============================================================

raw_file = (
    OUTPUT_DIR
    / "tunis_ville_2023-06-01_2023-06-04.json"
)

raw_file.write_text(
    response.text,
    encoding="utf-8",
)

print()
print(
    f"[PASS] Raw response saved:"
)
print(f"  {raw_file}")


data = response.json()


# ============================================================
# API METADATA
# ============================================================

print()
print("API metadata:")
print(f"  latitude:  {data.get('latitude')}")
print(f"  longitude: {data.get('longitude')}")
print(f"  timezone:  {data.get('timezone')}")
print(f"  elevation: {data.get('elevation')}")


# ============================================================
# PARSE HOURLY DATA
# ============================================================

if "hourly" not in data:
    print(
        "[ERROR] Response does not contain 'hourly'."
    )
    print(json.dumps(data, indent=2)[:5000])
    sys.exit(1)

hourly = data["hourly"]

if "time" not in hourly:
    print(
        "[ERROR] Hourly response does not contain time."
    )
    sys.exit(1)


weather = pd.DataFrame(hourly)

weather["forecast_valid_time_utc"] = pd.to_datetime(
    weather["time"],
    utc=True,
)

weather = weather.drop(
    columns=["time"]
)

weather["district_id"] = DISTRICT_ID
weather["district_name"] = district_name
weather["latitude"] = latitude
weather["longitude"] = longitude
weather["model"] = "ecmwf_ifs"

# This Historical Forecast endpoint gives a continuous
# stitched series. It does NOT expose one exact issue time
# for every returned row.
weather["forecast_source"] = (
    "open-meteo_historical_forecast"
)


# ============================================================
# BASIC WEATHER VALIDATION
# ============================================================

print()
print("Weather response:")
print(
    f"  rows: "
    f"{len(weather):,}"
)

print(
    f"  start: "
    f"{weather['forecast_valid_time_utc'].min()}"
)

print(
    f"  end: "
    f"{weather['forecast_valid_time_utc'].max()}"
)

expected_hours = (
    int(
        (
            weather["forecast_valid_time_utc"].max()
            -
            weather["forecast_valid_time_utc"].min()
        ).total_seconds()
        / 3600
    )
    + 1
)

print(
    f"  expected continuous hours: "
    f"{expected_hours}"
)


# Check duplicate timestamps
duplicate_count = weather[
    "forecast_valid_time_utc"
].duplicated().sum()

if duplicate_count == 0:
    print(
        "[PASS] No duplicate forecast timestamps."
    )
else:
    print(
        f"[ERROR] Duplicate timestamps: "
        f"{duplicate_count}"
    )


# Check continuity
time_diff = (
    weather["forecast_valid_time_utc"]
    .sort_values()
    .diff()
    .dropna()
)

missing_hour_gaps = (
    time_diff
    != pd.Timedelta(hours=1)
).sum()

if missing_hour_gaps == 0:
    print(
        "[PASS] Forecast timestamps are hourly "
        "and continuous."
    )
else:
    print(
        f"[WARN] Non-hourly gaps found: "
        f"{missing_hour_gaps}"
    )


# ============================================================
# WEATHER SANITY
# ============================================================

checks = []

if "temperature_2m" in weather:
    checks.append(
        (
            "temperature_2m",
            weather["temperature_2m"].notna().any(),
        )
    )

if "cloud_cover" in weather:
    checks.append(
        (
            "cloud_cover 0–100",
            weather["cloud_cover"].between(
                0, 100
            ).all(),
        )
    )

if "relative_humidity_2m" in weather:
    checks.append(
        (
            "relative_humidity_2m 0–100",
            weather[
                "relative_humidity_2m"
            ].between(0, 100).all(),
        )
    )

if "wind_speed_10m" in weather:
    checks.append(
        (
            "wind_speed_10m >= 0",
            (
                weather["wind_speed_10m"]
                >= 0
            ).all(),
        )
    )

print()
print("Weather sanity checks:")

for name, passed in checks:

    if passed:
        print(f"[PASS] {name}")
    else:
        print(f"[ERROR] {name}")


# ============================================================
# SAVE NORMALIZED WEATHER
# ============================================================

weather_file = (
    OUTPUT_DIR
    / "tunis_ville_historical_forecast.csv"
)

weather.to_csv(
    weather_file,
    index=False,
)

print()
print(
    "[PASS] Normalized weather saved:"
)
print(f"  {weather_file}")


# ============================================================
# CREATE VALID-TIME ALIGNMENT TEST
# ============================================================

print()
print("=" * 72)
print("HORIZON ALIGNMENT TEST")
print("=" * 72)

# Convert forecast valid time from UTC to
# Africa/Tunis for comparison with the project's
# existing naive PVGIS timestamps.
#
# We only use this conversion for timestamp matching.
# We do NOT alter the weather values.

weather["valid_time_local"] = (
    weather["forecast_valid_time_utc"]
    .dt.tz_convert(
        "Africa/Tunis"
    )
    .dt.tz_localize(None)
)

# Create target lookup
target_lookup = df_target[
    [
        "timestamp",
        TARGET,
    ]
].rename(
    columns={
        "timestamp": "valid_time_local"
    }
)

# Merge weather with target by valid time
merged = weather.merge(
    target_lookup,
    on="valid_time_local",
    how="inner",
)

print()
print(
    f"Weather rows: "
    f"{len(weather):,}"
)

print(
    f"Matched PVGIS rows: "
    f"{len(merged):,}"
)

if len(merged) > 0:

    print(
        "[PASS] Historical forecast period "
        "overlaps PVGIS target."
    )

else:

    print(
        "[ERROR] No timestamp overlap "
        "with PVGIS target."
    )


# ============================================================
# HORIZON AVAILABILITY
# ============================================================

print()
print("Required horizons:")

for h in HORIZONS:

    # We only verify that the target period contains
    # enough consecutive timestamps for an h-hour
    # valid-time relationship.
    required_rows = h + 1

    available = (
        len(weather)
        >= required_rows
    )

    if available:
        print(
            f"[PASS] H+{h}: "
            f"enough hourly data available"
        )
    else:
        print(
            f"[ERROR] H+{h}: "
            f"insufficient hourly data"
        )


# ============================================================
# SAVE MATCHED TEST
# ============================================================

matched_file = (
    OUTPUT_DIR
    / "tunis_ville_forecast_pvgis_overlap.csv"
)

merged.to_csv(
    matched_file,
    index=False,
)

print()
print(
    f"[PASS] Matched data saved:"
)
print(f"  {matched_file}")


# ============================================================
# FINAL SUMMARY
# ============================================================

print()
print("=" * 72)
print("STEP 2 SUMMARY")
print("=" * 72)

print()
print("District:")
print(f"  {district_name}")

print()
print("Forecast model:")
print("  ECMWF IFS HRES")

print()
print("Historical Forecast API:")
print("  Open-Meteo")

print()
print("Period:")
print(
    f"  {START_DATE} → {END_DATE}"
)

print()
print("PVGIS target:")
print(
    f"  {df_target['timestamp'].min()} "
    f"→ "
    f"{df_target['timestamp'].max()}"
)

print()
print(
    "IMPORTANT:"
)
print(
    "The Historical Forecast API provides a "
    "stitched continuous forecast series."
)
print(
    "It does not preserve the complete individual "
    "forecast run structure like the Single Runs API."
)

print()
print("=" * 72)
print("STEP 2 COMPLETE")
print("=" * 72)