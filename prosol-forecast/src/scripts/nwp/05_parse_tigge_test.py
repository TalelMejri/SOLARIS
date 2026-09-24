from pathlib import Path

import cfgrib
import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

GRIB_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "nwp"
    / "tigge_test"
    / "ecmwf_tigge_tunisia_2023-06-01_00.grib"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "nwp"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "tigge_test_normalized.parquet"
)


# ============================================================
# HELPERS
# ============================================================

def find_dataset(datasets, variable_name):
    """
    Find the GRIB dataset containing a specific variable.
    """
    for ds in datasets:
        if variable_name in ds.data_vars:
            return ds

    raise ValueError(
        f"Variable '{variable_name}' was not found "
        f"in the GRIB datasets."
    )


def dataset_to_long_dataframe(ds, variable_name):
    """
    Convert one cfgrib dataset into a long dataframe:

    issue_time
    valid_time
    lead_hours
    latitude
    longitude
    variable
    value
    """

    values = ds[variable_name].values

    steps = ds["step"].values
    valid_times = ds["valid_time"].values

    latitude = ds["latitude"].values
    longitude = ds["longitude"].values

    issue_time = pd.Timestamp(
        ds["time"].values
    ).tz_localize("UTC")

    rows = []

    for step_index, step in enumerate(steps):

        lead_hours = (
            pd.Timedelta(step).total_seconds()
            / 3600.0
        )

        valid_time = pd.Timestamp(
            valid_times[step_index]
        ).tz_localize("UTC")

        for point_index in range(len(latitude)):

            rows.append(
                {
                    "forecast_issue_time_utc": issue_time,
                    "forecast_valid_time_utc": valid_time,
                    "forecast_lead_hours": int(lead_hours),
                    "latitude": float(latitude[point_index]),
                    "longitude": float(longitude[point_index]),
                    variable_name: float(
                        values[step_index, point_index]
                    ),
                }
            )

    return pd.DataFrame(rows)


# ============================================================
# MAIN
# ============================================================

print("=" * 70)
print("TIGGE TEST PARSER")
print("=" * 70)

print(f"\nInput:")
print(GRIB_FILE)

if not GRIB_FILE.exists():
    raise FileNotFoundError(
        f"GRIB file not found:\n{GRIB_FILE}"
    )


# ------------------------------------------------------------
# Open GRIB
# ------------------------------------------------------------

print("\nOpening GRIB...")

datasets = cfgrib.open_datasets(
    str(GRIB_FILE),
    backend_kwargs={
        "indexpath": "",
    },
)

print(f"Found {len(datasets)} GRIB datasets.")


# ------------------------------------------------------------
# Locate variables
# ------------------------------------------------------------

t2m_ds = find_dataset(datasets, "t2m")
u10_ds = find_dataset(datasets, "u10")
tcc_ds = find_dataset(datasets, "tcc")

print("\nVariables found:")
print("  t2m")
print("  u10")
print("  v10")
print("  tcc")


# ------------------------------------------------------------
# Convert each dataset
# ------------------------------------------------------------

print("\nConverting t2m...")

df_t2m = dataset_to_long_dataframe(
    t2m_ds,
    "t2m",
)

print(f"t2m rows: {len(df_t2m):,}")


print("\nConverting u10...")

df_u10 = dataset_to_long_dataframe(
    u10_ds,
    "u10",
)

print(f"u10 rows: {len(df_u10):,}")


print("\nConverting v10...")

df_v10 = dataset_to_long_dataframe(
    u10_ds,
    "v10",
)

print(f"v10 rows: {len(df_v10):,}")


print("\nConverting tcc...")

df_tcc = dataset_to_long_dataframe(
    tcc_ds,
    "tcc",
)

print(f"tcc rows: {len(df_tcc):,}")


# ============================================================
# MERGE VARIABLES
# ============================================================

KEYS = [
    "forecast_issue_time_utc",
    "forecast_valid_time_utc",
    "forecast_lead_hours",
    "latitude",
    "longitude",
]


print("\nMerging variables...")

df = df_t2m.merge(
    df_u10,
    on=KEYS,
    how="inner",
)

df = df.merge(
    df_tcc,
    on=KEYS,
    how="inner",
)

# v10 was generated from the same dataset as u10
# but it is not in df_u10 because the helper only retained
# the requested variable. Add it explicitly.

df_v10_only = dataset_to_long_dataframe(
    u10_ds,
    "v10",
)

df = df.merge(
    df_v10_only,
    on=KEYS,
    how="inner",
)


# ============================================================
# DERIVED VARIABLES
# ============================================================

df["temperature_2m_c"] = (
    df["t2m"] - 273.15
)

df["wind_speed_10m_ms"] = np.sqrt(
    df["u10"] ** 2
    + df["v10"] ** 2
)

df["wind_direction_10m_deg"] = (
    np.degrees(
        np.arctan2(
            -df["u10"],
            -df["v10"],
        )
    )
    + 360
) % 360

df["cloud_cover_fraction"] = df["tcc"] / 100.0


# ============================================================
# CLEAN COLUMN ORDER
# ============================================================

df = df[
    [
        "forecast_issue_time_utc",
        "forecast_valid_time_utc",
        "forecast_lead_hours",
        "latitude",
        "longitude",
        "temperature_2m_c",
        "u10",
        "v10",
        "wind_speed_10m_ms",
        "wind_direction_10m_deg",
        "tcc",
        "cloud_cover_fraction",
    ]
]


# ============================================================
# SORT
# ============================================================

df = df.sort_values(
    [
        "forecast_issue_time_utc",
        "forecast_lead_hours",
        "latitude",
        "longitude",
    ]
).reset_index(drop=True)


# ============================================================
# VALIDATION
# ============================================================

print("\n" + "=" * 70)
print("VALIDATION")
print("=" * 70)

print("\nShape:")
print(df.shape)

print("\nColumns:")
for column in df.columns:
    print(f"  {column}")

print("\nIssue times:")
print(
    df["forecast_issue_time_utc"]
    .drop_duplicates()
    .tolist()
)

print("\nLead times:")
print(
    sorted(
        df["forecast_lead_hours"]
        .unique()
        .tolist()
    )
)

print("\nValid times:")
print(
    df["forecast_valid_time_utc"]
    .drop_duplicates()
    .tolist()
)

print("\nMissing values:")
print(
    df.isna()
    .sum()
)

print("\nTemperature range:")
print(
    df["temperature_2m_c"].min(),
    "to",
    df["temperature_2m_c"].max(),
)

print("\nWind speed range:")
print(
    df["wind_speed_10m_ms"].min(),
    "to",
    df["wind_speed_10m_ms"].max(),
)

print("\nCloud cover range:")
print(
    df["cloud_cover_fraction"].min(),
    "to",
    df["cloud_cover_fraction"].max(),
)


# ============================================================
# SAVE
# ============================================================

print("\nSaving:")

df.to_parquet(
    OUTPUT_FILE,
    index=False,
)

print(OUTPUT_FILE)

print("\n" + "=" * 70)
print("PARSER COMPLETE")
print("=" * 70)