from pathlib import Path
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DISTRICTS_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "districts.csv"
)

COORDINATES_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "district_coordinates.csv"
)


REQUIRED_COLUMNS = [
    "district_id",
    "district_name",
    "region_id",
    "region_name",
    "latitude",
    "longitude",
    "coordinate_method",
    "source_points_count",
]


print("=" * 70)
print("VALIDATE DISTRICT COORDINATES")
print("=" * 70)


districts = pd.read_csv(DISTRICTS_FILE)
coordinates = pd.read_csv(COORDINATES_FILE)


# ------------------------------------------------------------
# Columns
# ------------------------------------------------------------

missing = [
    column
    for column in REQUIRED_COLUMNS
    if column not in coordinates.columns
]

if missing:
    raise ValueError(
        f"Missing columns: {missing}"
    )

print("\n[1] Columns OK")


# ------------------------------------------------------------
# Number of districts
# ------------------------------------------------------------

if len(coordinates) != 50:
    raise ValueError(
        f"Expected 50 rows, found {len(coordinates)}"
    )

print("[2] Exactly 50 coordinate rows")


# ------------------------------------------------------------
# Unique IDs
# ------------------------------------------------------------

if coordinates["district_id"].duplicated().any():
    raise ValueError(
        "Duplicate district IDs detected."
    )

print("[3] District IDs are unique")


# ------------------------------------------------------------
# All districts represented
# ------------------------------------------------------------

expected_ids = set(
    districts["district_id"].astype(int)
)

actual_ids = set(
    coordinates["district_id"].astype(int)
)

missing_ids = expected_ids - actual_ids
extra_ids = actual_ids - expected_ids

if missing_ids:
    raise ValueError(
        f"Missing district IDs: {sorted(missing_ids)}"
    )

if extra_ids:
    raise ValueError(
        f"Unknown district IDs: {sorted(extra_ids)}"
    )

print("[4] All 50 Prosol districts represented")


# ------------------------------------------------------------
# Coordinates
# ------------------------------------------------------------

coordinates["latitude"] = pd.to_numeric(
    coordinates["latitude"],
    errors="coerce"
)

coordinates["longitude"] = pd.to_numeric(
    coordinates["longitude"],
    errors="coerce"
)

missing_coordinates = coordinates[
    coordinates["latitude"].isna()
    | coordinates["longitude"].isna()
]

if len(missing_coordinates) > 0:
    print(
        "\nWARNING: Missing coordinates:"
    )

    print(
        missing_coordinates[
            [
                "district_id",
                "district_name",
            ]
        ].to_string(index=False)
    )
else:
    print("[5] All districts have coordinates")


# ------------------------------------------------------------
# Tunisia coordinate sanity check
# ------------------------------------------------------------

valid = coordinates[
    coordinates["latitude"].notna()
    & coordinates["longitude"].notna()
]

# Broad Tunisia bounding box
invalid_tunisia = valid[
    ~valid["latitude"].between(30, 38)
    | ~valid["longitude"].between(7, 12)
]

if len(invalid_tunisia) > 0:

    print(
        "\nWARNING: Coordinates outside broad Tunisia bounds:"
    )

    print(
        invalid_tunisia[
            [
                "district_id",
                "district_name",
                "latitude",
                "longitude",
            ]
        ].to_string(index=False)
    )
else:
    print("[6] Coordinates are inside Tunisia sanity bounds")


# ------------------------------------------------------------
# Coordinate method
# ------------------------------------------------------------

allowed_methods = {
    "GEOGRAPHIC_CENTROID",
    "MISSING",
}

invalid_methods = set(
    coordinates["coordinate_method"].dropna()
) - allowed_methods

if invalid_methods:
    raise ValueError(
        f"Unexpected coordinate methods: {invalid_methods}"
    )

print("[7] Coordinate methods valid")


# ------------------------------------------------------------
# Source points
# ------------------------------------------------------------

if (
    coordinates["source_points_count"]
    .dropna()
    .astype(int)
    .lt(0)
    .any()
):
    raise ValueError(
        "Negative source_points_count detected."
    )

print("[8] Source point counts valid")


# ------------------------------------------------------------
# Result
# ------------------------------------------------------------

print("\n" + "=" * 70)
print("VALIDATION COMPLETE")
print("=" * 70)

print(
    f"Total districts       : {len(coordinates)}"
)

print(
    f"With coordinates      : {len(valid)}"
)

print(
    f"Without coordinates   : {len(missing_coordinates)}"
)

print(
    "\nCoordinate method distribution:"
)

print(
    coordinates[
        "coordinate_method"
    ].value_counts().to_string()
)

print("\nNo structural errors detected.")