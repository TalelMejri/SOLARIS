from pathlib import Path
import json
import csv
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = ROOT / "data" / "raw" / "municipalities.json"
OUTPUT_DIR = ROOT / "data" / "reference"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""

    return str(value).strip()


def load_data():
    """
    Load the API JSON.

    Expected structure:

    [
        {
            "Name": "ARIANA",
            "NameAr": "أريانة",
            "Value": "ARIANA",
            "Delegations": [
                {
                    "Name": "ARIANA VILLE (...)",
                    "NameAr": "...",
                    "Value": "ARIANA VILLE",
                    "PostalCode": "2058",
                    "Latitude": 36.866011,
                    "Longitude": 10.193923
                }
            ]
        }
    ]
    """

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found:\n{INPUT_FILE}"
        )

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            "Expected the API JSON to contain a list of municipalities."
        )

    return data


# ============================================================
# FLATTEN NESTED API
# ============================================================

def flatten_api_data(data):
    """
    Convert nested municipality -> Delegations
    into flat locality records.

    Example:

    Municipality:
        ARIANA

    Delegation/locality:
        ARIANA VILLE (Residence Kortoba)

    becomes:

        parent_municipality = ARIANA
        municipality = ARIANA VILLE
        locality_name = ARIANA VILLE (Residence Kortoba)
    """

    rows = []

    for parent in data:

        parent_name = clean(parent.get("Name"))
        parent_name_ar = clean(parent.get("NameAr"))
        parent_value = clean(parent.get("Value"))

        delegations = parent.get("Delegations", [])

        if not isinstance(delegations, list):
            continue

        for delegation in delegations:

            rows.append({
                "parent_municipality": parent_name,
                "parent_municipality_ar": parent_name_ar,
                "parent_municipality_value": parent_value,

                "locality_name": clean(
                    delegation.get("Name")
                ),

                "locality_name_ar": clean(
                    delegation.get("NameAr")
                ),

                "municipality": clean(
                    delegation.get("Value")
                ),

                "postal_code": clean(
                    delegation.get("PostalCode")
                ),

                "latitude": delegation.get("Latitude"),

                "longitude": delegation.get("Longitude"),
            })

    return rows


# ============================================================
# LOCALITIES CSV
# ============================================================

def build_localities_csv(rows):

    output = OUTPUT_DIR / "localities.csv"

    fieldnames = [
        "parent_municipality",
        "parent_municipality_ar",
        "parent_municipality_value",
        "locality_name",
        "locality_name_ar",
        "municipality",
        "postal_code",
        "latitude",
        "longitude",
    ]

    with open(
        output,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] {output}")
    print(f"     Locality records: {len(rows)}")


# ============================================================
# MUNICIPALITIES CSV
# ============================================================

def build_municipalities_csv(rows):

    output = OUTPUT_DIR / "municipalities.csv"

    municipalities = defaultdict(list)

    for row in rows:

        municipality = clean(
            row["municipality"]
        )

        if municipality:
            municipalities[municipality].append(row)

    result = []

    for municipality, items in sorted(
        municipalities.items()
    ):

        latitudes = []
        longitudes = []
        postal_codes = set()

        parent_names = set()

        for item in items:

            parent = clean(
                item["parent_municipality"]
            )

            if parent:
                parent_names.add(parent)

            postal = clean(
                item["postal_code"]
            )

            if postal:
                postal_codes.add(postal)

            try:
                latitudes.append(
                    float(item["latitude"])
                )
            except (
                ValueError,
                TypeError
            ):
                pass

            try:
                longitudes.append(
                    float(item["longitude"])
                )
            except (
                ValueError,
                TypeError
            ):
                pass

        latitude = (
            sum(latitudes) / len(latitudes)
            if latitudes
            else ""
        )

        longitude = (
            sum(longitudes) / len(longitudes)
            if longitudes
            else ""
        )

        result.append({
            "municipality": municipality,

            "parent_municipality": (
                ";".join(sorted(parent_names))
            ),

            "locality_count": len(items),

            "postal_code_count": len(
                postal_codes
            ),

            "latitude": (
                round(latitude, 6)
                if latitude != ""
                else ""
            ),

            "longitude": (
                round(longitude, 6)
                if longitude != ""
                else ""
            ),
        })

    fieldnames = [
        "municipality",
        "parent_municipality",
        "locality_count",
        "postal_code_count",
        "latitude",
        "longitude",
    ]

    with open(
        output,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(result)

    print(f"[OK] {output}")
    print(
        f"     Unique municipalities: {len(result)}"
    )


# ============================================================
# VALIDATION
# ============================================================

def validate(rows):

    errors = []

    required = [
        "parent_municipality",
        "parent_municipality_value",
        "locality_name",
        "locality_name_ar",
        "municipality",
        "postal_code",
        "latitude",
        "longitude",
    ]

    for index, row in enumerate(
        rows,
        start=1
    ):

        # ----------------------------------------------------
        # Required fields
        # ----------------------------------------------------

        for field in required:

            if field not in row:

                errors.append(
                    f"Row {index}: missing field '{field}'"
                )

        # ----------------------------------------------------
        # Municipality
        # ----------------------------------------------------

        if not clean(
            row.get("municipality")
        ):

            errors.append(
                f"Row {index}: empty municipality"
            )

        # ----------------------------------------------------
        # Locality
        # ----------------------------------------------------

        if not clean(
            row.get("locality_name")
        ):

            errors.append(
                f"Row {index}: empty locality name"
            )

        # ----------------------------------------------------
        # Latitude
        # ----------------------------------------------------

        try:

            latitude = float(
                row.get("latitude")
            )

            if not -90 <= latitude <= 90:

                errors.append(
                    f"Row {index}: invalid latitude "
                    f"{latitude}"
                )

        except (
            ValueError,
            TypeError
        ):

            errors.append(
                f"Row {index}: invalid latitude"
            )

        # ----------------------------------------------------
        # Longitude
        # ----------------------------------------------------

        try:

            longitude = float(
                row.get("longitude")
            )

            if not -180 <= longitude <= 180:

                errors.append(
                    f"Row {index}: invalid longitude "
                    f"{longitude}"
                )

        except (
            ValueError,
            TypeError
        ):

            errors.append(
                f"Row {index}: invalid longitude"
            )

    # ========================================================
    # REPORT
    # ========================================================

    print()
    print("========================================")
    print("GEOGRAPHY VALIDATION")
    print("========================================")

    if errors:

        print(
            f"[ERROR] {len(errors)} problems found"
        )

        for error in errors[:30]:

            print(
                " -",
                error
            )

        if len(errors) > 30:

            print(
                f" ... and "
                f"{len(errors) - 30} more"
            )

        raise ValueError(
            "Geography validation failed."
        )

    print(
        "[OK] All locality records are valid."
    )


# ============================================================
# STATISTICS
# ============================================================

def print_statistics(raw_data, rows):

    municipalities = set()
    parents = set()
    postal_codes = set()

    for row in rows:

        municipalities.add(
            row["municipality"]
        )

        parents.add(
            row["parent_municipality"]
        )

        if row["postal_code"]:

            postal_codes.add(
                row["postal_code"]
            )

    print()
    print("========================================")
    print("GEOGRAPHY STATISTICS")
    print("========================================")

    print(
        f"Top-level municipalities: "
        f"{len(raw_data)}"
    )

    print(
        f"Parent municipalities: "
        f"{len(parents)}"
    )

    print(
        f"Unique municipalities: "
        f"{len(municipalities)}"
    )

    print(
        f"Locality records: "
        f"{len(rows)}"
    )

    print(
        f"Postal codes: "
        f"{len(postal_codes)}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("========================================")
    print("BUILD GEOGRAPHY CSV")
    print("========================================")
    print()

    # --------------------------------------------------------
    # 1. Load JSON
    # --------------------------------------------------------

    raw_data = load_data()

    print(
        f"[OK] Loaded "
        f"{len(raw_data)} top-level municipalities"
    )

    # --------------------------------------------------------
    # 2. Flatten nested structure
    # --------------------------------------------------------

    rows = flatten_api_data(
        raw_data
    )

    print(
        f"[OK] Flattened "
        f"{len(rows)} locality records"
    )

    # --------------------------------------------------------
    # 3. Validate
    # --------------------------------------------------------

    validate(rows)

    # --------------------------------------------------------
    # 4. Create localities.csv
    # --------------------------------------------------------

    build_localities_csv(
        rows
    )

    # --------------------------------------------------------
    # 5. Create municipalities.csv
    # --------------------------------------------------------

    build_municipalities_csv(
        rows
    )

    # --------------------------------------------------------
    # 6. Statistics
    # --------------------------------------------------------

    print_statistics(
        raw_data,
        rows
    )

    print()
    print("========================================")
    print("DONE")
    print("========================================")


if __name__ == "__main__":
    main()