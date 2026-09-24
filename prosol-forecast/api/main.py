from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import config
from api.routers import (
    battery,
    districts,
    forecast,
    grid,
    methodology,
    regions,
)


app = FastAPI(
    title="Prosol Forecast API",
    description=(
        "National Intelligent Platform for Forecasting Rooftop Solar Production "
        "in Tunisia. Phase 5.2 (NWP) → Phase 6.2 (Battery) verified pipeline."
    ),
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ROUTERS
# ============================================================

app.include_router(forecast.router)
app.include_router(districts.router)
app.include_router(regions.router)
app.include_router(grid.router)
app.include_router(battery.router)
app.include_router(methodology.router)


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "platform": "Prosol Forecast",
        "phase": "5.2 → 6.2 verified",
    }


@app.get("/")
def root():
    return {
        "name": "Prosol Forecast API",
        "docs": "/docs",
        "health": "/api/health",
    }