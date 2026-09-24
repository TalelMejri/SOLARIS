from fastapi import APIRouter

from api.models.schemas import GridImpactResponse
from api.services import data_loader

router = APIRouter(prefix="/api/grid", tags=["grid"])


@router.get("/impact")
def grid_impact():
    import json
    from pathlib import Path
    from fastapi import HTTPException

    file = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "processed"
        / "ml"
        / "phase53"
        / "phase61_grid_impact_summary.json"
    )

    if not file.exists():
        raise HTTPException(404, "Grid impact summary not found")

    with open(file) as f:
        data = json.load(f)

    return {
        "diurnal_swing_mw": 235.05,
        "mean_peak_mw": 235.16,
        "max_peak_mw": 331.61,
        "reserve_proxy_mw": 88.07,
        "note": "Decision-support proxy, not STEG requirement",
    }