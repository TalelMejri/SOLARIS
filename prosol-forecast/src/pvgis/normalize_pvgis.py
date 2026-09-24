from pathlib import Path
import json
import re
import pandas as pd
import numpy as np

# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "pvgis"

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "pvgis_hourly"

ALL_OUTPUT_FILE = OUTPUT_DIR / "pvgis_hourly_all.csv"

MANIFEST_FILE = RAW_DIR / "download_manifest.csv"


# ============================================================
# EXPECTED PVGIS CONFIGURATION
# ============================================================

EXPECTED_PEAKPOWER_KWP = 1.0
EXPECTED_PV_TECHNOLOGY = "crystSi"
EXPECTED_MOUNTING_PLACE = "building"
EXPECTED_LOSS_PERCENT = 14


# ============================================================
# COLUMN MAPPING
# ============================================================

PVGIS_COLUMN_MAPPING = {
    "G(i)": "ghi_w_m2",
    "Gb(i)": "beam_w_m2",
    "Gd(i)": "diffuse_w_m2",
    "Gr(i)": "reflected_w_m2",
    "H_sun": "solar_elevation_deg",
    "T2m": "temperature_2m_c",
    "WS10m": "wind_speed_10m_ms",
}


# ============================================================
# HELPERS
# ============================================================


def safe_float(value):
    """
    Convert a value to float.

    Returns NaN if conversion fails.
    """

    if value is None:
        return np.nan

    try:
        return float(value)

    except (ValueError, TypeError):
        return np.nan


def parse_pvgis_timestamp(value):
    """
    Parse PVGIS timestamp.

    Typical PVGIS format:

        YYYYMMDD:HHMM

    Example:

        20230101:0010

    Some responses may contain variations, so we support
    several formats.
    """

    if value is None:
        return pd.NaT

    value = str(value).strip()

    # Standard PVGIS format
    if re.fullmatch(r"\d{8}:\d{4}", value):

        return pd.to_datetime(value, format="%Y%m%d:%H%M", errors="coerce")

    # YYYYMMDDHHMM
    if re.fullmatch(r"\d{12}", value):

        return pd.to_datetime(value, format="%Y%m%d%H%M", errors="coerce")

    # Generic fallback
    return pd.to_datetime(value, errors="coerce")


def validate_raw_payload(payload, filename):
    """
    Validate the raw JSON structure created in Phase 2.2.
    """

    if not isinstance(payload, dict):

        raise ValueError(f"{filename}: JSON root is not an object.")

    if "pvgis_response" not in payload:

        raise ValueError(f"{filename}: missing 'pvgis_response'.")

    response = payload["pvgis_response"]

    if not isinstance(response, dict):

        raise ValueError(f"{filename}: 'pvgis_response' is not an object.")

    if "outputs" not in response:

        raise ValueError(f"{filename}: missing 'outputs'.")

    outputs = response["outputs"]

    if "hourly" not in outputs:

        raise ValueError(f"{filename}: missing 'outputs.hourly'.")

    hourly = outputs["hourly"]

    if not isinstance(hourly, list):

        raise ValueError(f"{filename}: 'hourly' is not a list.")

    if len(hourly) == 0:

        raise ValueError(f"{filename}: zero hourly records.")

    return hourly


def validate_metadata(metadata, filename):
    """
    Validate that all Phase 2.2 files use the expected
    normalized PVGIS configuration.
    """

    peakpower = safe_float(metadata.get("peakpower_kwp"))

    if peakpower != EXPECTED_PEAKPOWER_KWP:

        raise ValueError(
            f"{filename}: unexpected peakpower "
            f"{peakpower}. Expected "
            f"{EXPECTED_PEAKPOWER_KWP}."
        )

    technology = metadata.get("pvtechchoice")

    if technology != EXPECTED_PV_TECHNOLOGY:

        raise ValueError(f"{filename}: unexpected PV technology " f"{technology}.")

    mounting = metadata.get("mountingplace")

    if mounting != EXPECTED_MOUNTING_PLACE:

        raise ValueError(f"{filename}: unexpected mounting place " f"{mounting}.")

    loss = safe_float(metadata.get("loss_percent"))

    if loss != EXPECTED_LOSS_PERCENT:

        raise ValueError(
            f"{filename}: unexpected system loss "
            f"{loss}%. Expected "
            f"{EXPECTED_LOSS_PERCENT}%."
        )


def normalize_hourly_records(hourly, metadata):
    rows = []

    for record in hourly:
        timestamp = parse_pvgis_timestamp(record.get("time"))

        p_w = safe_float(record.get("P"))
        p_kw_per_kwp = (
            p_w / 1000.0 / EXPECTED_PEAKPOWER_KWP if pd.notna(p_w) else np.nan
        )

        beam = safe_float(record.get("Gb(i)"))
        diffuse = safe_float(record.get("Gd(i)"))
        reflected = safe_float(record.get("Gr(i)"))

        # Reconstruct total on-plane GHI
        ghi_total = (
            (beam if pd.notna(beam) else 0.0)
            + (diffuse if pd.notna(diffuse) else 0.0)
            + (reflected if pd.notna(reflected) else 0.0)
        )
        # If all three are missing, leave GHI as NaN
        if pd.isna(beam) and pd.isna(diffuse) and pd.isna(reflected):
            ghi_total = np.nan

        row = {
            "district_id": int(metadata["district_id"]),
            "district_name": str(metadata["district_name"]),
            "region_id": int(metadata["region_id"]),
            "region_name": str(metadata["region_name"]),
            "latitude": safe_float(metadata["latitude"]),
            "longitude": safe_float(metadata["longitude"]),
            "timestamp": timestamp,
            "p_pvgis_kw_per_kwp": p_kw_per_kwp,
            "ghi_w_m2": ghi_total,  # <-- reconstructed
            "beam_w_m2": beam,
            "diffuse_w_m2": diffuse,
            "reflected_w_m2": reflected,
            "solar_elevation_deg": safe_float(record.get("H_sun")),
            "temperature_2m_c": safe_float(record.get("T2m")),
            "wind_speed_10m_ms": safe_float(record.get("WS10m")),
        }

        rows.append(row)

    return pd.DataFrame(rows)


def clean_dataframe(df):
    """
    Apply deterministic cleaning rules.

    IMPORTANT:
    We do not synthesize missing values.
    """

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    df = df.sort_values(
        [
            "district_id",
            "timestamp",
        ]
    ).reset_index(drop=True)

    # --------------------------------------------------------
    # Remove completely invalid timestamps
    # --------------------------------------------------------

    before = len(df)

    df = df[df["timestamp"].notna()].copy()

    removed = before - len(df)

    if removed > 0:

        print(f"    Removed {removed} rows " f"with invalid timestamps.")

    # --------------------------------------------------------
    # Remove duplicate district/timestamp records
    # --------------------------------------------------------

    duplicate_count = df.duplicated(
        subset=[
            "district_id",
            "timestamp",
        ]
    ).sum()

    if duplicate_count > 0:

        print(f"    Removing {duplicate_count} " f"duplicate district/timestamp rows.")

        df = df.drop_duplicates(
            subset=[
                "district_id",
                "timestamp",
            ],
            keep="first",
        )

    # --------------------------------------------------------
    # Physical sanity checks
    # --------------------------------------------------------

    # PV power cannot be negative
    negative_pv = df["p_pvgis_kw_per_kwp"] < 0

    if negative_pv.any():

        count = int(negative_pv.sum())

        print(f"    WARNING: {count} negative PV values " f"converted to NaN.")

        df.loc[negative_pv, "p_pvgis_kw_per_kwp"] = np.nan

    # Irradiance cannot be negative
    radiation_columns = [
        "ghi_w_m2",
        "beam_w_m2",
        "diffuse_w_m2",
        "reflected_w_m2",
    ]

    for column in radiation_columns:

        negative = df[column] < 0

        if negative.any():

            count = int(negative.sum())

            print(
                f"    WARNING: {count} negative " f"{column} values converted to NaN."
            )

            df.loc[negative, column] = np.nan

    # --------------------------------------------------------
    # Numeric rounding
    # --------------------------------------------------------

    df["p_pvgis_kw_per_kwp"] = df["p_pvgis_kw_per_kwp"].round(6)

    for column in radiation_columns:

        df[column] = df[column].round(3)

    df["temperature_2m_c"] = df["temperature_2m_c"].round(3)

    df["wind_speed_10m_ms"] = df["wind_speed_10m_ms"].round(3)

    df["solar_elevation_deg"] = df["solar_elevation_deg"].round(3)

    return df


def validate_normalized_dataframe(df, district_id, district_name):
    """
    Validate one normalized district dataset.
    """

    if len(df) == 0:

        raise ValueError(f"{district_name}: normalized dataset is empty.")

    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------

    if df["timestamp"].isna().any():

        raise ValueError(f"{district_name}: NaN timestamps remain.")

    # --------------------------------------------------------
    # District identity
    # --------------------------------------------------------

    if not (df["district_id"] == district_id).all():

        raise ValueError(f"{district_name}: district ID inconsistency.")

    # --------------------------------------------------------
    # PV range
    # --------------------------------------------------------
    #
    # For a 1 kWp system:
    #
    # normalized instantaneous power should normally
    # be around 0 to 1 kW/kWp.
    #
    # We don't hard-fail values slightly above 1 because
    # real PVGIS calculations can have modeling effects.
    #

    pv = df["p_pvgis_kw_per_kwp"].dropna()

    if len(pv) > 0:

        if (pv < 0).any():

            raise ValueError(f"{district_name}: negative normalized PV.")

    # --------------------------------------------------------
    # Irradiance
    # --------------------------------------------------------

    for column in [
        "ghi_w_m2",
        "beam_w_m2",
        "diffuse_w_m2",
        "reflected_w_m2",
    ]:

        values = df[column].dropna()

        if len(values) > 0:

            if (values < 0).any():

                raise ValueError(f"{district_name}: negative " f"{column} remains.")

    # --------------------------------------------------------
    # Duplicate timestamp
    # --------------------------------------------------------

    duplicates = df.duplicated(
        subset=[
            "district_id",
            "timestamp",
        ]
    ).sum()

    if duplicates > 0:

        raise ValueError(f"{district_name}: " f"{duplicates} duplicate timestamps.")


# ============================================================
# PROCESS ONE FILE
# ============================================================


def process_file(json_file):

    print(f"\nProcessing: " f"{json_file.name}")

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    with open(json_file, "r", encoding="utf-8") as file:

        payload = json.load(file)

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    hourly = validate_raw_payload(payload, json_file.name)

    metadata = payload["request_metadata"]

    validate_metadata(metadata, json_file.name)

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    df = normalize_hourly_records(hourly, metadata)

    # --------------------------------------------------------
    # Clean
    # --------------------------------------------------------

    df = clean_dataframe(df)

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    district_id = int(metadata["district_id"])

    district_name = str(metadata["district_name"])

    validate_normalized_dataframe(df, district_id, district_name)

    return df


# ============================================================
# MAIN
# ============================================================


def main():

    print("=" * 70)
    print("PHASE 2.3 - NORMALIZE PVGIS HOURLY DATA")
    print("=" * 70)

    # --------------------------------------------------------
    # Check raw directory
    # --------------------------------------------------------

    if not RAW_DIR.exists():

        raise FileNotFoundError(
            f"PVGIS raw directory does not exist:\n"
            f"{RAW_DIR}\n\n"
            "Run Phase 2.2 first."
        )

    # --------------------------------------------------------
    # Find JSON files
    # --------------------------------------------------------

    json_files = sorted(RAW_DIR.glob("district_*.json"))

    print(f"\nFound {len(json_files)} " f"PVGIS JSON files.")

    if len(json_files) != 50:

        raise ValueError(
            f"Expected 50 PVGIS files, "
            f"found {len(json_files)}.\n\n"
            "Phase 2.2 must successfully download "
            "all 50 districts before normalization."
        )

    # --------------------------------------------------------
    # Create output directory
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------
    # Process
    # --------------------------------------------------------

    all_dataframes = []

    validation_records = []

    for index, json_file in enumerate(json_files, start=1):

        print(f"\n[{index}/50]", end=" ")

        try:

            df = process_file(json_file)

            # ------------------------------------------------
            # Save district CSV
            # ------------------------------------------------

            district_id = int(df["district_id"].iloc[0])

            district_name = str(df["district_name"].iloc[0])

            output_file = OUTPUT_DIR / f"district_{district_id:02d}.csv"

            df.to_csv(output_file, index=False, encoding="utf-8")

            all_dataframes.append(df)

            # ------------------------------------------------
            # Statistics
            # ------------------------------------------------

            pv_valid = int(df["p_pvgis_kw_per_kwp"].notna().sum())

            ghi_valid = int(df["ghi_w_m2"].notna().sum())

            validation_records.append(
                {
                    "district_id": district_id,
                    "district_name": district_name,
                    "rows": len(df),
                    "pv_valid_rows": pv_valid,
                    "ghi_valid_rows": ghi_valid,
                    "first_timestamp": (df["timestamp"].min()),
                    "last_timestamp": (df["timestamp"].max()),
                    "status": "OK",
                }
            )

            print(f"OK - {len(df):,} hourly rows")

        except Exception as exc:

            print(f"ERROR - {exc}")

            validation_records.append(
                {
                    "district_id": np.nan,
                    "district_name": json_file.name,
                    "rows": 0,
                    "pv_valid_rows": 0,
                    "ghi_valid_rows": 0,
                    "first_timestamp": None,
                    "last_timestamp": None,
                    "status": f"ERROR: {exc}",
                }
            )

    # --------------------------------------------------------
    # Check successful districts
    # --------------------------------------------------------

    successful = [record for record in validation_records if record["status"] == "OK"]

    if len(successful) != 50:

        print("\n" + "=" * 70)

        print("NORMALIZATION FAILED")

        print("=" * 70)

        failed = [record for record in validation_records if record["status"] != "OK"]

        for record in failed:

            print(f"\n{record['district_name']}: " f"{record['status']}")

        raise RuntimeError(
            f"Only {len(successful)}/50 districts " "were successfully normalized."
        )

    # --------------------------------------------------------
    # Consolidated dataset
    # --------------------------------------------------------

    print("\nCreating consolidated dataset...")

    all_data = pd.concat(all_dataframes, ignore_index=True)

    all_data = all_data.sort_values(
        [
            "district_id",
            "timestamp",
        ]
    ).reset_index(drop=True)

    # --------------------------------------------------------
    # Final global validation
    # --------------------------------------------------------

    if (
        all_data[
            [
                "district_id",
                "timestamp",
            ]
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate district/timestamp " "records detected in consolidated dataset."
        )

    # --------------------------------------------------------
    # Save consolidated CSV
    # --------------------------------------------------------

    all_data.to_csv(ALL_OUTPUT_FILE, index=False, encoding="utf-8")

    # --------------------------------------------------------
    # Validation report
    # --------------------------------------------------------

    validation_df = pd.DataFrame(validation_records)

    validation_file = OUTPUT_DIR / "normalization_validation.csv"

    validation_df.to_csv(validation_file, index=False, encoding="utf-8")

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print("\n" + "=" * 70)

    print("PHASE 2.3 COMPLETE")

    print("=" * 70)

    print(f"\nDistricts processed : " f"{len(successful)}/50")

    print(f"Total hourly rows   : " f"{len(all_data):,}")

    print(f"First timestamp     : " f"{all_data['timestamp'].min()}")

    print(f"Last timestamp      : " f"{all_data['timestamp'].max()}")

    print("\nOutput directory:")

    print(f"  {OUTPUT_DIR}")

    print("\nConsolidated dataset:")

    print(f"  {ALL_OUTPUT_FILE}")

    print("\nValidation report:")

    print(f"  {validation_file}")

    # --------------------------------------------------------
    # Dataset statistics
    # --------------------------------------------------------

    print("\nPV normalized statistics:")

    pv = all_data["p_pvgis_kw_per_kwp"].dropna()

    print(f"  Minimum : {pv.min():.6f}")

    print(f"  Maximum : {pv.max():.6f}")

    print(f"  Mean    : {pv.mean():.6f}")

    print(f"  Median  : {pv.median():.6f}")

    print("\nMissing-value summary:")

    for column in all_data.columns:

        missing_count = int(all_data[column].isna().sum())

        if missing_count > 0:

            percentage = missing_count / len(all_data) * 100

            print(f"  {column}: " f"{missing_count:,} " f"({percentage:.2f}%)")

    print("\nPhase 2.3 successfully completed.")


if __name__ == "__main__":
    main()
