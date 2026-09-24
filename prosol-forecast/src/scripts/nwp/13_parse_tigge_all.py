"""
TIGGE GRIB -> 50 district NWP forecasts (Phase 5.2, step 13)

Usage:
    python extract_tigge_districts.py --inspect path\to\file.grib   # show GRIB structure
    python extract_tigge_districts.py --limit 2                     # dry run on 2 files (nothing saved)
    python extract_tigge_districts.py                               # full run

Key fixes vs. the previous version:
  * Uses the REAL issue time from the GRIB `time` dimension (not the 1st of the month)
  * Handles ensemble members (`number`): mean + spread (*_ens_std)
  * district_id travels with the data as a coordinate (no np.tile ordering assumption)
  * Per-file row-count sanity check
  * valid_time cross-check (valid == issue + lead)
  * Handles both 00Z and 12Z runs (filename suffix _00 or _12)
"""

from pathlib import Path
import argparse
import re
import json
import warnings

import cfgrib
import numpy as np
import pandas as pd
import xarray as xr

warnings.filterwarnings(
    "ignore",
    message=".*default value for compat.*",
    category=FutureWarning,
)


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

GRIB_DIR = PROJECT_ROOT / "data" / "raw" / "nwp" / "tigge"

DISTRICT_COORDS_FILE = PROJECT_ROOT / "data" / "reference" / "district_coordinates.csv"
DISTRICT_MAPPING_FILE = PROJECT_ROOT / "data" / "reference" / "district_region_mapping.csv"

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "nwp"
OUTPUT_FILE = OUTPUT_DIR / "tigge_district_forecasts.parquet"
MAPPING_OUTPUT_FILE = OUTPUT_DIR / "tigge_district_grid_mapping.csv"
REPORT_FILE = OUTPUT_DIR / "tigge_district_parse_report.json"


# ============================================================
# EXPECTED TIGGE CONFIGURATION
# ============================================================

EXPECTED_LEADS = {6, 12, 24, 72}
EXPECTED_VARIABLES = ("t2m", "u10", "v10", "tcc")
N_DISTRICTS = 50

KEYS = [
    "district_id",
    "forecast_issue_time_utc",
    "forecast_valid_time_utc",
    "forecast_lead_hours",
]


# ============================================================
# HELPERS
# ============================================================

def find_column(df, candidates, required=True):
    normalized = {str(c).strip().lower(): c for c in df.columns}

    for candidate in candidates:
        key = candidate.strip().lower()
        if key in normalized:
            return normalized[key]

    if required:
        raise ValueError(
            f"Could not find any of these columns: {candidates}\n"
            f"Available columns: {list(df.columns)}"
        )
    return None


def load_districts():
    """Load the 50 Prosol districts (+ optional region info)."""

    if not DISTRICT_COORDS_FILE.exists():
        raise FileNotFoundError(f"Missing district coordinates file:\n{DISTRICT_COORDS_FILE}")

    coords = pd.read_csv(DISTRICT_COORDS_FILE)

    id_col = find_column(coords, ["district_id", "id"])
    name_col = find_column(coords, ["district_name", "name"])
    lat_col = find_column(coords, ["latitude", "lat"])
    lon_col = find_column(coords, ["longitude", "lon", "lng"])

    districts = pd.DataFrame(
        {
            "district_id": coords[id_col],
            "district_name": coords[name_col],
            "latitude": pd.to_numeric(coords[lat_col], errors="coerce"),
            "longitude": pd.to_numeric(coords[lon_col], errors="coerce"),
        }
    )

    if DISTRICT_MAPPING_FILE.exists():
        mapping = pd.read_csv(DISTRICT_MAPPING_FILE)
        map_id_col = find_column(mapping, ["district_id", "id"])

        extra = pd.DataFrame({"district_id": mapping[map_id_col]})

        for target in ("region_id", "region_name"):
            col = find_column(mapping, [target], required=False)
            if col is not None:
                extra[target] = mapping[col]

        extra = extra.drop_duplicates(subset=["district_id"])
        districts = districts.merge(extra, on="district_id", how="left")

    for col in ("region_id", "region_name"):
        if col not in districts.columns:
            districts[col] = np.nan

    districts = districts.drop_duplicates(subset=["district_id"]).reset_index(drop=True)

    if len(districts) != N_DISTRICTS:
        raise ValueError(f"Expected {N_DISTRICTS} districts, found {len(districts)}")

    if districts[["latitude", "longitude"]].isna().any().any():
        raise ValueError("District coordinates contain missing values.")

    return districts


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0088
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def open_grib(path):
    return cfgrib.open_datasets(str(path), backend_kwargs={"indexpath": ""})


def close_all(datasets):
    for ds in datasets:
        try:
            ds.close()
        except Exception:
            pass


def build_grid_mapping(ds, districts):
    """Nearest TIGGE grid point (reduced Gaussian, 1D lat/lon) for every district."""

    lat = np.asarray(ds["latitude"].values)
    lon = np.asarray(ds["longitude"].values)

    if not (lat.ndim == 1 and lon.ndim == 1 and lat.shape == lon.shape):
        raise ValueError(
            "Expected a 1D reduced Gaussian grid.\n"
            f"latitude shape={lat.shape}, longitude shape={lon.shape}"
        )

    grid_lat = lat.astype(float)
    grid_lon = lon.astype(float)

    rows = []
    for _, d in districts.iterrows():
        dist = haversine_km(d["latitude"], d["longitude"], grid_lat, grid_lon)
        idx = int(np.argmin(dist))
        rows.append(
            {
                "district_id": d["district_id"],
                "district_name": d["district_name"],
                "latitude": d["latitude"],
                "longitude": d["longitude"],
                "nwp_grid_latitude": grid_lat[idx],
                "nwp_grid_longitude": grid_lon[idx],
                "nwp_distance_km": float(dist[idx]),
                "grid_index": idx,
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# EXTRACTION
# ============================================================

def extract_reduced_grid_points(ds, mapping, variable):
    """Extract ONLY the 50 district grid points (never the whole grid)."""

    lat = np.asarray(ds["latitude"].values)
    lon = np.asarray(ds["longitude"].values)

    if not (lat.ndim == 1 and lon.ndim == 1 and lat.shape == lon.shape):
        raise ValueError("Expected 1D reduced Gaussian grid.")

    spatial_dim = ds["latitude"].dims[0]
    indices = mapping["grid_index"].astype(int).to_numpy()

    selected = ds[variable].isel({spatial_dim: xr.DataArray(indices, dims="district")})

    # district_id travels with the data -> no tile / ordering assumptions
    selected = selected.assign_coords(
        district_id=("district", mapping["district_id"].to_numpy())
    )

    return selected.to_dataframe(name=variable).reset_index()


def normalize_variable_dataframe(df, variable):
    """Use the REAL issue time (`time` column), not the month start."""

    for col in ("time", "step"):
        if col not in df.columns:
            raise ValueError(f"Missing '{col}' column. Columns: {list(df.columns)}")

    if np.issubdtype(df["step"].dtype, np.timedelta64):
        lead_hours = (df["step"] / pd.Timedelta(hours=1)).round().astype(int)
    else:
        lead_hours = pd.to_numeric(df["step"]).round().astype(int)

    out = pd.DataFrame(
        {
            "district_id": df["district_id"].to_numpy(),
            "forecast_issue_time_utc": pd.to_datetime(df["time"]).dt.tz_localize("UTC"),
            "forecast_lead_hours": lead_hours,
            "number": df["number"].to_numpy() if "number" in df.columns else 0,
            variable: df[variable].to_numpy(),
        },
        index=df.index,
    )

    out = out[out["forecast_lead_hours"].isin(EXPECTED_LEADS)].copy()

    out["forecast_valid_time_utc"] = (
        out["forecast_issue_time_utc"]
        + pd.to_timedelta(out["forecast_lead_hours"], unit="h")
    )

    # Cross-check against the valid_time coordinate cfgrib provides
    if "valid_time" in df.columns:
        vt = pd.to_datetime(df.loc[out.index, "valid_time"]).dt.tz_localize("UTC")
        mismatch = (vt - out["forecast_valid_time_utc"]).ne(pd.Timedelta(0)).sum()
        if mismatch > 0:
            raise ValueError(
                f"{variable}: {mismatch} rows where valid_time != issue_time + lead"
            )

    return out


def collapse_members(frame, variable):
    """Collapse ensemble members -> mean (+ spread). Fail loudly on real duplicates."""

    if frame["number"].nunique() > 1:
        g = frame.groupby(KEYS)[variable]
        res = g.mean().rename(variable).to_frame()
        res[f"{variable}_ens_std"] = g.std()
        return res.reset_index()

    frame = frame.drop(columns="number")

    if frame.duplicated(KEYS).any():
        raise ValueError(
            f"{variable}: duplicate keys remain (extra dimension in the GRIB?). "
            "Run with --inspect on this file."
        )

    return frame


def extract_variable(datasets, mapping, variable):
    """A variable can live in several cfgrib datasets (e.g. control + perturbed)."""

    parts = []
    for ds in datasets:
        if variable in ds.data_vars:
            raw = extract_reduced_grid_points(ds, mapping, variable)
            parts.append(normalize_variable_dataframe(raw, variable))

    if not parts:
        raise ValueError(f"Variable {variable} not found in GRIB")

    return collapse_members(pd.concat(parts, ignore_index=True), variable)


def parse_one_grib(path, mapping):
    datasets = open_grib(path)

    try:
        frames = {v: extract_variable(datasets, mapping, v) for v in EXPECTED_VARIABLES}

        result = frames["t2m"]
        for v in ("u10", "v10", "tcc"):
            result = result.merge(frames[v], on=KEYS, how="inner", validate="one_to_one")

        # Derived variables
        result["temperature_2m_c"] = result["t2m"] - 273.15
        result["wind_speed_10m_ms"] = np.sqrt(result["u10"] ** 2 + result["v10"] ** 2)
        result["wind_direction_10m_deg"] = (
            np.degrees(np.arctan2(-result["u10"], -result["v10"])) + 360.0
        ) % 360.0
        result["cloud_cover_fraction"] = result["tcc"].clip(lower=0.0, upper=1.0)

        result = result.drop(columns=["t2m", "tcc"])

        # District + grid metadata
        meta_cols = [c for c in mapping.columns if c != "grid_index"]
        result = result.merge(
            mapping[meta_cols], on="district_id", how="left", validate="many_to_one"
        )

        columns = [
            "forecast_issue_time_utc",
            "forecast_valid_time_utc",
            "forecast_lead_hours",
            "district_id",
            "district_name",
            "region_id",
            "region_name",
            "latitude",
            "longitude",
            "nwp_grid_latitude",
            "nwp_grid_longitude",
            "nwp_distance_km",
            "temperature_2m_c",
            "u10",
            "v10",
            "wind_speed_10m_ms",
            "wind_direction_10m_deg",
            "cloud_cover_fraction",
            "t2m_ens_std",
            "u10_ens_std",
            "v10_ens_std",
            "tcc_ens_std",
        ]
        result = result[[c for c in columns if c in result.columns]]

        return (
            result.sort_values(
                ["forecast_issue_time_utc", "forecast_lead_hours", "district_id"]
            ).reset_index(drop=True)
        )

    finally:
        close_all(datasets)


def validate_file_frame(df):
    leads = set(df["forecast_lead_hours"].unique().tolist())
    if leads != EXPECTED_LEADS:
        raise ValueError(f"Expected leads {sorted(EXPECTED_LEADS)}, found {sorted(leads)}")

    n_districts = df["district_id"].nunique()
    if n_districts != N_DISTRICTS:
        raise ValueError(f"Expected {N_DISTRICTS} districts, found {n_districts}")

    n_days = df["forecast_issue_time_utc"].nunique()
    expected_rows = n_days * len(EXPECTED_LEADS) * N_DISTRICTS
    if len(df) != expected_rows:
        raise ValueError(
            f"Row count {len(df)} != expected {expected_rows} "
            f"({n_days} issue times x {len(EXPECTED_LEADS)} leads x {N_DISTRICTS} districts)"
        )

    dups = df.duplicated(subset=KEYS).sum()
    if dups > 0:
        raise ValueError(f"{dups} duplicate district forecast records")

    if not df["cloud_cover_fraction"].between(0, 1).all():
        raise ValueError("Cloud cover outside [0,1]")
    if not df["wind_speed_10m_ms"].between(0, 100).all():
        raise ValueError("Invalid wind speed")
    if not df["wind_direction_10m_deg"].between(0, 360).all():
        raise ValueError("Invalid wind direction")

    required = [
        "temperature_2m_c",
        "u10",
        "v10",
        "wind_speed_10m_ms",
        "wind_direction_10m_deg",
        "cloud_cover_fraction",
    ]
    missing = int(df[required].isna().sum().sum())
    if missing > 0:
        raise ValueError(f"{missing} missing meteorological values")

    return n_days, n_districts, sorted(leads)


# ============================================================
# INSPECT MODE
# ============================================================

def inspect_grib(path):
    datasets = open_grib(path)
    print(f"{path}\n{len(datasets)} cfgrib dataset(s)\n")

    for i, ds in enumerate(datasets):
        print(f"--- dataset {i}")
        print(f"    data_vars: {list(ds.data_vars)}")
        print(f"    sizes    : {dict(ds.sizes)}")
        print(f"    coords   : {list(ds.coords)}")

    close_all(datasets)


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", type=Path, help="Print the structure of one GRIB and exit")
    parser.add_argument("--limit", type=int, default=None, help="Dry run on the first N files (nothing saved)")
    args = parser.parse_args()

    if args.inspect:
        inspect_grib(args.inspect)
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("TIGGE -> 50 DISTRICT NWP EXTRACTION")
    print("=" * 80)
    print(f"GRIB directory : {GRIB_DIR}")
    print(f"District file  : {DISTRICT_COORDS_FILE}")

    districts = load_districts()
    print(f"\nDistricts loaded: {len(districts)}")

    files = sorted(GRIB_DIR.glob("ecmwf_tigge_*.grib"))
    print(f"GRIB files found: {len(files)}")

    if not files:
        raise FileNotFoundError("No TIGGE GRIB files found.")

    if len(files) not in (118, 119):
        print(
            "WARNING: expected 118-119 files "
            "(59 x 00Z + 59-60 x 12Z, February 2019 excluded for 00Z)."
        )
        print(f"Found: {len(files)}")

    dry_run = args.limit is not None
    if dry_run:
        files = files[: args.limit]
        print(f"DRY RUN: only {len(files)} file(s), nothing will be saved.")

    # --------------------------------------------------------
    # Grid mapping (from first file)
    # --------------------------------------------------------
    print("\n" + "=" * 80)
    print("BUILDING TIGGE GRID -> DISTRICT MAPPING")
    print("=" * 80)

    datasets = open_grib(files[0])
    try:
        mapping_ds = next(
            (ds for ds in datasets if "latitude" in ds.coords and "longitude" in ds.coords),
            None,
        )
        if mapping_ds is None:
            raise RuntimeError("No GRIB dataset with latitude/longitude found.")
        mapping = build_grid_mapping(mapping_ds, districts)
    finally:
        close_all(datasets)

    region_cols = [c for c in ("region_id", "region_name") if c in districts.columns]
    mapping = mapping.merge(
        districts[["district_id"] + region_cols], on="district_id", how="left"
    )

    mapping.to_csv(MAPPING_OUTPUT_FILE, index=False)
    print(f"\nMapping saved: {MAPPING_OUTPUT_FILE}")
    print("\nNearest-grid distance statistics (km):")
    print(mapping["nwp_distance_km"].describe())

    # --------------------------------------------------------
    # Parse files
    # --------------------------------------------------------
    print("\n" + "=" * 80)
    print("PARSING TIGGE FILES")
    print("=" * 80)

    all_frames = []
    failed_files = []

    for i, path in enumerate(files, start=1):
        print(f"\n[{i:02d}/{len(files):02d}] {path.name}")

        try:
            df = parse_one_grib(path, mapping)
            n_days, n_districts, leads = validate_file_frame(df)

            print(
                f"    OK rows={len(df):,} issue_times={n_days} "
                f"districts={n_districts} leads={leads}"
            )
            all_frames.append(df)

        except Exception as exc:
            failed_files.append({"file": path.name, "error": str(exc)})
            print(f"    FAILED: {exc}")

    successful = len(all_frames)
    failed = len(failed_files)

    if failed > 0:
        report = {
            "status": "FAILED",
            "total_files": len(files),
            "successful_files": successful,
            "failed_files": failed,
            "failed": failed_files,
        }
        if not dry_run:
            with open(REPORT_FILE, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)

        print("\n" + "=" * 80)
        print("EXTRACTION FAILED")
        print("=" * 80)
        print(f"Successful: {successful}")
        print(f"Failed:     {failed}")
        raise RuntimeError("At least one TIGGE file failed.")

    # --------------------------------------------------------
    # Combine + global validation
    # --------------------------------------------------------
    print("\n" + "=" * 80)
    print("COMBINING DISTRICT DATA")
    print("=" * 80)

    data = pd.concat(all_frames, ignore_index=True)

    dup_count = int(data.duplicated(subset=KEYS).sum())
    if dup_count > 0:
        raise RuntimeError(f"{dup_count:,} duplicate district forecast records found.")

    data = data.sort_values(
        ["forecast_issue_time_utc", "forecast_lead_hours", "district_id"]
    ).reset_index(drop=True)

    print(f"Total rows   : {len(data):,}")
    print(f"Districts    : {data['district_id'].nunique()}")
    print(f"Lead times   : {sorted(data['forecast_lead_hours'].unique())}")
    print(f"Issue times  : {data['forecast_issue_time_utc'].nunique():,}")
    print(f"Valid times  : {data['forecast_valid_time_utc'].nunique():,}")
    print(f"Duplicates   : {dup_count:,}")

    print("\nMissing values:")
    for column, count in data.isna().sum().items():
        if count > 0:
            print(f"  {column}: {count:,}")

    # --------------------------------------------------------
    # Daylight check: which UTC hours does each lead land on?
    # --------------------------------------------------------
    valid_hour = data["forecast_valid_time_utc"].dt.hour
    hours_by_lead = {
        int(lead): sorted(int(h) for h in valid_hour[data["forecast_lead_hours"] == lead].unique())
        for lead in sorted(data["forecast_lead_hours"].unique())
    }

    print("\nValid UTC hours per lead:")
    for lead, hours in hours_by_lead.items():
        print(f"  H+{lead:<3d} -> {hours}")
        if not any(5 <= h <= 17 for h in hours):
            print(
                f"  WARNING: H+{lead} is valid only at night (UTC hours {hours}). "
                "PV target will be ~all zeros. Add 12 UTC runs or more steps."
            )

    if dry_run:
        print("\nDRY RUN complete. Nothing saved.")
        return

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------
    print("\n" + "=" * 80)
    print("SAVING")
    print("=" * 80)

    data.to_parquet(OUTPUT_FILE, index=False)

    report = {
        "status": "PASSED",
        "grib_files_found": len(files),
        "successful_files": successful,
        "failed_files": failed,
        "district_count": int(data["district_id"].nunique()),
        "total_rows": int(len(data)),
        "unique_issue_times": int(data["forecast_issue_time_utc"].nunique()),
        "unique_valid_times": int(data["forecast_valid_time_utc"].nunique()),
        "lead_times": [int(x) for x in sorted(data["forecast_lead_hours"].unique())],
        "valid_utc_hours_by_lead": {str(k): v for k, v in hours_by_lead.items()},
        "ensemble_spread_columns": [c for c in data.columns if c.endswith("_ens_std")],
        "mapping_distance_km": {
            "min": float(mapping["nwp_distance_km"].min()),
            "mean": float(mapping["nwp_distance_km"].mean()),
            "median": float(mapping["nwp_distance_km"].median()),
            "max": float(mapping["nwp_distance_km"].max()),
        },
        "excluded_period": {
            "period": "2019-02",
            "reason": "TIGGE archive unavailable due to damaged MARS tape J0018900",
        },
        "output_file": str(OUTPUT_FILE),
        "mapping_file": str(MAPPING_OUTPUT_FILE),
    }

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 80)
    print("TIGGE DISTRICT EXTRACTION COMPLETE")
    print("=" * 80)
    print(f"Rows     : {len(data):,}")
    print(f"Dataset  : {OUTPUT_FILE}")
    print(f"Mapping  : {MAPPING_OUTPUT_FILE}")
    print(f"Report   : {REPORT_FILE}")


if __name__ == "__main__":
    main()