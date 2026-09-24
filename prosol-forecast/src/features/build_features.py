"""
PHASE 3.1 — Leakage-safe feature engineering for PV forecasting.

INPUT:
    data/processed/prosol_pvgis/district_hourly_production.csv

OUTPUT:
    data/processed/features/district_features.parquet
    data/processed/features/feature_metadata.json

TARGET:
    p_pvgis_kw_per_kwp

NO:
    - synthetic data
    - interpolation
    - current-target leakage
    - future-target leakage
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import pvlib

# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "prosol_pvgis"
    / "district_hourly_production.csv"
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "features"
OUTPUT_FILE = OUTPUT_DIR / "district_features.parquet"
METADATA_FILE = OUTPUT_DIR / "feature_metadata.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# CONFIG
# ============================================================

TARGET = "p_pvgis_kw_per_kwp"
EXPECTED_DISTRICTS = 50
TIMEZONE = "Africa/Tunis"

LAGS = [1, 2, 3, 6, 12, 24, 48, 168]
ROLLING_WINDOWS = [3, 6, 24]


# ============================================================
# LOAD + VALIDATE
# ============================================================


def load_data():
    print("\nLoading source data...")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"""
Input file not found:

{INPUT_FILE}

Make sure Phase 2.4 has been completed.
""")

    df = pd.read_csv(INPUT_FILE)
    if df.empty:
        raise ValueError("Input dataset is empty.")

    required_columns = [
        "district_id",
        "district_name",
        "region_id",
        "region_name",
        "timestamp",
        TARGET,
        "latitude",
        "longitude",
        "capacity_mw",
        "ghi_w_m2",
        "beam_w_m2",
        "diffuse_w_m2",
        "reflected_w_m2",
        "temperature_2m_c",
        "wind_speed_10m_ms",
    ]
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="raise")
    df["district_id"] = pd.to_numeric(df["district_id"], errors="raise").astype(int)

    df = df.sort_values(["district_id", "timestamp"]).reset_index(drop=True)
    return df


def validate_data(df):
    print("\nValidating source data...")

    districts = df["district_id"].nunique()
    print(f"  Rows       : {len(df):,}")
    print(f"  Districts  : {districts}")
    print(f"  Start      : {df['timestamp'].min()}")
    print(f"  End        : {df['timestamp'].max()}")

    if districts != EXPECTED_DISTRICTS:
        raise ValueError(f"Expected {EXPECTED_DISTRICTS} districts, found {districts}")

    dups = df.duplicated(subset=["district_id", "timestamp"]).sum()
    if dups > 0:
        raise ValueError(f"Found {dups:,} duplicate district/timestamp rows.")

    neg = (df[TARGET].dropna() < 0).sum()
    if neg > 0:
        raise ValueError(f"Found {neg:,} negative target values.")


# ============================================================
# SOLAR GEOMETRY — Location.get_clearsky (physically correct)
# ============================================================


def add_solar_geometry(df):
    print("\nCreating solar geometry...")

    # 1. Snap to hour, dedupe
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.round("h")
    dup = df.duplicated(subset=["district_id", "timestamp"], keep="first")
    if dup.sum() > 0:
        print(f"  Dropped {dup.sum():,} rows from rounding.")
        df = df[~dup].reset_index(drop=True)

    # 2. Unique timestamps (naive local)
    unique_ts_naive = pd.DatetimeIndex(sorted(df["timestamp"].unique()))

    # 3. Localize safely (DST-aware)
    ts_local = unique_ts_naive.tz_localize(
        TIMEZONE, ambiguous="NaT", nonexistent="shift_forward"
    )
    valid_mask = ts_local.notna()
    ts_valid_local = ts_local[valid_mask]
    ts_valid_naive = unique_ts_naive[valid_mask]

    if (~valid_mask).sum() > 0:
        print(f"  Dropped {(~valid_mask).sum()} DST-ambiguous timestamps")

    # 4. Per-district solar geometry
    district_meta = (
        df.groupby("district_id")[["latitude", "longitude"]].first().reset_index()
    )
    print(f"  Computing solar position for {len(district_meta)} districts...")
    print(f"  Unique valid timestamps: {len(ts_valid_local):,}")

    chunks = []
    for _, row in district_meta.iterrows():
        did = int(row["district_id"])
        lat = float(row["latitude"])
        lon = float(row["longitude"])

        sp = pvlib.solarposition.get_solarposition(ts_valid_local, lat, lon)
        loc = pvlib.location.Location(latitude=lat, longitude=lon, tz=TIMEZONE)
        cs = loc.get_clearsky(ts_valid_local, model="ineichen")

        chunk = pd.DataFrame(
            {
                "district_id": did,
                "timestamp": ts_valid_naive.values,
                "solar_zenith_deg": sp["apparent_zenith"].values,
                "solar_azimuth_deg": sp["azimuth"].values,
                "solar_elevation_calc_deg": (90 - sp["apparent_zenith"]).values,
                "ghi_clearsky_w_m2": cs["ghi"].values,
                "dni_clearsky_w_m2": cs["dni"].values,
                "dhi_clearsky_w_m2": cs["dhi"].values,
            }
        )
        chunks.append(chunk)

    solar = pd.concat(chunks, ignore_index=True)

    cs_max = float(solar["ghi_clearsky_w_m2"].max())
    cs_mean = float(solar["ghi_clearsky_w_m2"].mean())
    print(f"  GHI clearsky max : {cs_max:.2f} W/m²")
    print(f"  GHI clearsky mean: {cs_mean:.2f} W/m²")
    print(f"  GHI clearsky NaN : {solar['ghi_clearsky_w_m2'].isna().sum()}")

    if cs_max < 800 or cs_max > 1300:
        raise ValueError(f"GHI clearsky max = {cs_max:.2f}. Expected 800–1300 W/m².")

    # 5. Merge
    overlap = [
        c
        for c in solar.columns
        if c in df.columns and c not in ("district_id", "timestamp")
    ]
    if overlap:
        df = df.drop(columns=overlap)

    df = df.merge(
        solar,
        on=["district_id", "timestamp"],
        how="left",
        validate="one_to_one",
    )
    return df


# ============================================================
# IRRADIANCE FEATURES (kt, beam/diffuse fractions)
# ============================================================


def add_irradiance_features(df):
    print("\nCreating irradiance features...")

    ghi = pd.to_numeric(df["ghi_w_m2"], errors="coerce")
    beam = pd.to_numeric(df["beam_w_m2"], errors="coerce")
    diffuse = pd.to_numeric(df["diffuse_w_m2"], errors="coerce")
    clear_ghi = pd.to_numeric(df["ghi_clearsky_w_m2"], errors="coerce")

    print("\n  Irradiance diagnostics:")
    print(f"    GHI valid       : {ghi.notna().sum():,}")
    print(f"    GHI > 0         : {(ghi > 0).sum():,}")
    print(f"    Clear GHI valid : {clear_ghi.notna().sum():,}")
    print(f"    Clear GHI > 10  : {(clear_ghi > 10).sum():,}")
    print(f"    GHI mean        : {ghi.mean():.3f}")
    print(f"    GHI max         : {ghi.max():.3f}")
    print(f"    Clear GHI max   : {clear_ghi.max():.3f}")

    # ---- Clear-sky index ----
    valid_kt = ghi.notna() & clear_ghi.notna() & (ghi >= 0) & (clear_ghi > 10)
    kt = pd.Series(np.nan, index=df.index, dtype="float64")
    kt.loc[valid_kt] = ghi.loc[valid_kt] / clear_ghi.loc[valid_kt]
    kt.loc[(kt < 0) | (kt > 1.5)] = np.nan
    df["kt"] = kt.astype("float32")

    # ---- Beam fraction ----
    beam_fraction = pd.Series(np.nan, index=df.index, dtype="float64")
    valid_beam = ghi.notna() & beam.notna() & (ghi > 10)
    beam_fraction.loc[valid_beam] = beam.loc[valid_beam] / ghi.loc[valid_beam]
    df["beam_fraction"] = beam_fraction.clip(0, 1).astype("float32")

    # ---- Diffuse fraction ----
    diffuse_fraction = pd.Series(np.nan, index=df.index, dtype="float64")
    valid_diffuse = ghi.notna() & diffuse.notna() & (ghi > 10)
    diffuse_fraction.loc[valid_diffuse] = (
        diffuse.loc[valid_diffuse] / ghi.loc[valid_diffuse]
    )
    df["diffuse_fraction"] = diffuse_fraction.clip(0, 1).astype("float32")

    # ---- Daylight flag ----
    df["is_daylight"] = (df["solar_elevation_calc_deg"] > 0).astype("int8")

    valid_count = int(df["kt"].notna().sum())
    print("\n  KT diagnostics:")
    print(f"    kt valid : {valid_count:,}")
    print(f"    kt mean  : {df['kt'].mean():.6f}")
    print(f"    kt max   : {df['kt'].max():.6f}")
    print(f"    kt NaN   : {df['kt'].isna().mean() * 100:.2f}%")

    if valid_count == 0:
        raise ValueError("kt produced ZERO valid rows. Check clearsky merge.")

    return df


# ============================================================
# CALENDAR
# ============================================================


def add_calendar_features(df):
    print("\nCreating calendar features...")
    ts = df["timestamp"]

    df["hour"] = ts.dt.hour.astype("int8")
    df["day_of_week"] = ts.dt.dayofweek.astype("int8")
    df["month"] = ts.dt.month.astype("int8")
    df["day_of_year"] = ts.dt.dayofyear.astype("int16")
    df["week_of_year"] = ts.dt.isocalendar().week.astype("int16")
    df["is_weekend"] = (df["day_of_week"] >= 5).astype("int8")
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24).astype("float32")
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24).astype("float32")
    df["doy_sin"] = np.sin(2 * np.pi * df["day_of_year"] / 365.25).astype("float32")
    df["doy_cos"] = np.cos(2 * np.pi * df["day_of_year"] / 365.25).astype("float32")
    return df


# ============================================================
# LAGS + ROLLING
# ============================================================


def add_lag_features(df):
    print("\nCreating lag features...")
    grouped = df.groupby("district_id", sort=False)
    for lag in LAGS:
        df[f"p_lag_{lag}h"] = grouped[TARGET].shift(lag).astype("float32")
        df[f"kt_lag_{lag}h"] = grouped["kt"].shift(lag).astype("float32")
    return df


def add_rolling_features(df):
    print("\nCreating past-only rolling features...")
    for w in ROLLING_WINDOWS:
        df[f"p_roll_mean_{w}h"] = (
            df.groupby("district_id")[TARGET]
            .transform(lambda s: s.shift(1).rolling(w, min_periods=1).mean())
            .astype("float32")
        )
        df[f"p_roll_std_{w}h"] = (
            df.groupby("district_id")[TARGET]
            .transform(lambda s: s.shift(1).rolling(w, min_periods=2).std())
            .astype("float32")
        )
        df[f"kt_roll_mean_{w}h"] = (
            df.groupby("district_id")["kt"]
            .transform(lambda s: s.shift(1).rolling(w, min_periods=1).mean())
            .astype("float32")
        )
    return df


# ============================================================
# DIFFERENCES (leakage-safe — historical only)
# ============================================================


def add_difference_features(df):
    print("\nCreating leakage-safe difference features...")
    df["p_lag_diff_1h_24h"] = (df["p_lag_1h"] - df["p_lag_24h"]).astype("float32")
    df["p_lag_diff_24h_168h"] = (df["p_lag_24h"] - df["p_lag_168h"]).astype("float32")
    df["kt_lag_diff_1h_24h"] = (df["kt_lag_1h"] - df["kt_lag_24h"]).astype("float32")
    return df


# ============================================================
# SPATIAL HISTORICAL (shift before aggregation)
# ============================================================


def add_spatial_features(df):
    print("\nCreating historical spatial features...")

    history = df[["timestamp", "district_id", "region_id", TARGET, "kt"]].copy()
    history["power_previous"] = history.groupby("district_id")[TARGET].shift(1)
    history["kt_previous"] = history.groupby("district_id")["kt"].shift(1)

    region_power = (
        history.groupby(["timestamp", "region_id"])["power_previous"]
        .mean()
        .reset_index()
        .rename(columns={"power_previous": "region_mean_p_lag"})
    )
    region_kt = (
        history.groupby(["timestamp", "region_id"])["kt_previous"]
        .mean()
        .reset_index()
        .rename(columns={"kt_previous": "region_mean_kt_lag"})
    )
    national_power = (
        history.groupby("timestamp")["power_previous"]
        .mean()
        .reset_index()
        .rename(columns={"power_previous": "national_mean_p_lag"})
    )
    national_kt = (
        history.groupby("timestamp")["kt_previous"]
        .mean()
        .reset_index()
        .rename(columns={"kt_previous": "national_mean_kt_lag"})
    )

    df = df.merge(region_power, on=["timestamp", "region_id"], how="left")
    df = df.merge(region_kt, on=["timestamp", "region_id"], how="left")
    df = df.merge(national_power, on="timestamp", how="left")
    df = df.merge(national_kt, on="timestamp", how="left")

    df["p_dev_from_region"] = (df["p_lag_1h"] - df["region_mean_p_lag"]).astype(
        "float32"
    )

    return df


# ============================================================
# PHYSICAL PROXIES
# ============================================================


def add_physical_features(df):
    print("\nCreating physical features...")
    temperature = pd.to_numeric(df["temperature_2m_c"], errors="coerce")
    wind = pd.to_numeric(df["wind_speed_10m_ms"], errors="coerce")

    df["temp_effect_proxy"] = (temperature - 25.0).astype("float32")
    df["wind_cooling_proxy"] = wind.astype("float32")
    df["kt_anomaly_24h"] = (df["kt"] - df["kt_lag_24h"]).astype("float32")
    return df


# ============================================================
# CLEAN
# ============================================================


def clean_data(df):
    print("\nCleaning...")
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=[TARGET])
    df = df.sort_values(["timestamp", "district_id"]).reset_index(drop=True)
    return df


# ============================================================
# FEATURE LIST
# ============================================================


def get_model_features(df):
    excluded = {
        TARGET,
        "estimated_power_mw",
        "timestamp",
        "district_id",
        "district_name",
        "region_name",
        "latitude",
        "longitude",
        "capacity_mw",
        "capacity_source",
        "pv_reference",
    }
    features = []
    for column in df.columns:
        if column in excluded:
            continue
        if pd.api.types.is_numeric_dtype(df[column]):
            features.append(column)
    return features


# ============================================================
# MAIN
# ============================================================


def main():
    print("=" * 70)
    print("PHASE 3.1 — FEATURE ENGINEERING")
    print("=" * 70)

    df = load_data()
    validate_data(df)

    df = add_solar_geometry(df)
    df = add_irradiance_features(df)
    df = add_calendar_features(df)
    df = add_lag_features(df)
    df = add_rolling_features(df)
    df = add_difference_features(df)
    df = add_spatial_features(df)
    df = add_physical_features(df)
    df = clean_data(df)

    features = get_model_features(df)

    metadata = {
        "phase": "3.1",
        "target": TARGET,
        "rows": int(len(df)),
        "districts": int(df["district_id"].nunique()),
        "time_start": str(df["timestamp"].min()),
        "time_end": str(df["timestamp"].max()),
        "model_features": features,
        "lags": LAGS,
        "rolling_windows": ROLLING_WINDOWS,
        "synthetic_data": False,
        "interpolation": False,
        "current_target_leakage": False,
        "future_target_leakage": False,
    }

    print(f"\nRows          : {len(df):,}")
    print(f"Districts     : {df['district_id'].nunique()}")
    print(f"Time          : {df['timestamp'].min()} → {df['timestamp'].max()}")
    print(f"Features      : {len(features)}")

    print("\nSaving:")
    df.to_parquet(OUTPUT_FILE, index=False, engine="pyarrow")
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("\n" + "=" * 70)
    print("PHASE 3.1 COMPLETE")
    print("=" * 70)
    print(f"\nCreated:")
    print(f"  {OUTPUT_FILE}")
    print(f"  {METADATA_FILE}")


if __name__ == "__main__":
    main()
