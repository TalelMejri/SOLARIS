from pathlib import Path
import json

import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

PHASE53_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ml"
    / "phase53"
)

NATIONAL_FILE = PHASE53_DIR / "national_mw_predictions.parquet"

OUTPUT_DIR = PHASE53_DIR
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BATTERY_FILE = OUTPUT_DIR / "battery_simulation.parquet"
SUMMARY_FILE = OUTPUT_DIR / "phase62_battery_summary.json"


# ============================================================
# BATTERY CONFIG (configurable)
# ============================================================

BATTERY_CONFIG = {
    "capacity_mwh": 100.0,
    "max_charge_mw": 30.0,
    "max_discharge_mw": 30.0,
    "round_trip_efficiency": 0.88,
    "soc_min": 0.10,
    "soc_max": 0.90,
    "initial_soc": 0.50,
}


# ============================================================
# LOAD NATIONAL FORECAST
# ============================================================

print("=" * 80)
print("STEP 22 — PHASE 6.2 BATTERY DECISION SUPPORT")
print("=" * 80)

national = pd.read_parquet(NATIONAL_FILE)
national["forecast_valid_time_utc"] = pd.to_datetime(
    national["forecast_valid_time_utc"], utc=True
)

print()
print(f"Rows: {len(national):,}")
print(f"Horizons: {sorted(national['horizon'].unique())}")

print()
print("Battery configuration:")
for k, v in BATTERY_CONFIG.items():
    print(f"  {k}: {v}")


# ============================================================
# SIMULATION
# ============================================================

def simulate_battery(pv_series, config):
    """
    Simulate a battery on a PV time series.

    For each time step:
      - If PV > baseline, charge the battery (up to max_charge)
      - If PV < baseline, discharge to serve load
      - Track SOC

    This is a decision-support simulation, not actual STEG operation.
    """
    capacity = config["capacity_mwh"]
    max_charge = config["max_charge_mw"]
    max_discharge = config["max_discharge_mw"]
    rte = config["round_trip_efficiency"]
    soc_min = config["soc_min"]
    soc_max = config["soc_max"]
    initial_soc = config["initial_soc"]

    n = len(pv_series)
    soc = np.zeros(n)
    charged = np.zeros(n)
    discharged = np.zeros(n)
    curtailed = np.zeros(n)
    net_grid = np.zeros(n)

    current_soc = initial_soc * capacity
    soc_min_energy = soc_min * capacity
    soc_max_energy = soc_max * capacity

    daytime_pv = pv_series[pv_series > 0]
    baseline = daytime_pv.mean() if len(daytime_pv) > 0 else 0

    for i in range(n):
        pv = pv_series.iloc[i] if hasattr(pv_series, "iloc") else pv_series[i]
        net = pv - baseline

        if net > 0:
            charge_amount = min(net, max_charge)
            energy_available = charge_amount
            energy_stored = energy_available * np.sqrt(rte)
            headroom = soc_max_energy - current_soc
            actual_stored = min(energy_stored, headroom)

            current_soc += actual_stored
            charged[i] = actual_stored
            curtailed[i] = max(0, energy_available - actual_stored)
            net_grid[i] = pv - actual_stored

        else:
            discharge_amount = min(-net, max_discharge)
            energy_needed = discharge_amount
            energy_drawn = energy_needed / np.sqrt(rte)
            available = current_soc - soc_min_energy
            actual_drawn = min(energy_drawn, available)

            current_soc -= actual_drawn
            discharged[i] = actual_drawn * np.sqrt(rte)
            net_grid[i] = pv + discharged[i]

        soc[i] = current_soc / capacity

    return pd.DataFrame({
        "soc": soc,
        "charged_mwh": charged,
        "discharged_mwh": discharged,
        "curtailed_mwh": curtailed,
        "net_grid_mw": net_grid,
        "baseline_mw": baseline,
    })


# ============================================================
# RUN SIMULATION PER HORIZON
# ============================================================

print()
print("=" * 80)
print("BATTERY SIMULATION RESULTS")
print("=" * 80)

all_results = []
summary = {}

for h in ["h12", "h24", "h72"]:
    print()
    print(f"=== {h.upper()} ===")

    sub = national[national["horizon"] == h].copy()
    sub = sub.sort_values("forecast_valid_time_utc").reset_index(drop=True)

    sim = simulate_battery(sub["national_mw"], BATTERY_CONFIG)

    sub = pd.concat([sub, sim], axis=1)
    sub["horizon"] = h
    all_results.append(sub)

    total_charged = float(sim["charged_mwh"].sum())
    total_discharged = float(sim["discharged_mwh"].sum())
    total_curtailed = float(sim["curtailed_mwh"].sum())
    cycles_equiv = total_discharged / BATTERY_CONFIG["capacity_mwh"]

    mean_soc = float(sim["soc"].mean())
    min_soc = float(sim["soc"].min())
    max_soc = float(sim["soc"].max())

    original_peak = float(sub["national_mw"].max())
    net_peak = float(sim["net_grid_mw"].max())
    peak_reduction = original_peak - net_peak
    peak_reduction_pct = 100 * peak_reduction / original_peak if original_peak > 0 else 0

    summary[h] = {
        "total_charged_mwh": total_charged,
        "total_discharged_mwh": total_discharged,
        "total_curtailed_mwh": total_curtailed,
        "cycles_equivalent": float(cycles_equiv),
        "mean_soc": mean_soc,
        "min_soc": min_soc,
        "max_soc": max_soc,
        "original_peak_mw": original_peak,
        "net_peak_mw": net_peak,
        "peak_reduction_mw": float(peak_reduction),
        "peak_reduction_pct": float(peak_reduction_pct),
    }

    print(f"  Total charged:       {total_charged:>10.2f} MWh")
    print(f"  Total discharged:    {total_discharged:>10.2f} MWh")
    print(f"  Total curtailed:     {total_curtailed:>10.2f} MWh")
    print(f"  Equivalent cycles:   {cycles_equiv:>10.2f}")
    print(f"  Mean SOC:            {mean_soc:>10.2%}")
    print(f"  Min SOC:             {min_soc:>10.2%}")
    print(f"  Max SOC:             {max_soc:>10.2%}")
    print(f"  Original peak:       {original_peak:>10.2f} MW")
    print(f"  Net grid peak:       {net_peak:>10.2f} MW")
    print(f"  Peak reduction:      {peak_reduction:>10.2f} MW ({peak_reduction_pct:.1f}%)")


# ============================================================
# SAVE
# ============================================================

print()
print("=" * 80)
print("SAVING")
print("=" * 80)

battery_df = pd.concat(all_results, ignore_index=True)
battery_df.to_parquet(BATTERY_FILE, index=False)
print(f"Saved: {BATTERY_FILE}")

final_summary = {
    "phase": "6.2",
    "battery_config": BATTERY_CONFIG,
    "simulation_disclaimer": (
        "This is a decision-support simulation. Results do not represent "
        "actual STEG battery operations or infrastructure."
    ),
    "per_horizon": summary,
}

with open(SUMMARY_FILE, "w") as f:
    json.dump(final_summary, f, indent=2)

print(f"Summary: {SUMMARY_FILE}")

print()
print("=" * 80)
print("STEP 22 COMPLETE — PHASE 6.2 BATTERY DECISION SUPPORT DONE")
print("=" * 80)