from pathlib import Path
import pandas as pd
import numpy as np


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DISTRICTS_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "districts.csv"
)

MAPPING_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "municipality_district_mapping.csv"
)

LOCALITIES_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "localities.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "district_coordinates.csv"
)


# ============================================================
# HELPERS
# ============================================================

def normalize_text(value):
    if pd.isna(value):
        return ""

    return (
        str(value)
        .strip()
        .upper()
        .replace("\u00A0", " ")
    )


def geographic_centroid(latitudes, longitudes):
    """
    Simple geographic centroid.

    We do NOT weight by Prosol capacity because
    municipality-level capacity is unavailable.
    """

    latitudes = np.asarray(latitudes, dtype=float)
    longitudes = np.asarray(longitudes, dtype=float)

    return (
        float(latitudes.mean()),
        float(longitudes.mean())
    )


# ============================================================
# START
# ============================================================

print("=" * 70)
print("PHASE 2.1 - BUILD DISTRICT COORDINATES")
print("=" * 70)


# ============================================================
# 1. LOAD FILES
# ============================================================

print("\n[1/7] Loading reference files...")

districts = pd.read_csv(
    DISTRICTS_FILE,
    encoding="utf-8"
)

mapping = pd.read_csv(
    MAPPING_FILE,
    encoding="utf-8"
)

localities = pd.read_csv(
    LOCALITIES_FILE,
    encoding="utf-8"
)

print(f"  Districts   : {len(districts)}")
print(f"  Mappings    : {len(mapping)}")
print(f"  Localities  : {len(localities)}")

print("\n  districts.csv columns:")
print(
    "  "
    + ", ".join(districts.columns.tolist())
)


# ============================================================
# 2. VALIDATE PROSOL DISTRICTS
# ============================================================

print("\n[2/7] Validating Prosol districts...")

required_district_columns = [
    "district_id",
    "district_name",
]

missing = [
    col
    for col in required_district_columns
    if col not in districts.columns
]

if missing:
    raise ValueError(
        f"districts.csv is missing columns: {missing}"
    )


# Exactly 50 districts
if len(districts) != 50:
    raise ValueError(
        f"Expected exactly 50 Prosol districts, "
        f"found {len(districts)}."
    )


# Unique IDs
if districts["district_id"].duplicated().any():

    duplicates = districts[
        districts["district_id"].duplicated(keep=False)
    ]

    raise ValueError(
        "Duplicate district IDs found:\n"
        f"{duplicates.to_string(index=False)}"
    )


districts["district_id"] = (
    pd.to_numeric(
        districts["district_id"],
        errors="raise"
    )
    .astype(int)
)


print("  OK - exactly 50 unique Prosol districts.")


# ============================================================
# 3. VALIDATE MAPPING
# ============================================================

print("\n[3/7] Validating municipality → Prosol district mapping...")

required_mapping_columns = [
    "municipality",
    "prosol_district_id",
    "prosol_district_name",
    "region_id",
    "region_name",
]

missing = [
    col
    for col in required_mapping_columns
    if col not in mapping.columns
]

if missing:
    raise ValueError(
        "municipality_district_mapping.csv is missing columns: "
        f"{missing}"
    )


mapping["prosol_district_id"] = (
    pd.to_numeric(
        mapping["prosol_district_id"],
        errors="raise"
    )
    .astype(int)
)

mapping["region_id"] = (
    pd.to_numeric(
        mapping["region_id"],
        errors="raise"
    )
    .astype(int)
)


# Check that mapping references only real districts
expected_district_ids = set(
    districts["district_id"]
)

mapped_district_ids = set(
    mapping["prosol_district_id"]
)

unknown_districts = (
    mapped_district_ids
    - expected_district_ids
)

if unknown_districts:

    raise ValueError(
        "Mapping references unknown Prosol district IDs: "
        f"{sorted(unknown_districts)}"
    )


# ============================================================
# BUILD DISTRICT → REGION TABLE
# ============================================================

district_region = (
    mapping[
        [
            "prosol_district_id",
            "prosol_district_name",
            "region_id",
            "region_name",
        ]
    ]
    .drop_duplicates()
    .copy()
)


# Each Prosol district must have exactly one region
district_region_counts = (
    district_region
    .groupby("prosol_district_id")
    .size()
)

bad_district_region = (
    district_region_counts[
        district_region_counts > 1
    ]
)

if len(bad_district_region) > 0:

    raise ValueError(
        "Some Prosol districts are associated with "
        "multiple regions:\n"
        f"{bad_district_region}"
    )


if len(district_region) != 50:

    missing_regions = (
        expected_district_ids
        - set(district_region["prosol_district_id"])
    )

    raise ValueError(
        "Could not build region information for all 50 districts.\n"
        f"Missing: {sorted(missing_regions)}"
    )


print(
    "  OK - district → region relationship obtained "
    "from municipality_district_mapping.csv."
)


# ============================================================
# 4. PREPARE LOCALITIES
# ============================================================

print("\n[4/7] Preparing geographic points...")

required_locality_columns = [
    "municipality",
    "latitude",
    "longitude",
]

missing = [
    col
    for col in required_locality_columns
    if col not in localities.columns
]

if missing:
    raise ValueError(
        f"localities.csv is missing columns: {missing}"
    )


localities = localities.copy()


localities["municipality_key"] = (
    localities["municipality"]
    .map(normalize_text)
)


localities["latitude"] = pd.to_numeric(
    localities["latitude"],
    errors="coerce"
)

localities["longitude"] = pd.to_numeric(
    localities["longitude"],
    errors="coerce"
)


# Valid geographic points only
valid_geo = (
    localities["latitude"].notna()
    &
    localities["longitude"].notna()
    &
    localities["latitude"].between(-90, 90)
    &
    localities["longitude"].between(-180, 180)
)


localities_geo = localities.loc[
    valid_geo
].copy()


print(
    f"  Total locality rows : {len(localities)}"
)

print(
    f"  Valid geo points    : {len(localities_geo)}"
)


if len(localities_geo) == 0:

    raise ValueError(
        "No valid geographic points found in localities.csv."
    )


# ============================================================
# 5. JOIN LOCALITIES → MUNICIPALITY → PROSOL DISTRICT
# ============================================================

print(
    "\n[5/7] Joining geographic points "
    "to Prosol districts..."
)


mapping_geo = mapping[
    [
        "municipality",
        "prosol_district_id",
        "prosol_district_name",
        "region_id",
        "region_name",
    ]
].copy()


mapping_geo["municipality_key"] = (
    mapping_geo["municipality"]
    .map(normalize_text)
)


# Remove accidental duplicate municipality mappings
mapping_geo = (
    mapping_geo
    .drop_duplicates(
        subset=["municipality_key"]
    )
)


geo_points = localities_geo.merge(
    mapping_geo[
        [
            "municipality_key",
            "prosol_district_id",
            "prosol_district_name",
            "region_id",
            "region_name",
        ]
    ],
    on="municipality_key",
    how="inner",
)


print(
    f"  Geographic points mapped to districts: "
    f"{len(geo_points)}"
)


if len(geo_points) == 0:

    raise ValueError(
        "No locality coordinates could be connected "
        "to municipality_district_mapping.csv."
    )


# ============================================================
# 6. CALCULATE DISTRICT CENTROIDS
# ============================================================

print(
    "\n[6/7] Calculating geographic centroids..."
)


records = []


for _, district in districts.iterrows():

    district_id = int(
        district["district_id"]
    )

    district_name = str(
        district["district_name"]
    ).strip()


    # Find region information
    region_row = district_region[
        district_region["prosol_district_id"]
        == district_id
    ]

    if len(region_row) != 1:

        raise ValueError(
            f"Could not determine region for "
            f"district {district_id} - {district_name}"
        )


    region_id = int(
        region_row.iloc[0]["region_id"]
    )

    region_name = str(
        region_row.iloc[0]["region_name"]
    ).strip()


    # Geographic points belonging to this district
    points = geo_points[
        geo_points["prosol_district_id"]
        == district_id
    ].copy()


    # --------------------------------------------------------
    # No points
    # --------------------------------------------------------

    if len(points) == 0:

        print(
            f"  WARNING: No geographic points for "
            f"{district_id} - {district_name}"
        )

        records.append({

            "district_id": district_id,

            "district_name": district_name,

            "region_id": region_id,

            "region_name": region_name,

            "latitude": np.nan,

            "longitude": np.nan,

            "coordinate_method": "MISSING",

            "source_points_count": 0,

        })

        continue


    # --------------------------------------------------------
    # Centroid
    # --------------------------------------------------------

    latitude, longitude = geographic_centroid(
        points["latitude"],
        points["longitude"],
    )


    records.append({

        "district_id": district_id,

        "district_name": district_name,

        "region_id": region_id,

        "region_name": region_name,

        "latitude": round(latitude, 6),

        "longitude": round(longitude, 6),

        "coordinate_method": "GEOGRAPHIC_CENTROID",

        "source_points_count": len(points),

    })


# Create final dataframe
district_coordinates = pd.DataFrame(
    records
)


# ============================================================
# 7. FINAL VALIDATION
# ============================================================

print("\n[7/7] Validating output...")


# ------------------------------------------------------------
# Exactly 50 rows
# ------------------------------------------------------------

if len(district_coordinates) != 50:

    raise ValueError(
        f"Expected 50 output rows, "
        f"found {len(district_coordinates)}."
    )


# ------------------------------------------------------------
# Unique district IDs
# ------------------------------------------------------------

if district_coordinates[
    "district_id"
].duplicated().any():

    raise ValueError(
        "Duplicate district IDs found in output."
    )


# ------------------------------------------------------------
# All districts represented
# ------------------------------------------------------------

output_ids = set(
    district_coordinates[
        "district_id"
    ]
)

missing_ids = (
    expected_district_ids
    - output_ids
)

if missing_ids:

    raise ValueError(
        "Missing district IDs: "
        f"{sorted(missing_ids)}"
    )


# ------------------------------------------------------------
# Missing coordinates
# ------------------------------------------------------------

missing_coordinates = district_coordinates[
    district_coordinates["latitude"].isna()
    |
    district_coordinates["longitude"].isna()
]


# ------------------------------------------------------------
# Coordinate sanity check
# ------------------------------------------------------------

valid_coordinates = district_coordinates[
    district_coordinates["latitude"].notna()
    &
    district_coordinates["longitude"].notna()
]


invalid_coordinates = valid_coordinates[
    ~valid_coordinates["latitude"].between(30, 38)
    |
    ~valid_coordinates["longitude"].between(7, 12)
]


if len(invalid_coordinates) > 0:

    print(
        "\nWARNING: Coordinates outside Tunisia "
        "sanity bounds:"
    )

    print(
        invalid_coordinates[
            [
                "district_id",
                "district_name",
                "latitude",
                "longitude",
            ]
        ].to_string(index=False)
    )


# ============================================================
# SAVE
# ============================================================

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)


district_coordinates.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8"
)


# ============================================================
# SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("PHASE 2.1 COMPLETE")
print("=" * 70)

print(
    f"\nOutput file:"
)

print(
    f"  {OUTPUT_FILE}"
)

print(
    f"\nTotal districts       : "
    f"{len(district_coordinates)}"
)

print(
    f"With coordinates      : "
    f"{len(valid_coordinates)}"
)

print(
    f"Without coordinates   : "
    f"{len(missing_coordinates)}"
)

print(
    "\nCoordinate methods:"
)

print(
    district_coordinates[
        "coordinate_method"
    ]
    .value_counts()
    .to_string()
)


# ============================================================
# SHOW RESULTS
# ============================================================

print("\nGenerated district coordinates:\n")

print(
    district_coordinates.to_string(
        index=False
    )
)