from pathlib import Path
import cdsapi


PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "nwp" / "coverage_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

client = cdsapi.Client()

TEST_RUNS = [
    ("2018", "06", "01", "00:00"),
    ("2019", "06", "01", "00:00"),
    ("2020", "06", "01", "00:00"),
]


REQUEST = {
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


for year, month, day, time in TEST_RUNS:

    output_file = (
        OUTPUT_DIR
        / f"ecmwf_tigge_{year}-{month}-{day}_00.grib"
    )

    print("\n" + "=" * 70)
    print(f"TESTING {year}-{month}-{day} {time}")
    print("=" * 70)

    request = {
        **REQUEST,
        "year": year,
        "month": month,
        "day": day,
        "time": time,
    }

    print("Output:", output_file)

    try:
        client.retrieve(
            "tigge-forecasts",
            request,
            str(output_file),
        )

        size_mb = output_file.stat().st_size / (1024 * 1024)

        print(f"SUCCESS: {size_mb:.2f} MB")

    except Exception as exc:
        print("FAILED")
        print(type(exc).__name__)
        print(str(exc))