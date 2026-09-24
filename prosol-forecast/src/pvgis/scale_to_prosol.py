from pathlib import Path

import pandas as pd
import numpy as np


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PVGIS_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "pvgis_hourly"
    / "pvgis_hourly_all.csv"
)

PROSOL_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "prosol_district_capacity.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "prosol_pvgis"
)

OUTPUT_FILE = OUTPUT_DIR / "district_hourly_production.csv"
SUMMARY_FILE = OUTPUT_DIR / "district_production_summary.csv"
VALIDATION_FILE = OUTPUT_DIR / "scaling_validation.csv"


# ============================================================
# EXPECTED DATA
# ============================================================

EXPECTED_DISTRICTS = 50


# ============================================================
# LOAD PVGIS
# ============================================================

def load_pvgis():
    if not PVGIS_FILE.exists():
        raise FileNotFoundError(
            f"PVGIS normalized dataset not found:\n{PVGIS_FILE}\n\n"
            "Run Phase 2.3 first."
        )

    df = pd.read_csv(PVGIS_FILE)

    required_columns = [
        "district_id",
        "district_name",
        "region_id",
        "region_name",
        "latitude",
        "longitude",
        "timestamp",
        "p_pvgis_kw_per_kwp",
        "ghi_w_m2",
        "beam_w_m2",
        "diffuse_w_m2",
        "reflected_w_m2",
        "solar_elevation_deg",
        "temperature_2m_c",
        "wind_speed_10m_ms",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"PVGIS dataset is missing columns: {missing}"
        )

    df["district_id"] = pd.to_numeric(
        df["district_id"],
        errors="raise"
    ).astype(int)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="raise"
    )

    return df


# ============================================================
# LOAD PROSOL CAPACITY
# ============================================================

def load_prosol_capacity():
    if not PROSOL_FILE.exists():
        raise FileNotFoundError(
            f"Prosol district capacity file not found:\n{PROSOL_FILE}\n\n"
            "Run Phase 1 first."
        )

    df = pd.read_csv(PROSOL_FILE)

    required_columns = [
        "district_id",
        "district_name",
        "region_name",
        "capacity_mw",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Prosol capacity dataset is missing columns: {missing}"
        )

    df["district_id"] = pd.to_numeric(
        df["district_id"],
        errors="raise"
    ).astype(int)

    df["capacity_mw"] = pd.to_numeric(
        df["capacity_mw"],
        errors="raise"
    )

    return df


# ============================================================
# VALIDATE DISTRICT COVERAGE
# ============================================================

def validate_districts(pvgis, prosol):

    pvgis_districts = set(
        pvgis["district_id"].unique()
    )

    prosol_districts = set(
        prosol["district_id"].unique()
    )

    print("\nDistrict coverage:")
    print(f"  PVGIS districts  : {len(pvgis_districts)}")
    print(f"  Prosol districts : {len(prosol_districts)}")

    if len(pvgis_districts) != EXPECTED_DISTRICTS:
        raise ValueError(
            f"Expected {EXPECTED_DISTRICTS} PVGIS districts, "
            f"found {len(pvgis_districts)}."
        )

    if len(prosol_districts) != EXPECTED_DISTRICTS:
        raise ValueError(
            f"Expected {EXPECTED_DISTRICTS} Prosol districts, "
            f"found {len(prosol_districts)}."
        )

    missing_from_prosol = (
        pvgis_districts - prosol_districts
    )

    missing_from_pvgis = (
        prosol_districts - pvgis_districts
    )

    if missing_from_prosol:
        raise ValueError(
            "PVGIS districts missing from Prosol:\n"
            f"{sorted(missing_from_prosol)}"
        )

    if missing_from_pvgis:
        raise ValueError(
            "Prosol districts missing from PVGIS:\n"
            f"{sorted(missing_from_pvgis)}"
        )

    duplicate_capacity = prosol[
        prosol["district_id"].duplicated(keep=False)
    ]

    if not duplicate_capacity.empty:
        raise ValueError(
            "Duplicate Prosol district IDs detected:\n"
            f"{duplicate_capacity}"
        )


# ============================================================
# MERGE
# ============================================================

def merge_datasets(pvgis, prosol):

    capacity = prosol[
        [
            "district_id",
            "district_name",
            "region_name",
            "capacity_mw",
        ]
    ].copy()

    capacity = capacity.rename(
        columns={
            "district_name": "prosol_district_name",
            "region_name": "prosol_region_name",
        }
    )

    merged = pvgis.merge(
        capacity,
        on="district_id",
        how="left",
        validate="many_to_one",
    )

    missing_capacity = merged[
        merged["capacity_mw"].isna()
    ]

    if not missing_capacity.empty:
        districts = (
            missing_capacity["district_id"]
            .drop_duplicates()
            .tolist()
        )

        raise ValueError(
            "Missing Prosol capacity for districts:\n"
            f"{districts}"
        )

    return merged


# ============================================================
# SCALE PVGIS
# ============================================================

def calculate_production(df):

    # --------------------------------------------------------
    # PVGIS normalized power:
    #
    # p_pvgis_kw_per_kwp
    #
    # Prosol:
    #
    # capacity_mw
    #
    # Therefore:
    #
    # kW/kWp × MWp = MW
    # --------------------------------------------------------

    df["estimated_power_mw"] = (
        df["p_pvgis_kw_per_kwp"]
        * df["capacity_mw"]
    )

    # Preserve the original PVGIS normalized signal.
    # Do NOT replace it.
    #
    # The estimated power is the district-level scaling.

    df["capacity_source"] = (
        "PROSOL_DISTRICT_CAPACITY_JULY_2026"
    )

    df["pv_reference"] = (
        "PVGIS_1KWP"
    )

    return df


# ============================================================
# VALIDATE PRODUCTION
# ============================================================

def validate_production(df):

    errors = []

    # --------------------------------------------------------
    # 1. District count
    # --------------------------------------------------------

    district_count = df["district_id"].nunique()

    if district_count != EXPECTED_DISTRICTS:
        errors.append(
            f"Expected {EXPECTED_DISTRICTS} districts, "
            f"found {district_count}"
        )

    # --------------------------------------------------------
    # 2. Capacity
    # --------------------------------------------------------

    if df["capacity_mw"].isna().any():
        errors.append(
            "Missing district capacity detected."
        )

    if (df["capacity_mw"] < 0).any():
        errors.append(
            "Negative district capacity detected."
        )

    # --------------------------------------------------------
    # 3. PVGIS normalized production
    # --------------------------------------------------------

    negative_pv = (
        df["p_pvgis_kw_per_kwp"].dropna() < 0
    ).any()

    if negative_pv:
        errors.append(
            "Negative normalized PVGIS production detected."
        )

    # --------------------------------------------------------
    # 4. Estimated production
    # --------------------------------------------------------

    negative_power = (
        df["estimated_power_mw"].dropna() < 0
    ).any()

    if negative_power:
        errors.append(
            "Negative estimated district production detected."
        )

    # --------------------------------------------------------
    # 5. Duplicate records
    # --------------------------------------------------------

    duplicates = df.duplicated(
        subset=[
            "district_id",
            "timestamp",
        ]
    ).sum()

    if duplicates > 0:
        errors.append(
            f"{duplicates} duplicate district/timestamp records."
        )

    if errors:
        raise ValueError(
            "\n".join(
                f"- {error}"
                for error in errors
            )
        )


# ============================================================
# DISTRICT SUMMARY
# ============================================================

def build_summary(df):

    summary_rows = []

    for district_id, group in df.groupby(
        "district_id"
    ):

        production = group[
            "estimated_power_mw"
        ].dropna()

        pv_profile = group[
            "p_pvgis_kw_per_kwp"
        ].dropna()

        capacity = float(
            group["capacity_mw"].iloc[0]
        )

        summary_rows.append({

            "district_id": district_id,

            "district_name": group[
                "district_name"
            ].iloc[0],

            "region_name": group[
                "region_name"
            ].iloc[0],

            "capacity_mw": capacity,

            "hours": len(group),

            "valid_pv_hours": len(
                production
            ),

            "first_timestamp": group[
                "timestamp"
            ].min(),

            "last_timestamp": group[
                "timestamp"
            ].max(),

            "mean_pvgis_kw_per_kwp": (
                pv_profile.mean()
                if len(pv_profile)
                else np.nan
            ),

            "max_pvgis_kw_per_kwp": (
                pv_profile.max()
                if len(pv_profile)
                else np.nan
            ),

            "mean_estimated_power_mw": (
                production.mean()
                if len(production)
                else np.nan
            ),

            "max_estimated_power_mw": (
                production.max()
                if len(production)
                else np.nan
            ),

            "capacity_factor_proxy": (
                production.mean() / capacity
                if len(production) and capacity > 0
                else np.nan
            ),
        })

    return pd.DataFrame(summary_rows)


# ============================================================
# VALIDATION REPORT
# ============================================================

def build_validation_report(
    pvgis,
    prosol,
    merged,
):

    rows = []

    for district_id in sorted(
        prosol["district_id"].unique()
    ):

        pv = pvgis[
            pvgis["district_id"]
            == district_id
        ]

        ps = prosol[
            prosol["district_id"]
            == district_id
        ]

        merged_district = merged[
            merged["district_id"]
            == district_id
        ]

        rows.append({

            "district_id": district_id,

            "district_name": ps[
                "district_name"
            ].iloc[0],

            "prosol_capacity_mw": ps[
                "capacity_mw"
            ].iloc[0],

            "pvgis_rows": len(pv),

            "scaled_rows": len(
                merged_district
            ),

            "valid_pv_rows": int(
                merged_district[
                    "p_pvgis_kw_per_kwp"
                ].notna().sum()
            ),

            "valid_scaled_rows": int(
                merged_district[
                    "estimated_power_mw"
                ].notna().sum()
            ),

            "capacity_present": (
                not merged_district[
                    "capacity_mw"
                ].isna().any()
            ),

            "status": "OK",
        })

    return pd.DataFrame(rows)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print(
        "PHASE 2.4 - SCALE PVGIS TO REAL PROSOL CAPACITY"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Create output directory
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Load data
    # --------------------------------------------------------

    print("\nLoading normalized PVGIS data...")

    pvgis = load_pvgis()

    print(
        f"  PVGIS rows: {len(pvgis):,}"
    )

    print("\nLoading Prosol district capacities...")

    prosol = load_prosol_capacity()

    print(
        f"  Prosol districts: {len(prosol)}"
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    validate_districts(
        pvgis,
        prosol
    )

    # --------------------------------------------------------
    # Merge
    # --------------------------------------------------------

    print(
        "\nJoining PVGIS with Prosol capacity..."
    )

    merged = merge_datasets(
        pvgis,
        prosol
    )

    print(
        f"  Joined rows: {len(merged):,}"
    )

    # --------------------------------------------------------
    # Calculate production
    # --------------------------------------------------------

    print(
        "\nCalculating district-level production..."
    )

    merged = calculate_production(
        merged
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    print(
        "\nValidating scaled production..."
    )

    validate_production(
        merged
    )

    # --------------------------------------------------------
    # Select final columns
    # --------------------------------------------------------

    final_columns = [

        "district_id",
        "district_name",

        "region_id",
        "region_name",

        "latitude",
        "longitude",

        "timestamp",

        "capacity_mw",
        "capacity_source",

        "p_pvgis_kw_per_kwp",

        "estimated_power_mw",

        "ghi_w_m2",
        "beam_w_m2",
        "diffuse_w_m2",
        "reflected_w_m2",

        "solar_elevation_deg",
        "temperature_2m_c",
        "wind_speed_10m_ms",

        "pv_reference",
    ]

    merged = merged[
        final_columns
    ]

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    merged = merged.sort_values(
        [
            "district_id",
            "timestamp",
        ]
    ).reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # Save hourly dataset
    # --------------------------------------------------------

    print(
        "\nSaving district hourly production..."
    )

    merged.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print(
        "Building district summary..."
    )

    summary = build_summary(
        merged
    )

    summary.to_csv(
        SUMMARY_FILE,
        index=False,
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Validation report
    # --------------------------------------------------------

    print(
        "Building validation report..."
    )

    validation = build_validation_report(
        pvgis,
        prosol,
        merged
    )

    validation.to_csv(
        VALIDATION_FILE,
        index=False,
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Final statistics
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print(
        "PHASE 2.4 COMPLETE"
    )
    print("=" * 70)

    print(
        f"\nDistricts          : "
        f"{merged['district_id'].nunique()}"
    )

    print(
        f"Hourly rows        : "
        f"{len(merged):,}"
    )

    print(
        f"Total Prosol MW    : "
        f"{prosol['capacity_mw'].sum():.3f}"
    )

    valid_power = (
        merged[
            "estimated_power_mw"
        ].dropna()
    )

    print(
        f"\nEstimated production:"
    )

    print(
        f"  Minimum          : "
        f"{valid_power.min():.6f} MW"
    )

    print(
        f"  Maximum          : "
        f"{valid_power.max():.6f} MW"
    )

    print(
        f"  Mean             : "
        f"{valid_power.mean():.6f} MW"
    )

    print("\nOutputs:")

    print(
        f"  Hourly dataset:"
    )
    print(
        f"    {OUTPUT_FILE}"
    )

    print(
        f"\n  District summary:"
    )
    print(
        f"    {SUMMARY_FILE}"
    )

    print(
        f"\n  Validation:"
    )
    print(
        f"    {VALIDATION_FILE}"
    )

    print(
        "\nNo synthetic production data was generated."
    )

    print(
        "\nPhase 2.4 successfully completed."
    )


if __name__ == "__main__":
    main()