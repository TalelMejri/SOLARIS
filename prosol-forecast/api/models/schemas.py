from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ============================================================
# FORECAST
# ============================================================

class ForecastPoint(BaseModel):
    time: datetime
    national_mw: float
    capacity_mw: float


class ForecastResponse(BaseModel):
    horizon: str
    window_start: datetime
    window_end: datetime
    points: list[ForecastPoint]


# ============================================================
# DISTRICT
# ============================================================

class DistrictSnapshot(BaseModel):
    district_id: int
    district_name: str
    region_id: int
    region_name: str
    latitude: float
    longitude: float
    capacity_mw: float
    forecast_mw: float
    forecast_normalized: float


class DistrictListResponse(BaseModel):
    timestamp: datetime
    horizon: str
    districts: list[DistrictSnapshot]


# ============================================================
# REGION
# ============================================================

class RegionSnapshot(BaseModel):
    region_id: int
    region_name: str
    capacity_mw: float
    forecast_mw: float
    n_districts: int


class RegionListResponse(BaseModel):
    timestamp: datetime
    horizon: str
    regions: list[RegionSnapshot]


# ============================================================
# GRID IMPACT
# ============================================================

class GridImpactResponse(BaseModel):
    diurnal_swing_mw: float
    mean_peak_mw: float
    max_peak_mw: float
    std_peak_mw: float
    reserve_proxy_mw: float
    note: str


# ============================================================
# BATTERY
# ============================================================

class BatteryConfig(BaseModel):
    capacity_mwh: float
    max_charge_mw: float
    max_discharge_mw: float
    round_trip_efficiency: float
    soc_min: float
    soc_max: float


class BatteryPoint(BaseModel):
    time: datetime
    soc: float
    charged_mwh: float
    discharged_mwh: float
    net_grid_mw: float


class BatteryResponse(BaseModel):
    config: BatteryConfig
    points: list[BatteryPoint]
    total_charged_mwh: float
    total_discharged_mwh: float
    peak_reduction_mw: float
    peak_reduction_pct: float


# ============================================================
# METHODOLOGY
# ============================================================

class Phase52Results(BaseModel):
    baseline: dict
    nwp: dict
    improvement_pct: dict
    districts_improved: int
    districts_total: int
    nwp_source: str
    verification: str