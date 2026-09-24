import cdsapi
from pathlib import Path

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

OUTPUT_DIR = Path("data/raw/nwp/tigge_test")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_FILE = OUTPUT_DIR / "ecmwf_tigge_tunisia_2023-06-01_00.grib"

# Tunisia + small geographic buffer
# [North, West, South, East]
AREA = [37.6, 7.5, 30.0, 12.5]

# ---------------------------------------------------------
# TIGGE request
# ---------------------------------------------------------

dataset = "tigge-forecasts"

request = {
    "origin": "ecmwf",

    "year": "2023",
    "month": "06",
    "day": "01",
    "time": "00:00",

    "level_type": "single_level",

    "variable": [
        "10_m_u_component_of_wind",
        "10_m_v_component_of_wind",
        "2_m_temperature",
        "total_cloud_cover",
    ],

    "forecast_type": "high_resolution_forecast",

    "leadtime_hour": [
        "6",
        "12",
        "24",
        "72",
    ],

    "data_format": "grib",

    "area": AREA,
}

# ---------------------------------------------------------
# Download
# ---------------------------------------------------------

client = cdsapi.Client()

print("Starting TIGGE download...")
print(f"Target: {TARGET_FILE}")

client.retrieve(
    dataset,
    request,
    str(TARGET_FILE),
)

print("\nDownload completed successfully.")
print(f"File: {TARGET_FILE}")
print(f"Size: {TARGET_FILE.stat().st_size / 1024 / 1024:.2f} MB")