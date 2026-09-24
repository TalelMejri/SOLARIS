from fastapi import APIRouter, Query
from typing import Literal
from datetime import datetime, timezone

router = APIRouter(prefix="/api/forecast", tags=["forecast"])

Horizon = Literal["h12", "h24", "h72"]


@router.get("/national")
def national_timeline(horizon: Horizon = Query("h12")):
    """
    Return the 24-hour national timeline used by the dashboard map.

    Replace `query_national_timeline` with your real model call.
    Expected output shape (all lists same length):
      hours     : [0, 0.25, 0.5, ..., 24]
      load_mw   : grid load at each hour
      pv_mw     : national rooftop PV output
      pv_lo_mw  : lower uncertainty bound (e.g. 92%)
      pv_hi_mw  : upper uncertainty bound (e.g. 108%)
    """
    rows = query_national_timeline(horizon=horizon)
    return {
        "horizon": horizon,
        "hours": [r.hour for r in rows],
        "load_mw": [r.load_mw for r in rows],
        "pv_mw": [r.pv_mw for r in rows],
        "pv_lo_mw": [r.pv_lo_mw for r in rows],
        "pv_hi_mw": [r.pv_hi_mw for r in rows],
    }


def query_national_timeline(horizon: str):
    """
    TODO: replace with a real query against your forecast table.

    Example SQLAlchemy version:
        return (
            db.query(ForecastHour)
            .filter(ForecastHour.horizon == horizon)
            .order_by(ForecastHour.hour)
            .all()
        )
    """
    from types import SimpleNamespace

    out = []
    for i in range(97):  # 0 → 24 in 0.25 steps
        h = i / 4
        t = max(0.0, min(1.0, (h - 6) / 14))
        import math

        shape = math.sin(t * math.pi) if 6 <= h <= 20 else 0
        load = 2800 + 1500 * math.sin(((h - 3) / 18) * math.pi)
        pv = 800 * shape
        out.append(
            SimpleNamespace(
                hour=h,
                load_mw=load,
                pv_mw=pv,
                pv_lo_mw=pv * 0.92,
                pv_hi_mw=pv * 1.08,
            )
        )
    return out


@router.get("/national/quantile")
def national_quantile(
    horizon: str = Query("h12", pattern="^(h12|h24|h72)$"),
    start: str = Query("2022-07-01"),
    end: str = Query("2022-07-05"),
):
    import pandas as pd
    from pathlib import Path
    from fastapi import HTTPException

    file = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "processed"
        / "ml"
        / "phase53"
        / "national_quantile_mw.parquet"
    )

    if not file.exists():
        raise HTTPException(404, "National quantile aggregation not found")

    df = pd.read_parquet(file)
    df["forecast_valid_time_utc"] = pd.to_datetime(
        df["forecast_valid_time_utc"], utc=True
    )

    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")

    sub = df[
        (df["horizon"] == horizon)
        & (df["forecast_valid_time_utc"] >= start_ts)
        & (df["forecast_valid_time_utc"] < end_ts)
    ].sort_values("forecast_valid_time_utc")

    if sub.empty:
        raise HTTPException(404, "No data for given window")

    return {
        "horizon": horizon,
        "window_start": start_ts.isoformat(),
        "window_end": end_ts.isoformat(),
        "points": [
            {
                "time": row["forecast_valid_time_utc"].isoformat(),
                "national_p10": float(row["national_mw_p10_calibrated"]),
                "national_p50": float(row["national_mw_p50"]),
                "national_p90": float(row["national_mw_p90_calibrated"]),
                "national_true": float(row["national_mw_true"]),
                "capacity_mw": float(row["capacity_mw"]),
            }
            for _, row in sub.iterrows()
        ],
    }
