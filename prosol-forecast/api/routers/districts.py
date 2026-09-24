from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
from functools import lru_cache

import pandas as pd

router = APIRouter(prefix="/api/districts", tags=["districts"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]

QUANTILE_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase53"
    / "district_quantile_mw.parquet"
)

POINT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase53"
    / "district_mw_predictions.parquet"
)

COORDS_FILE = (
    PROJECT_ROOT / "data" / "reference" / "district_coordinates.csv"
)

NWP_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "nwp"
    / "tigge_district_forecasts.parquet"
)


@lru_cache(maxsize=1)
def _load_predictions() -> pd.DataFrame:
    file = QUANTILE_FILE if QUANTILE_FILE.exists() else POINT_FILE
    if not file.exists():
        raise FileNotFoundError("District prediction file not found")

    df = pd.read_parquet(file)
    df["forecast_valid_time_utc"] = pd.to_datetime(
        df["forecast_valid_time_utc"], utc=True
    )
    return df


@lru_cache(maxsize=1)
def _load_coords() -> dict[int, tuple[float, float]]:
    if not COORDS_FILE.exists():
        return {}
    out: dict[int, tuple[float, float]] = {}
    coords_df = pd.read_csv(COORDS_FILE)
    for _, crow in coords_df.iterrows():
        try:
            out[int(crow["district_id"])] = (
                float(crow["latitude"]),
                float(crow["longitude"]),
            )
        except (ValueError, TypeError):
            continue
    return out


@lru_cache(maxsize=1)
def _load_nwp() -> pd.DataFrame | None:
    if not NWP_FILE.exists():
        return None
    try:
        nwp = pd.read_parquet(NWP_FILE)
        nwp["forecast_valid_time_utc"] = pd.to_datetime(
            nwp["forecast_valid_time_utc"], utc=True
        )
        return nwp.drop_duplicates(
            subset=["district_id", "forecast_valid_time_utc"]
        )
    except Exception:
        return None


def _pick_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


@router.get("")
def districts_snapshot(
    horizon: str = Query("h12", pattern="^(h12|h24|h72)$"),
    timestamp: str = Query("2022-07-01T12:00:00+00:00"),
):
    try:
        df = _load_predictions()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))

    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")

    sub = df[
        (df["horizon"] == horizon)
        & (df["forecast_valid_time_utc"] == ts)
    ]

    if sub.empty:
        available = df[df["horizon"] == horizon]["forecast_valid_time_utc"]
        if available.empty:
            raise HTTPException(404, f"No data for horizon {horizon}")
        nearest = available.iloc[(available - ts).abs().argmin()]
        sub = df[
            (df["horizon"] == horizon)
            & (df["forecast_valid_time_utc"] == nearest)
        ]
        ts = nearest

    # One row per district
    sub = (
        sub.sort_values("district_id")
        .drop_duplicates(subset=["district_id"], keep="first")
        .reset_index(drop=True)
    )

    mw_p50_col = _pick_column(sub, ["district_mw_p50", "district_mw"])
    mw_p10_col = _pick_column(sub, ["district_mw_p10"])
    mw_p90_col = _pick_column(sub, ["district_mw_p90"])
    norm_p50_col = _pick_column(sub, ["y_pred_p50", "y_pred"])
    cap_col = _pick_column(sub, ["capacity_mw"])

    if mw_p50_col is None:
        raise HTTPException(
            500,
            f"No MW forecast column. Available: {list(sub.columns)}",
        )
    if cap_col is None:
        raise HTTPException(
            500,
            f"No capacity column. Available: {list(sub.columns)}",
        )

    coords_map = _load_coords()
    nwp_df = _load_nwp()

    districts = []

    for _, row in sub.iterrows():
        did = int(row["district_id"])
        lat, lon = coords_map.get(did, (0.0, 0.0))

        capacity_mw = float(row[cap_col]) if pd.notna(row[cap_col]) else 0.0
        raw_p50 = float(row[mw_p50_col]) if pd.notna(row[mw_p50_col]) else 0.0
        raw_p10 = (
            float(row[mw_p10_col])
            if mw_p10_col and pd.notna(row[mw_p10_col])
            else raw_p50
        )
        raw_p90 = (
            float(row[mw_p90_col])
            if mw_p90_col and pd.notna(row[mw_p90_col])
            else raw_p50
        )
        forecast_norm = (
            float(row[norm_p50_col])
            if norm_p50_col and pd.notna(row[norm_p50_col])
            else 0.0
        )

        if capacity_mw > 0:
            if raw_p50 > capacity_mw * 1.001:
                scale = capacity_mw / raw_p50
                raw_p50 *= scale
                raw_p10 *= scale
                raw_p90 *= scale

            p50 = max(0.0, min(raw_p50, capacity_mw))
            p10 = max(0.0, min(raw_p10, p50))
            p90 = max(p50, min(raw_p90, capacity_mw))
        else:
            p50 = max(raw_p50, 0.0)
            p10 = max(raw_p10, 0.0)
            p90 = max(raw_p90, p50)

        utilization = p50 / capacity_mw if capacity_mw > 0 else 0.0

        rec = {
            "district_id": did,
            "district_name": str(row["district_name"]),
            "region_name": str(row.get("region_name", "")),
            "latitude": lat,
            "longitude": lon,
            "capacity_mw": capacity_mw,
            "forecast_mw": p50,
            "forecast_p10": p10,
            "forecast_p90": p90,
            "forecast_normalized": forecast_norm,
            "utilization": utilization,
            "temperature_2m_c": None,
            "wind_speed_10m_ms": None,
            "wind_direction_10m_deg": None,
            "cloud_cover_fraction": None,
        }

        if nwp_df is not None:
            nwp_row = nwp_df[
                (nwp_df["district_id"] == did)
                & (nwp_df["forecast_valid_time_utc"] == ts)
            ]
            if not nwp_row.empty:
                r = nwp_row.iloc[0]
                for key in (
                    "temperature_2m_c",
                    "wind_speed_10m_ms",
                    "wind_direction_10m_deg",
                    "cloud_cover_fraction",
                ):
                    if key in r and pd.notna(r[key]):
                        rec[key] = float(r[key])

        districts.append(rec)

    return {
        "timestamp": ts.isoformat(),
        "horizon": horizon,
        "count": len(districts),
        "districts": districts,
    }
    
@router.get("/quantile")
def districts_quantile_snapshot(
    horizon: str = Query("h12", pattern="^(h12|h24|h72)$"),
    timestamp: str = Query("2022-07-01T12:00:00+00:00"),
):
    """District-level P10/P50/P90 quantile forecast at a specific timestamp."""

    file = QUANTILE_FILE if QUANTILE_FILE.exists() else POINT_FILE
    if not file.exists():
        raise HTTPException(404, "District quantile data not found")

    df = _load_predictions()

    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")

    sub = df[
        (df["horizon"] == horizon)
        & (df["forecast_valid_time_utc"] == ts)
    ]

    if sub.empty:
        available = df[df["horizon"] == horizon]["forecast_valid_time_utc"]
        if available.empty:
            raise HTTPException(404, f"No data for horizon {horizon}")
        nearest = available.iloc[(available - ts).abs().argmin()]
        sub = df[
            (df["horizon"] == horizon)
            & (df["forecast_valid_time_utc"] == nearest)
        ]
        ts = nearest

    sub = (
        sub.sort_values("district_id")
        .drop_duplicates(subset=["district_id"], keep="first")
        .reset_index(drop=True)
    )

    coords_map = _load_coords()
    nwp_df = _load_nwp()

    districts = []
    for _, row in sub.iterrows():
        did = int(row["district_id"])
        lat, lon = coords_map.get(did, (0.0, 0.0))

        capacity = float(row["capacity_mw"]) if pd.notna(row.get("capacity_mw")) else 0.0
        p50 = float(row.get("district_mw_p50", 0) or 0)
        p10 = float(row.get("district_mw_p10", p50) or p50)
        p90 = float(row.get("district_mw_p90", p50) or p50)

        # Clamp to physics
        if capacity > 0:
            if p50 > capacity:
                scale = capacity / p50
                p50 *= scale
                p10 *= scale
                p90 *= scale
            p50 = max(0.0, min(p50, capacity))
            p10 = max(0.0, min(p10, p50))
            p90 = max(p50, min(p90, capacity))

        norm_p50 = float(row.get("y_pred_p50", 0) or 0)

        rec = {
            "district_id": did,
            "district_name": str(row["district_name"]),
            "region_name": str(row.get("region_name", "")),
            "latitude": lat,
            "longitude": lon,
            "capacity_mw": capacity,
            "forecast_p10": p10,
            "forecast_p50": p50,
            "forecast_p90": p90,
            "forecast_normalized": norm_p50,
            "utilization": p50 / capacity if capacity > 0 else 0.0,
            "temperature_2m_c": None,
            "wind_speed_10m_ms": None,
            "cloud_cover_fraction": None,
        }

        if nwp_df is not None:
            nwp_row = nwp_df[
                (nwp_df["district_id"] == did)
                & (nwp_df["forecast_valid_time_utc"] == ts)
            ]
            if not nwp_row.empty:
                r = nwp_row.iloc[0]
                for key in (
                    "temperature_2m_c",
                    "wind_speed_10m_ms",
                    "cloud_cover_fraction",
                ):
                    if key in r and pd.notna(r[key]):
                        rec[key] = float(r[key])

        districts.append(rec)

    return {
        "timestamp": ts.isoformat(),
        "horizon": horizon,
        "count": len(districts),
        "districts": districts,
    }