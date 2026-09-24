from pathlib import Path
from datetime import date, timedelta
import cdsapi
import time


PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "nwp"
    / "long_term_coverage_test"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

client = cdsapi.Client()

YEARS = [2018, 2019, 2020]
TEST_DATES = [
    "2018-01-15",
    "2019-01-15",
    "2020-01-15",
    "2021-01-15",
    "2022-01-15",
    "2022-10-15",
]

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


# for year in YEARS:

#     current = date(year, 1, 1)

#     # First day on/after Jan 1, then every 7 days.
#     while current.year == year:

#         day_str = current.strftime("%Y-%m-%d")

#         output_file = (
#             OUTPUT_DIR
#             / f"ecmwf_tigge_{day_str}_00.grib"
#         )

#         print("\n" + "=" * 70)
#         print(f"TESTING {day_str} 00:00 UTC")
#         print("=" * 70)

#         if output_file.exists() and output_file.stat().st_size > 0:

#             print("ALREADY EXISTS")

#             success.append(day_str)

#         else:

#             request = {
#                 **REQUEST_BASE,
#                 "year": current.strftime("%Y"),
#                 "month": current.strftime("%m"),
#                 "day": current.strftime("%d"),
#                 "time": "00:00",
#             }

#             try:

#                 client.retrieve(
#                     "tigge-forecasts",
#                     request,
#                     str(output_file),
#                 )

#                 size_mb = output_file.stat().st_size / (
#                     1024 * 1024
#                 )

#                 if size_mb > 0:

#                     print(f"SUCCESS: {size_mb:.2f} MB")

#                     success.append(day_str)

#                 else:

#                     print("FAILED: empty file")

#                     failed.append(day_str)

#             except Exception as exc:

#                 print("FAILED")
#                 print(type(exc).__name__)
#                 print(str(exc))

#                 failed.append(day_str)

#         time.sleep(1)

#         current += timedelta(days=7)
for day_str in TEST_DATES:

    output_file = (
        OUTPUT_DIR
        / f"ecmwf_tigge_{day_str}_00.grib"
    )

    print("\n" + "=" * 70)
    print(f"TESTING {day_str} 00:00 UTC")
    print("=" * 70)

    if output_file.exists() and output_file.stat().st_size > 0:

        print("ALREADY EXISTS")
        success.append(day_str)

    else:

        current = date.fromisoformat(day_str)

        request = {
            **REQUEST_BASE,
            "year": current.strftime("%Y"),
            "month": current.strftime("%m"),
            "day": current.strftime("%d"),
            "time": "00:00",
        }

        try:

            client.retrieve(
                "tigge-forecasts",
                request,
                str(output_file),
            )

            size_mb = output_file.stat().st_size / (
                1024 * 1024
            )

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

    time.sleep(1)


print("\n" + "=" * 70)
print("LONG-TERM COVERAGE SUMMARY")
print("=" * 70)

total = len(success) + len(failed)

print("Requested:", total)
print("Successful:", len(success))
print("Failed:", len(failed))

if total:
    print(
        f"Coverage: "
        f"{100 * len(success) / total:.2f}%"
    )

print("\nFailed dates:")

for item in failed:
    print(item)