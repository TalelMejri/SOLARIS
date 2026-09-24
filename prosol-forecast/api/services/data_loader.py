import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from api import config


# ============================================================
# PARQUET LOADERS (cached at process start)
# ============================================================

@lru_cache(maxsize=1)
def load_district_predictions() -> pd.DataFrame:
    df = pd.read_parquet(config.DISTRICT_MW_FILE)
    df["forecast_issue_time_utc"] = pd.to_datetime(
        df["forecast_issue_time_utc"], utc=True
    )
    df["forecast_valid_time_utc"] = pd.to_datetime(
        df["forecast_valid_time_utc"], utc=True
    )
    return df


@lru_cache(maxsize=1)
def load_regional_predictions() -> pd.DataFrame:
    df = pd.read_parquet(config.REGIONAL_MW_FILE)
    df["forecast_issue_time_utc"] = pd.to_datetime(
        df["forecast_issue_time_utc"], utc=True
    )
    df["forecast_valid_time_utc"] = pd.to_datetime(
        df["forecast_valid_time_utc"], utc=True
    )
    return df


@lru_cache(maxsize=1)
def load_national_predictions() -> pd.DataFrame:
    df = pd.read_parquet(config.NATIONAL_MW_FILE)
    df["forecast_issue_time_utc"] = pd.to_datetime(
        df["forecast_issue_time_utc"], utc=True
    )
    df["forecast_valid_time_utc"] = pd.to_datetime(
        df["forecast_valid_time_utc"], utc=True
    )
    return df


@lru_cache(maxsize=1)
def load_battery_simulation() -> pd.DataFrame:
    df = pd.read_parquet(config.BATTERY_FILE)
    df["forecast_valid_time_utc"] = pd.to_datetime(
        df["forecast_valid_time_utc"], utc=True
    )
    return df


@lru_cache(maxsize=1)
def load_district_coordinates() -> pd.DataFrame:
    return pd.read_csv(config.DISTRICT_COORDS_FILE)


# ============================================================
# JSON LOADERS
# ============================================================

@lru_cache(maxsize=1)
def load_grid_impact() -> dict:
    with open(config.GRID_IMPACT_FILE) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_battery_summary() -> dict:
    with open(config.BATTERY_SUMMARY_FILE) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_phase52_results() -> dict:
    with open(config.PHASE52_RESULTS_FILE) as f:
        return json.load(f)