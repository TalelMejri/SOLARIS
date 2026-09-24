from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data" / "processed" / "ml" / "phase53"

DISTRICT_MW_FILE = DATA_DIR / "district_mw_predictions.parquet"
REGIONAL_MW_FILE = DATA_DIR / "regional_mw_predictions.parquet"
NATIONAL_MW_FILE = DATA_DIR / "national_mw_predictions.parquet"
BATTERY_FILE = DATA_DIR / "battery_simulation.parquet"
GRID_IMPACT_FILE = DATA_DIR / "phase61_grid_impact_summary.json"
BATTERY_SUMMARY_FILE = DATA_DIR / "phase62_battery_summary.json"

# Quantile aggregation (Phase 5.3)
NATIONAL_QUANTILE_FILE = DATA_DIR / "national_quantile_mw.parquet"
REGIONAL_QUANTILE_FILE = DATA_DIR / "regional_quantile_mw.parquet"
DISTRICT_QUANTILE_FILE = DATA_DIR / "district_quantile_mw.parquet"

# Phase 5.2 comparison
PHASE52_RESULTS_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase52"
    / "phase51r_vs_phase52.json"
)

# Calibrated quantile predictions
PHASE52_QUANTILE_CALIBRATED = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase52"
    / "phase52_quantile_predictions_calibrated.parquet"
)

# District coordinates
DISTRICT_COORDS_FILE = (
    PROJECT_ROOT / "data" / "reference" / "district_coordinates.csv"
)

# CORS — allow both Vite (5173) and Next.js (3000)
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
]