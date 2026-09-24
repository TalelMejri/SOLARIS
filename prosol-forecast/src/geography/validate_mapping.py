from pathlib import Path
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "data" / "reference"

MAPPING_FILE = REFERENCE / "municipality_district_mapping.csv"
DISTRICTS_FILE = REFERENCE / "districts.csv"
REGIONS_FILE = REFERENCE / "regions.csv"
DISTRICT_REGION_FILE = REFERENCE / "district_region_mapping.csv"


print("=" * 70)
print("VALIDATE MUNICIPALITY → DISTRICT → REGION MAPPING")
print("=" * 70)


mapping = pd.read_csv(
    MAPPING_FILE,
    dtype=str
)

districts = pd.read_csv(
    DISTRICTS_FILE,
    dtype=str
)

regions = pd.read_csv(
    REGIONS_FILE,
    dtype=str
)

district_region = pd.read_csv(
    DISTRICT_REGION_FILE,
    dtype=str
)


# ------------------------------------------------------------
# REQUIRED COLUMNS
# ------------------------------------------------------------

required = {
    "municipality",
    "parent_municipality",
    "prosol_district_id",
    "prosol_district_name",
    "region_id",
    "region_name",
    "mapping_status",
    "mapping_method",
    "confidence",
    "notes",
}

missing = required - set(mapping.columns)

if missing:
    raise ValueError(
        f"Missing mapping columns: {sorted(missing)}"
    )


# ------------------------------------------------------------
# BASIC COUNTS
# ------------------------------------------------------------

print(f"\nMunicipalities : {len(mapping)}")
print(f"Districts      : {len(districts)}")
print(f"Regions        : {len(regions)}")


# ------------------------------------------------------------
# DISTRICT COUNT
# ------------------------------------------------------------

if len(districts) != 50:
    raise ValueError(
        f"Expected 50 Prosol districts, found {len(districts)}"
    )


# ------------------------------------------------------------
# VALID STATUS
# ------------------------------------------------------------

valid_status = {
    "MAPPED",
    "REVIEW",
    "UNMAPPED",
}

bad_status = mapping[
    ~mapping["mapping_status"].isin(valid_status)
]

if len(bad_status):

    print("\nINVALID STATUSES:")
    print(
        bad_status[
            ["municipality", "mapping_status"]
        ].to_string(index=False)
    )

    raise ValueError("Invalid mapping status found.")


# ------------------------------------------------------------
# MAPPED RECORDS
# ------------------------------------------------------------

mapped = mapping[
    mapping["mapping_status"] == "MAPPED"
]

review = mapping[
    mapping["mapping_status"] == "REVIEW"
]

unmapped = mapping[
    mapping["mapping_status"] == "UNMAPPED"
]


print("\nSTATUS")
print("-" * 70)
print(f"MAPPED   : {len(mapped)}")
print(f"REVIEW   : {len(review)}")
print(f"UNMAPPED : {len(unmapped)}")


# ------------------------------------------------------------
# VALID DISTRICT IDS
# ------------------------------------------------------------

valid_district_ids = set(
    district_region["district_id"].astype(str)
)

mapped_ids = set(
    mapped["prosol_district_id"].astype(str)
)

invalid_ids = mapped[
    ~mapped["prosol_district_id"].astype(str).isin(
        valid_district_ids
    )
]

if len(invalid_ids):

    print("\nINVALID DISTRICT IDS:")
    print(
        invalid_ids.to_string(index=False)
    )

    raise ValueError(
        "Mapped municipality references a nonexistent Prosol district."
    )


# ------------------------------------------------------------
# VALID REGION IDS
# ------------------------------------------------------------

valid_region_ids = set(
    regions["region_id"].astype(str)
)

invalid_regions = mapped[
    ~mapped["region_id"].astype(str).isin(
        valid_region_ids
    )
]

if len(invalid_regions):

    raise ValueError(
        "Mapping contains an invalid region ID."
    )


# ------------------------------------------------------------
# DISTRICT → REGION CONSISTENCY
# ------------------------------------------------------------

errors = []

for _, row in mapping[
    mapping["mapping_status"].isin(
        ["MAPPED", "REVIEW"]
    )
].iterrows():

    district_id = str(
        row["prosol_district_id"]
    ).strip()

    if not district_id:
        continue

    reference = district_region[
        district_region["district_id"].astype(str)
        == district_id
    ]

    if len(reference) != 1:

        errors.append(
            (
                row["municipality"],
                "district_not_unique"
            )
        )

        continue

    expected = reference.iloc[0]

    if str(row["region_id"]) != str(
        expected["region_id"]
    ):

        errors.append(
            (
                row["municipality"],
                "region_id_mismatch"
            )
        )

    if str(row["region_name"]).strip() != str(
        expected["region_name"]
    ).strip():

        errors.append(
            (
                row["municipality"],
                "region_name_mismatch"
            )
        )


if errors:

    print("\nDISTRICT/REGION ERRORS:")

    for error in errors:
        print(error)

    raise ValueError(
        "District-region consistency validation failed."
    )


# ------------------------------------------------------------
# DUPLICATE MUNICIPALITY CHECK
# ------------------------------------------------------------

duplicates = mapping[
    mapping["municipality"]
    .str.upper()
    .duplicated(keep=False)
]

if len(duplicates):

    print("\nDUPLICATE MUNICIPALITIES:")

    print(
        duplicates[
            [
                "municipality",
                "prosol_district_name",
                "mapping_status"
            ]
        ].to_string(index=False)
    )

    raise ValueError(
        "Duplicate municipality mappings detected."
    )


# ------------------------------------------------------------
# MAKE SURE NO OLD COLUMNS / FORMAT
# ------------------------------------------------------------

old_columns = {
    "district_name"
}

if old_columns.intersection(mapping.columns):

    raise ValueError(
        "Old mapping schema detected. "
        "Use prosol_district_name instead."
    )


# ------------------------------------------------------------
# FINAL
# ------------------------------------------------------------

print("\n" + "=" * 70)
print("MAPPING VALIDATION PASSED")
print("=" * 70)

print("\nThe mapping is structurally valid.")

print(
    "\nIMPORTANT: REVIEW and UNMAPPED records are not "
    "considered verified geographic mappings."
)

print("\nYou can now inspect the REVIEW records before Phase 2.")