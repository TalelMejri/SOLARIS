from fastapi import APIRouter, Query
import pandas as pd

from api.models.schemas import BatteryConfig, BatteryPoint, BatteryResponse
from api.services import data_loader

router = APIRouter(prefix="/api/battery", tags=["battery"])


@router.get("/simulation")
def battery_simulation(
    horizon: str = Query("h12", pattern="^(h12|h24|h72)$"),
):
    """Battery decision support — peak reduction and SOC summary."""
    import json
    from pathlib import Path
    from fastapi import HTTPException

    summary_file = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "processed"
        / "ml"
        / "phase53"
        / "phase62_battery_summary.json"
    )

    if not summary_file.exists():
        raise HTTPException(404, "Battery simulation not found")

    with open(summary_file) as f:
        summary = json.load(f)

    h_summary = summary["per_horizon"][horizon]

    return {
        "horizon": horizon,
        "peak_reduction_mw": h_summary["peak_reduction_mw"],
        "peak_reduction_pct": h_summary["peak_reduction_pct"],
        "total_charged_mwh": h_summary["total_charged_mwh"],
        "total_discharged_mwh": h_summary["total_discharged_mwh"],
        "mean_soc": h_summary["mean_soc"],
    }
