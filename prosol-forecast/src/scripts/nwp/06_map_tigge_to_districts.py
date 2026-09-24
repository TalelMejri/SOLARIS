from pathlib import Path

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
    / "tigge_test_normalized.parquet"
)

DISTRICT_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "district_coordinates.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "nwp"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "tigge_test_district_mapping.csv"
)


# ============================================================
# LOAD DATA
# ============================================================

print("=" * 70)
print("TIGGE → DISTRICT MAPPING TEST")
print("=" * 70)

tigge = pd.read_parquet(TIGGE_FILE)
districts = pd.read_csv(DISTRICT_FILE)

print("\nTIGGE rows:", len(tigge))
print("District rows:", len(districts))

print("\nDistrict columns:")
print(districts.columns.tolist())


# ============================================================
# DETECT COORDINATE COLUMNS
# ============================================================

possible_lat = [
    "latitude",
    "lat",
    "Latitude",
    "LATITUDE",
]

possible_lon = [
    "longitude",
    "lon",
    "lng",
    "Longitude",
    "LONGITUDE",
]

lat_col = next(
    (
        c
        for c in possible_lat
        if c in districts.columns
    ),
    None,
)

lon_col = next(
    (
        c
        for c in possible_lon
        if c in districts.columns
    ),
    None,
)

if lat_col is None or lon_col is None:
    raise ValueError(
        "Could not identify latitude/longitude columns."
    )


# ============================================================
# DISTRICT ID / NAME
# ============================================================

possible_id = [
    "district_id",
    "id",
    "District_ID",
    "DISTRICT_ID",
]

possible_name = [
    "district_name",
    "name",
    "District_Name",
    "DISTRICT_NAME",
]

district_id_col = next(
    (
        c
        for c in possible_id
        if c in districts.columns
    ),
    None,
)

district_name_col = next(
    (
        c
        for c in possible_name
        if c in districts.columns
    ),
    None,
)

if district_id_col is None:
    raise ValueError(
        "Could not identify district ID column."
    )

if district_name_col is None:
    raise ValueError(
        "Could not identify district name column."
    )


# ============================================================
# UNIQUE TIGGE GRID
# ============================================================

grid = (
    tigge[
        [
            "latitude",
            "longitude",
        ]
    ]
    .drop_duplicates()
    .reset_index(drop=True)
)

print("\nUnique TIGGE spatial points:")
print(len(grid))


# ============================================================
# NEAREST GRID POINT
# ============================================================

def haversine_km(
    lat1,
    lon1,
    lat2,
    lon2,
):
    """
    Great-circle distance in km.
    """

    R = 6371.0088

    lat1 = np.radians(lat1)
    lat2 = np.radians(lat2)

    dlat = lat2 - lat1

    dlon = np.radians(
        lon2 - lon1
    )

    a = (
        np.sin(dlat / 2.0) ** 2
        +
        np.cos(lat1)
        * np.cos(lat2)
        * np.sin(dlon / 2.0) ** 2
    )

    return (
        2
        * R
        * np.arcsin(
            np.sqrt(a)
        )
    )


mapping_rows = []

for _, district in districts.iterrows():

    district_lat = float(
        district[lat_col]
    )

    district_lon = float(
        district[lon_col]
    )

    distances = haversine_km(
        district_lat,
        district_lon,
        grid["latitude"].values,
        grid["longitude"].values,
    )

    nearest_idx = int(
        np.argmin(distances)
    )

    nearest = grid.iloc[
        nearest_idx
    ]

    mapping_rows.append(
        {
            "district_id": district[
                district_id_col
            ],
            "district_name": district[
                district_name_col
            ],
            "district_latitude": district_lat,
            "district_longitude": district_lon,
            "nwp_latitude": float(
                nearest["latitude"]
            ),
            "nwp_longitude": float(
                nearest["longitude"]
            ),
            "distance_km": float(
                distances[nearest_idx]
            ),
        }
    )


mapping = pd.DataFrame(
    mapping_rows
)


# ============================================================
# VALIDATION
# ============================================================

print("\n" + "=" * 70)
print("MAPPING VALIDATION")
print("=" * 70)

print("\nDistricts mapped:")
print(len(mapping))

print("\nDistance statistics:")
print(
    mapping["distance_km"].describe()
)

print("\nMaximum distance:")
print(
    mapping["distance_km"].max()
)

print("\nDistricts with largest distances:")

print(
    mapping
    .sort_values(
        "distance_km",
        ascending=False,
    )
    .head(10)
    [
        [
            "district_id",
            "district_name",
            "distance_km",
        ]
    ]
    .to_string(index=False)
)


# ============================================================
# SAVE
# ============================================================

mapping.to_csv(
    OUTPUT_FILE,
    index=False,
)

print("\nSaved:")
print(OUTPUT_FILE)

print("\n" + "=" * 70)
print("MAPPING COMPLETE")
print("=" * 70)