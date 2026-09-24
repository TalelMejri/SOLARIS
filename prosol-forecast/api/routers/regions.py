from fastapi import APIRouter, Query
import pandas as pd

from api.models.schemas import RegionListResponse, RegionSnapshot
from api.services import data_loader

router = APIRouter(prefix="/api/regions", tags=["regions"])


@router.get("")
def regions_snapshot(
    horizon: str = Query("h12", pattern="^(h12|h24|h72)$"),
    timestamp: str = Query("2022-07-01T12:00:00+00:00"),
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
        / "regional_quantile_mw.parquet"
    )

    if not file.exists():
        raise HTTPException(404, "Regional quantile file not found")

    df = pd.read_parquet(file)
    df["forecast_valid_time_utc"] = pd.to_datetime(
        df["forecast_valid_time_utc"], utc=True
    )

    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")

    sub = df[(df["horizon"] == horizon) & (df["forecast_valid_time_utc"] == ts)]

    if sub.empty:
        available = df[df["horizon"] == horizon]["forecast_valid_time_utc"]
        nearest = available.iloc[(available - ts).abs().argmin()]
        sub = df[
            (df["horizon"] == horizon) & (df["forecast_valid_time_utc"] == nearest)
        ]
        ts = nearest

    return {
        "timestamp": ts.isoformat(),
        "horizon": horizon,
        "regions": [
            {
                "region_id": int(row["region_id"]),
                "region_name": row["region_name"],
                "capacity_mw": float(row["capacity_mw"]),
                "forecast_mw": float(row["regional_mw_p50"]),
                "regional_mw_true": float(row["regional_mw_true"]),
            }
            for _, row in sub.iterrows()
        ],
    }


@router.get("/quantile")
def regions_quantile(
    horizon: str = Query("h12", pattern="^(h12|h24|h72)$"),
    timestamp: str = Query("2022-07-01T12:00:00+00:00"),
):
    """Regional P10/P50/P90 quantile forecast."""
    import pandas as pd
    from pathlib import Path
    from fastapi import HTTPException

    file = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "processed"
        / "ml"
        / "phase53"
        / "regional_quantile_mw.parquet"
    )

    if not file.exists():
        raise HTTPException(404, "Regional quantile file not found")

    df = pd.read_parquet(file)
    df["forecast_valid_time_utc"] = pd.to_datetime(
        df["forecast_valid_time_utc"], utc=True
    )

    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")

    sub = df[(df["horizon"] == horizon) & (df["forecast_valid_time_utc"] == ts)]

    if sub.empty:
        available = df[df["horizon"] == horizon]["forecast_valid_time_utc"]
        nearest = available.iloc[(available - ts).abs().argmin()]
        sub = df[
            (df["horizon"] == horizon) & (df["forecast_valid_time_utc"] == nearest)
        ]
        ts = nearest

    return {
        "timestamp": ts.isoformat(),
        "horizon": horizon,
        "regions": [
            {
                "region_id": int(row["region_id"]),
                "region_name": row["region_name"],
                "capacity_mw": float(row["capacity_mw"]),
                "regional_mw_p10": float(row.get("regional_mw_p10", 0)),
                "regional_mw_p50": float(row.get("regional_mw_p50", 0)),
                "regional_mw_p90": float(row.get("regional_mw_p90", 0)),
                "regional_mw_true": float(row.get("regional_mw_true", 0)),
                "n_districts": int(row.get("n_districts", 0)),
            }
            for _, row in sub.iterrows()
        ],
    }
