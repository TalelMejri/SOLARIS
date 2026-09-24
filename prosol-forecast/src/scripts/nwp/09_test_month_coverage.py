from pathlib import Path
import cdsapi
import time

PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "nwp" / "month_coverage_test"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

client = cdsapi.Client()


YEAR = "2020"
MONTH = "06"

REQUEST_BASE = {
    "origin": "ecmwf",
    "level_type": "single_level",
    "variable": [
        "10_m_u_component_of_wind",
        "10_m_v_component_of_wind",
        "2_m_temperature",
        "total_cloud_cover",
    ],
    "forecast_type": "control_forecast",
    "leadtime_hour": [
        "6",
        "12",
        "24",
        "72",
    ],
    "data_format": "grib",
    "area": [
        37.6,
        7.5,
        30.0,
        12.5,
    ],
}


success = []
failed = []


for day in range(1, 31):

    day_str = f"{day:02d}"

    output_file = OUTPUT_DIR / f"ecmwf_tigge_{YEAR}-{MONTH}-{day_str}_00.grib"

    print("\n" + "=" * 70)
    print(f"RUN {YEAR}-{MONTH}-{day_str} 00:00 UTC")
    print("=" * 70)

    if output_file.exists() and output_file.stat().st_size > 0:

        size_mb = output_file.stat().st_size / (1024 * 1024)

        print(f"ALREADY EXISTS: {size_mb:.2f} MB")

        success.append(day_str)

        continue

    request = {
        **REQUEST_BASE,
        "year": YEAR,
        "month": MONTH,
        "day": day_str,
        "time": "00:00",
    }

    try:

        client.retrieve(
            "tigge-forecasts",
            request,
            str(output_file),
        )

        size_mb = output_file.stat().st_size / (1024 * 1024)

        if size_mb > 0:

            print(f"SUCCESS: {size_mb:.2f} MB")

            success.append(day_str)

        else:

            print("FAILED: empty file")

            failed.append(day_str)

    except Exception as exc:

        print("FAILED")

        print(type(exc).__name__)
        print(str(exc))

        failed.append(day_str)

    # Small delay to avoid hammering the service
    time.sleep(1)


print("\n" + "=" * 70)
print("MONTH COVERAGE SUMMARY")
print("=" * 70)

print("Year:", YEAR)
print("Month:", MONTH)

print("Successful:", len(success))
print("Failed:", len(failed))

print("\nSuccessful days:")
print(success)

print("\nFailed days:")
print(failed)

if len(success) > 0:

    coverage = len(success) / 30 * 100

    print(f"\nCoverage: {coverage:.2f}%")
