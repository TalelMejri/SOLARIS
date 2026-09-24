
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import requests


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]


COORDINATES_FILE = (
    PROJECT_ROOT / "data" / "reference" / "district_coordinates.csv"
)

FEATURES_FILE = (
    PROJECT_ROOT / "data" / "processed" / "features" / "district_features.parquet"
)

RAW_TEST_DIR = (
    PROJECT_ROOT / "data" / "raw" / "nwp" / "availability_test"
)

RAW_TEST_DIR.mkdir(parents=True, exist_ok=True)

# Open-Meteo Single Runs API
SINGLE_RUN_URL = "https://single-runs-api.open-meteo.com/v1/forecast"

# IMPORTANT:
# Use a known historical ECMWF IFS HRES run.
#
# The current Open-Meteo documentation states that ECMWF IFS HRES
# Single Runs are archived from 2024-03-14.
#
# We will test this run first.
TEST_RUN = "2025-01-01T00:00"

# Required Phase 5.2 horizons
REQUIRED_HORIZONS = [1, 6, 12, 24, 72]

# Weather variables for the first API test.
#
# These are variables currently documented by Open-Meteo
# for the ECMWF forecast API.
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
# LOGGING
# ============================================================

def log(message: str) -> None:
    print(f"[INFO] {message}")


def success(message: str) -> None:
    print(f"[PASS] {message}")


def warning(message: str) -> None:
    print(f"[WARN] {message}")


def error(message: str) -> None:
    print(f"[ERROR] {message}")


# ============================================================
# LOAD COORDINATES
# ============================================================

def load_coordinates() -> pd.DataFrame:
    if not COORDINATES_FILE.exists():
        raise FileNotFoundError(
            f"Coordinates file not found:\n{COORDINATES_FILE}"
        )

    df = pd.read_csv(COORDINATES_FILE)

    required = {
        "district_id",
        "district_name",
        "latitude",
        "longitude",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "district_coordinates.csv is missing columns: "
            + ", ".join(sorted(missing))
        )

    df = df.copy()

    df["district_id"] = df["district_id"].astype(str)

    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    if df[["latitude", "longitude"]].isna().any().any():
        raise ValueError(
            "Some district coordinates contain invalid/missing values."
        )

    if df["district_id"].duplicated().any():
        duplicates = df.loc[
            df["district_id"].duplicated(keep=False),
            "district_id"
        ].unique()

        raise ValueError(
            "Duplicate district_id values found: "
            + ", ".join(map(str, duplicates))
        )

    return df


# ============================================================
# LOAD PV FEATURES
# ============================================================

def inspect_target_dataset() -> dict:
    if not FEATURES_FILE.exists():
        raise FileNotFoundError(
            f"Feature dataset not found:\n{FEATURES_FILE}"
        )

    log(f"Reading feature dataset: {FEATURES_FILE}")

    df = pd.read_parquet(
        FEATURES_FILE,
        columns=[
            "district_id",
            "timestamp",
            "p_pvgis_kw_per_kwp",
        ],
    )

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    result = {
        "rows": int(len(df)),
        "district_count": int(df["district_id"].nunique()),
        "start": str(df["timestamp"].min()),
        "end": str(df["timestamp"].max()),
        "target_missing": int(
            df["p_pvgis_kw_per_kwp"].isna().sum()
        ),
    }

    return result


# ============================================================
# COORDINATE VALIDATION
# ============================================================

def validate_coordinates(df: pd.DataFrame) -> None:
    log("Validating district coordinates...")

    # Tunisia approximate bounding box.
    #
    # This is only a sanity check, not a geographic source.
    invalid = df[
        ~df["latitude"].between(30, 38)
        | ~df["longitude"].between(7, 12)
    ]

    if not invalid.empty:
        print(invalid[
            [
                "district_id",
                "district_name",
                "latitude",
                "longitude",
            ]
        ].to_string(index=False))

        raise ValueError(
            "Some district coordinates fall outside the expected "
            "Tunisia sanity-check bounding box."
        )

    if len(df) != 50:
        raise ValueError(
            f"Expected 50 districts, found {len(df)}."
        )

    success("50 district coordinates found.")

    success(
        "All district coordinates passed the Tunisia "
        "sanity check."
    )


# ============================================================
# BUILD TEST REQUEST
# ============================================================

def build_request(lat: float, lon: float) -> dict:
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARIABLES),
        "forecast_hours": 73,
        "timezone": "UTC",
        "run": TEST_RUN,
        "models": "ecmwf_ifs",
    }


# ============================================================
# API TEST
# ============================================================

def test_single_run(
    district: pd.Series,
) -> dict:

    params = build_request(
        lat=float(district["latitude"]),
        lon=float(district["longitude"]),
    )

    log(
        "Testing ECMWF IFS HRES Single Run for "
        f"{district['district_name']} "
        f"({district['latitude']}, {district['longitude']})"
    )

    log(f"Run: {TEST_RUN}")

    response = requests.get(
        SINGLE_RUN_URL,
        params=params,
        timeout=60,
    )

    log(f"HTTP status: {response.status_code}")

    if response.status_code != 200:
        error("Open-Meteo returned a non-200 response.")

        try:
            print(
                json.dumps(
                    response.json(),
                    indent=2,
                    ensure_ascii=False,
                )
            )
        except Exception:
            print(response.text[:2000])

        raise RuntimeError(
            f"Open-Meteo API request failed with HTTP "
            f"{response.status_code}"
        )

    payload = response.json()

    raw_file = RAW_TEST_DIR / (
        f"{district['district_id']}_"
        f"{TEST_RUN.replace(':', '-')}.json"
    )

    raw_file.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    success(f"Raw response saved to: {raw_file}")

    return payload


# ============================================================
# RESPONSE VALIDATION
# ============================================================

def validate_response(
    payload: dict,
) -> pd.DataFrame:

    if "hourly" not in payload:
        raise ValueError(
            "API response does not contain an 'hourly' section."
        )

    hourly = payload["hourly"]

    if "time" not in hourly:
        raise ValueError(
            "API response does not contain hourly timestamps."
        )

    times = pd.to_datetime(
        hourly["time"],
        utc=True,
    )

    df = pd.DataFrame(
        {
            "forecast_valid_time_utc": times,
        }
    )

    for variable in HOURLY_VARIABLES:
        if variable in hourly:
            df[variable] = hourly[variable]
        else:
            warning(
                f"Variable missing from response: {variable}"
            )

    return df


# ============================================================
# HORIZON CHECK
# ============================================================

def check_required_horizons(
    forecast_df: pd.DataFrame,
) -> None:

    if forecast_df.empty:
        raise ValueError("Forecast response contains no rows.")

    issue_time = pd.Timestamp(
        TEST_RUN,
        tz="UTC",
    )

    forecast_df = forecast_df.copy()

    forecast_df["lead_hours"] = (
        (
            forecast_df["forecast_valid_time_utc"]
            - issue_time
        ).dt.total_seconds()
        / 3600
    )

    available = set(
        forecast_df["lead_hours"]
        .round()
        .astype(int)
        .tolist()
    )

    print()
    print("Required horizons:")
    print("------------------")

    for horizon in REQUIRED_HORIZONS:
        if horizon in available:
            success(
                f"H+{horizon}: available"
            )
        else:
            error(
                f"H+{horizon}: NOT available"
            )

    missing = [
        h for h in REQUIRED_HORIZONS
        if h not in available
    ]

    if missing:
        raise ValueError(
            "Required forecast horizons are missing: "
            + ", ".join(map(str, missing))
        )


# ============================================================
# BASIC WEATHER VALIDATION
# ============================================================

def validate_weather_values(
    forecast_df: pd.DataFrame,
) -> None:

    print()
    print("Weather sanity checks:")
    print("----------------------")

    checks_passed = True

    if "temperature_2m" in forecast_df:
        temp = forecast_df["temperature_2m"]

        if temp.isna().all():
            error("temperature_2m contains no usable values.")
            checks_passed = False
        else:
            success(
                "temperature_2m contains usable values."
            )

    if "cloud_cover" in forecast_df:
        cloud = forecast_df["cloud_cover"]

        if cloud.dropna().between(0, 100).all():
            success(
                "cloud_cover is within 0–100%."
            )
        else:
            error(
                "cloud_cover contains values outside 0–100%."
            )
            checks_passed = False

    if "relative_humidity_2m" in forecast_df:
        rh = forecast_df["relative_humidity_2m"]

        if rh.dropna().between(0, 100).all():
            success(
                "relative_humidity_2m is within 0–100%."
            )
        else:
            error(
                "relative_humidity_2m contains invalid values."
            )
            checks_passed = False

    if "wind_speed_10m" in forecast_df:
        wind = forecast_df["wind_speed_10m"]

        if (wind.dropna() >= 0).all():
            success(
                "wind_speed_10m is non-negative."
            )
        else:
            error(
                "wind_speed_10m contains negative values."
            )
            checks_passed = False

    if not checks_passed:
        raise ValueError(
            "One or more weather sanity checks failed."
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print()
    print("=" * 72)
    print("PROSOL FORECAST — PHASE 5.2")
    print("STEP 1 — NWP AVAILABILITY & OVERLAP DIAGNOSTIC")
    print("=" * 72)
    print()

    print(f"Project root:")
    print(f"  {PROJECT_ROOT}")
    print()

    print(f"Test run:")
    print(f"  ECMWF IFS HRES")
    print(f"  {TEST_RUN} UTC")
    print()

    # --------------------------------------------------------
    # 1. Coordinates
    # --------------------------------------------------------

    coordinates = load_coordinates()

    validate_coordinates(coordinates)

    # --------------------------------------------------------
    # 2. Existing target
    # --------------------------------------------------------

    log("Inspecting existing PVGIS feature dataset...")

    target_info = inspect_target_dataset()

    print()
    print("Existing PVGIS target:")
    print("----------------------")

    for key, value in target_info.items():
        print(f"{key}: {value}")

    # --------------------------------------------------------
    # 3. Basic overlap information
    # --------------------------------------------------------

    pv_start = pd.Timestamp(target_info["start"])
    pv_end = pd.Timestamp(target_info["end"])

    nwp_start = pd.Timestamp("2024-03-14")
    nwp_end = pd.Timestamp.now()

    print()
    print("Potential IFS Single Runs archive:")
    print("-----------------------------------")
    print(f"Documented start: {nwp_start.date()}")
    print(f"Current date:     {nwp_end.date()}")

    overlap_start = max(
        pv_start,
        nwp_start,
    )

    overlap_end = min(
        pv_end,
        nwp_end,
    )

    print()
    print("PVGIS / IFS Single Runs overlap:")
    print("---------------------------------")
    print(f"PVGIS start:       {pv_start}")
    print(f"PVGIS end:         {pv_end}")
    print(f"IFS archive start: {nwp_start}")
    print(f"Overlap start:     {overlap_start}")
    print(f"Overlap end:       {overlap_end}")

    if overlap_start <= overlap_end:
        success(
            "A calendar overlap exists between the current "
            "PVGIS target and the documented IFS archive."
        )
    else:
        warning(
            "There is NO calendar overlap between the current "
            "PVGIS 5.3 target and the documented ECMWF IFS "
            "Single Runs archive."
        )

    # --------------------------------------------------------
    # 4. Select first district
    # --------------------------------------------------------

    district = coordinates.iloc[0]

    print()
    print("Test district:")
    print("--------------")
    print(
        district[
            [
                "district_id",
                "district_name",
                "latitude",
                "longitude",
            ]
        ].to_string()
    )

    # --------------------------------------------------------
    # 5. API request
    # --------------------------------------------------------

    payload = test_single_run(district)

    # --------------------------------------------------------
    # 6. Validate response
    # --------------------------------------------------------

    forecast_df = validate_response(payload)

    print()
    print("NWP response:")
    print("-------------")
    print(f"Rows: {len(forecast_df)}")
    print(
        f"Start: {forecast_df['forecast_valid_time_utc'].min()}"
    )
    print(
        f"End:   {forecast_df['forecast_valid_time_utc'].max()}"
    )

    # --------------------------------------------------------
    # 7. Validate required horizons
    # --------------------------------------------------------

    check_required_horizons(forecast_df)

    # --------------------------------------------------------
    # 8. Weather sanity checks
    # --------------------------------------------------------

    validate_weather_values(forecast_df)

    # --------------------------------------------------------
    # 9. Save normalized test response
    # --------------------------------------------------------

    normalized_file = (
        RAW_TEST_DIR / "test_forecast_normalized.csv"
    )

    forecast_df.to_csv(
        normalized_file,
        index=False,
    )

    success(
        f"Normalized test forecast saved to: "
        f"{normalized_file}"
    )

    # --------------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("STEP 1 SUMMARY")
    print("=" * 72)

    print()
    print("Existing target:")
    print(
        f"  {pv_start} → {pv_end}"
    )

    print()
    print("NWP source tested:")
    print("  Open-Meteo")
    print("  ECMWF IFS HRES")
    print("  Single Runs API")
    print(f"  Run: {TEST_RUN} UTC")

    print()
    print("Required horizons:")
    print(
        "  "
        + ", ".join(
            f"H+{h}"
            for h in REQUIRED_HORIZONS
        )
    )

    print()
    print("IMPORTANT:")
    print(
        "The API test confirms that the selected NWP source "
        "can provide the required forecast horizons."
    )

    print(
        "It does NOT yet prove that the complete historical "
        "PV/NWP training period is aligned."
    )

    print()
    print("=" * 72)
    print("STEP 1 COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print()
        error(str(exc))
        print()
        sys.exit(1)

