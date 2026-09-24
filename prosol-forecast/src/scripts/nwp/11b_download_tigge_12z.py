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
# CONFIGURATION — 12 UTC RUNS
# ============================================================

START_YEAR = 2018
END_YEAR = 2022

FORECAST_TIME = "12:00"   # <-- changed from 00:00

LEAD_TIMES = ["6", "12", "24", "72"]

VARIABLES = [
    "10_m_u_component_of_wind",
    "10_m_v_component_of_wind",
    "2_m_temperature",
    "total_cloud_cover",
]

AREA = [37.6, 7.5, 30.0, 12.5]


# ============================================================
# CDS CLIENT
# ============================================================

client = cdsapi.Client()


# ============================================================
# STATS
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

        # 12Z filename — distinct from 00Z
        output_file = (
            OUTPUT_DIR
            / f"ecmwf_tigge_{year}_{month_str}_12.grib"
        )

        print("\n" + "=" * 90)
        print(f"TIGGE 12Z MONTH DOWNLOAD: {year}-{month_str}")
        print("=" * 90)

        # ---------------- RESUME ----------------
        if output_file.exists() and output_file.stat().st_size > 0:
            size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"ALREADY EXISTS -> {output_file.name}")
            print(f"Size: {size_mb:.2f} MB")
            skipped.append(f"{year}-{month_str}")
            continue

        # ---------------- DAYS ----------------
        days_in_month = calendar.monthrange(year, month)[1]
        days = [f"{d:02d}" for d in range(1, days_in_month + 1)]

        # ---------------- REQUEST ----------------
        request = {
            "origin": "ecmwf",
            "level_type": "single_level",
            "variable": VARIABLES,
            "year": str(year),
            "month": month_str,
            "day": days,
            "time": FORECAST_TIME,     # 12:00 UTC
            "forecast_type": "control_forecast",
            "leadtime_hour": LEAD_TIMES,
            "data_format": "grib",
            "area": AREA,
        }

        # ---------------- DOWNLOAD ----------------
        try:
            print(f"Downloading {year}-{month_str} 12Z...")
            print(f"Days: {days_in_month}")

            client.retrieve(
                "tigge-forecasts",
                request,
                str(output_file),
            )

            if output_file.exists() and output_file.stat().st_size > 0:
                size_mb = output_file.stat().st_size / (1024 * 1024)
                print(f"SUCCESS -> {year}-{month_str} ({size_mb:.2f} MB)")
                successful.append(f"{year}-{month_str}")
            else:
                print(f"FAILED -> empty: {year}-{month_str}")
                failed.append(f"{year}-{month_str}")
                if output_file.exists():
                    output_file.unlink()

        except Exception as exc:
            print(f"DOWNLOAD FAILED -> {year}-{month_str}")
            print(f"Error type: {type(exc).__name__}")
            print(f"Error: {exc}")
            failed.append(f"{year}-{month_str}")
            if output_file.exists():
                try:
                    output_file.unlink()
                except Exception:
                    pass
            time.sleep(10)

        time.sleep(3)


# ============================================================
# FINAL SUMMARY
# ============================================================

total_months = (END_YEAR - START_YEAR + 1) * 12
completed = len(successful) + len(skipped)

print("\n")
print("=" * 90)
print("TIGGE 12Z MONTHLY DOWNLOAD SUMMARY")
print("=" * 90)
print(f"Period:       {START_YEAR}-01 -> {END_YEAR}-12")
print(f"Total months: {total_months}")
print(f"Successful:   {len(successful)}")
print(f"Skipped:      {len(skipped)}")
print(f"Failed:       {len(failed)}")
print(f"Completed:    {completed}/{total_months}")
print(f"Coverage:     {100 * completed / total_months:.2f}%")

if failed:
    print("\nFAILED MONTHS:")
    for item in failed:
        print(item)
    print("\nRe-run to retry only these months.")
else:
    print("\nALL 12Z MONTHS DOWNLOADED SUCCESSFULLY.")

print("\nOutput directory:")
print(OUTPUT_DIR)