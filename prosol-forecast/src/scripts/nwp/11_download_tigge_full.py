from pathlib import Path
import calendar
import cdsapi
import time


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "nwp"
    / "tigge"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# PERIOD
# ============================================================

START_YEAR = 2018
END_YEAR = 2022

FORECAST_TIME = "00:00"

LEAD_TIMES = [
    "6",
    "12",
    "24",
    "72",
]


# ============================================================
# VARIABLES
# ============================================================

VARIABLES = [
    "10_m_u_component_of_wind",
    "10_m_v_component_of_wind",
    "2_m_temperature",
    "total_cloud_cover",
]


# ============================================================
# TUNISIA AREA
# ============================================================

AREA = [
    37.6,   # North
    7.5,    # West
    30.0,   # South
    12.5,   # East
]


# ============================================================
# CDS CLIENT
# ============================================================

client = cdsapi.Client()


# ============================================================
# STORAGE
# ============================================================

successful = []
skipped = []
failed = []


# ============================================================
# DOWNLOAD MONTH BY MONTH
# ============================================================

for year in range(START_YEAR, END_YEAR + 1):

    for month in range(1, 13):

        month_str = f"{month:02d}"

        output_file = (
            OUTPUT_DIR
            / f"ecmwf_tigge_{year}_{month_str}_00.grib"
        )

        print("\n" + "=" * 90)
        print(
            f"TIGGE MONTH DOWNLOAD: "
            f"{year}-{month_str}"
        )
        print("=" * 90)

        # ----------------------------------------------------
        # RESUME
        # ----------------------------------------------------

        if output_file.exists() and output_file.stat().st_size > 0:

            size_mb = output_file.stat().st_size / (
                1024 * 1024
            )

            print(
                f"ALREADY EXISTS → "
                f"{output_file.name}"
            )

            print(
                f"Size: {size_mb:.2f} MB"
            )

            skipped.append(
                f"{year}-{month_str}"
            )

            continue

        # ----------------------------------------------------
        # NUMBER OF DAYS IN MONTH
        # ----------------------------------------------------

        days_in_month = calendar.monthrange(
            year,
            month
        )[1]

        days = [
            f"{day:02d}"
            for day in range(
                1,
                days_in_month + 1
            )
        ]

        # ----------------------------------------------------
        # REQUEST
        # ----------------------------------------------------

        request = {
            "origin": "ecmwf",

            "level_type": "single_level",

            "variable": VARIABLES,

            "year": str(year),

            "month": month_str,

            "day": days,

            "time": FORECAST_TIME,

            "forecast_type": "control_forecast",

            "leadtime_hour": LEAD_TIMES,

            "data_format": "grib",

            "area": AREA,
        }

        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        try:

            print(
                f"Downloading {year}-{month_str}..."
            )

            print(
                f"Days: {days_in_month}"
            )

            print(
                f"Lead times: {LEAD_TIMES}"
            )

            print(
                "Variables:"
            )

            for variable in VARIABLES:
                print(f"  - {variable}")

            print()

            client.retrieve(
                "tigge-forecasts",
                request,
                str(output_file),
            )

            # ------------------------------------------------
            # VALIDATE FILE
            # ------------------------------------------------

            if (
                output_file.exists()
                and output_file.stat().st_size > 0
            ):

                size_mb = output_file.stat().st_size / (
                    1024 * 1024
                )

                print()
                print(
                    f"SUCCESS → "
                    f"{year}-{month_str}"
                )

                print(
                    f"File: {output_file.name}"
                )

                print(
                    f"Size: {size_mb:.2f} MB"
                )

                successful.append(
                    f"{year}-{month_str}"
                )

            else:

                print()
                print(
                    f"FAILED → "
                    f"empty output: "
                    f"{year}-{month_str}"
                )

                failed.append(
                    f"{year}-{month_str}"
                )

                if output_file.exists():
                    output_file.unlink()

        except Exception as exc:

            print()
            print(
                f"DOWNLOAD FAILED → "
                f"{year}-{month_str}"
            )

            print(
                f"Error type: "
                f"{type(exc).__name__}"
            )

            print(
                f"Error: {exc}"
            )

            failed.append(
                f"{year}-{month_str}"
            )

            # Remove potentially incomplete file
            if output_file.exists():

                try:
                    output_file.unlink()

                except Exception:
                    pass

            print(
                "Waiting 10 seconds before continuing..."
            )

            time.sleep(10)

        # Small pause between monthly requests
        time.sleep(3)


# ============================================================
# FINAL SUMMARY
# ============================================================

total_months = (
    (END_YEAR - START_YEAR + 1)
    * 12
)

completed = (
    len(successful)
    + len(skipped)
)

print("\n")
print("=" * 90)
print("TIGGE MONTHLY DOWNLOAD SUMMARY")
print("=" * 90)

print(
    f"Period:       "
    f"{START_YEAR}-01 → {END_YEAR}-12"
)

print(
    f"Total months: "
    f"{total_months}"
)

print(
    f"Successful:   "
    f"{len(successful)}"
)

print(
    f"Skipped:      "
    f"{len(skipped)}"
)

print(
    f"Failed:       "
    f"{len(failed)}"
)

print(
    f"Completed:    "
    f"{completed}/{total_months}"
)

print(
    f"Coverage:     "
    f"{100 * completed / total_months:.2f}%"
)


# ============================================================
# FAILED MONTHS
# ============================================================

if failed:

    print("\n")
    print("=" * 90)
    print("FAILED MONTHS")
    print("=" * 90)

    for item in failed:
        print(item)

    print()
    print(
        "Re-run the script to retry only these months."
    )

else:

    print()
    print(
        "ALL MONTHS DOWNLOADED SUCCESSFULLY."
    )


# ============================================================
# OUTPUT
# ============================================================

print()
print("=" * 90)
print("OUTPUT DIRECTORY")
print("=" * 90)

print(OUTPUT_DIR)