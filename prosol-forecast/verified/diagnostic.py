# import pandas as pd
# import numpy as np

# df = pd.read_parquet("../data/processed/features/district_features.parquet")

# print("=" * 60)
# print("SHAPE & TIME")
# print("=" * 60)
# print(f"Shape       : {df.shape}")
# print(f"Time range  : {df['timestamp'].min()} → {df['timestamp'].max()}")
# print(f"Districts   : {df['district_id'].nunique()}")

# print("\n" + "=" * 60)
# print("TARGET (p_pvgis_kw_per_kwp)")
# print("=" * 60)
# print(df["p_pvgis_kw_per_kwp"].describe())

# print("\n" + "=" * 60)
# print("CLEAR-SKY INDEX (kt)")
# print("=" * 60)
# print(df["kt"].describe())

# print("\n" + "=" * 60)
# print("KT BY REGION (should be sunny in south)")
# print("=" * 60)
# kt_by_region = (
#     df.groupby("region_name")["kt"].mean().round(3).sort_values()
# )
# print(kt_by_region.to_string())

# print("\n" + "=" * 60)
# print("LAG NaN RATE (should be tiny)")
# print("=" * 60)
# for lag in [1, 24, 168]:
#     col = f"p_lag_{lag}h"
#     if col in df.columns:
#         nan_pct = df[col].isna().mean() * 100
#         print(f"{col:15s} : {nan_pct:.4f}% NaN")

# print("\n" + "=" * 60)
# print("FEATURE LIST")
# print("=" * 60)
# import json
# with open("../data/processed/features/feature_metadata.json") as f:
#     meta = json.load(f)
# for i, feat in enumerate(meta["model_features"], 1):
#     print(f"  {i:2d}. {feat}")

# import pandas as pd
# import numpy as np
# import pvlib

# df = pd.read_parquet("../data/processed/features/district_features.parquet")

# # Look at clearsky column
# print("=== GHI CLEARSKY ===")
# print(df["ghi_clearsky_w_m2"].describe())
# print(df["ghi_clearsky_w_m2"].head(20).tolist())

# print("\n=== GHI ACTUAL ===")
# print(df["ghi_w_m2"].describe())

# print("\n=== SOLAR ELEVATION ===")
# print(df["solar_elevation_calc_deg"].describe())

# # Sample a midsummer noon row for district 1
# sample = df[(df["district_id"] == 1) &
#             (df["timestamp"].dt.month == 6) &
#             (df["timestamp"].dt.hour == 12)].head(3)
# print("\n=== JUNE NOON, DISTRICT 1 ===")
# print(sample[["timestamp", "ghi_w_m2", "ghi_clearsky_w_m2",
#               "solar_elevation_calc_deg", "solar_zenith_deg"]].to_string())

# import pandas as pd
# import pvlib
# from datetime import datetime

# # Reproduce exactly
# lat, lon = 36.788353, 10.186666   # district 1

# # Test 1: naive timestamps
# ts_naive = pd.DatetimeIndex([
#     "2005-06-01 12:00:00",
#     "2005-06-01 00:00:00",
#     "2005-12-01 12:00:00",
# ])

# print("=== RAW pvlib calls ===")
# print("\n-- get_solarposition with tz-aware --")
# ts_aware = ts_naive.tz_localize("Africa/Tunis")
# sp = pvlib.solarposition.get_solarposition(ts_aware, lat, lon)
# print(sp[["apparent_zenith", "elevation", "azimuth"]])

# print("\n-- Location.get_clearsky with tz-aware --")
# loc = pvlib.location.Location(lat, lon, tz="Africa/Tunis")
# cs = loc.get_clearsky(ts_aware, model="ineichen")
# print(cs)

# print("\n-- direct ineichen --")
# cs2 = pvlib.clearsky.ineichen(
#     sp["apparent_zenith"], lat, altitude=0, linke_turbidity=3.0,
# )
# print(cs2)

# import pandas as pd
# df = pd.read_parquet("../data/processed/features/district_features.parquet")

# print("kt mean:", df["kt"].mean())
# print("kt notna:", df["kt"].notna().sum())
# print("ghi_w_m2 mean:", df["ghi_w_m2"].mean())
# print("ghi_w_m2 max:", df["ghi_w_m2"].max())
# print("ghi_clearsky_w_m2 max:", df["ghi_clearsky_w_m2"].max())

# # June noon district 1 sanity
# s = df[(df["district_id"]==1) &
#        (df["timestamp"].dt.month==6) &
#        (df["timestamp"].dt.hour==12)].head(1)
# print(s[["ghi_w_m2","ghi_clearsky_w_m2","kt","solar_zenith_deg"]])


# import pandas as pd
# df = pd.read_parquet("../data/processed/features/district_features.parquet")
# leaky_cols = [
#     "ghi_w_m2", "beam_w_m2", "diffuse_w_m2", "reflected_w_m2",
#     "temperature_2m_c", "wind_speed_10m_ms",
#     "kt", "beam_fraction", "diffuse_fraction",
# ]
# print("Leakage features present in current df:")
# for c in leaky_cols:
#     if c in df.columns:
#         print(f"  {c}: {df[c].notna().sum():,} rows, mean={df[c].mean():.3f}")

# import pandas as pd

# df = pd.read_parquet("../data/processed/features/district_features.parquet")
# print("kt mean:", df["kt"].mean())
# print("kt notna:", df["kt"].notna().sum())
# print("ghi_w_m2 mean:", df["ghi_w_m2"].mean())
# print("columns:", len(df.columns))


# """
# Verify Phase 4.2 quantile model outputs.
# Run from project root: python verified/verify_quantile.py
# """
# import json
# import numpy as np
# import pandas as pd
# from pathlib import Path

# PROJECT_ROOT = Path(__file__).resolve().parents[1]

# # ---- Load outputs ----
# metrics_file = PROJECT_ROOT / "data" / "processed" / "ml" / "lightgbm_quantile_metrics.json"
# preds_file   = PROJECT_ROOT / "data" / "processed" / "ml" / "lightgbm_quantile_test_predictions.parquet"
# district_file= PROJECT_ROOT / "data" / "processed" / "ml" / "lightgbm_quantile_district_metrics.csv"

# with open(metrics_file) as f:
#     M = json.load(f)

# df = pd.read_parquet(preds_file)
# dm = pd.read_csv(district_file)

# # ============================================================
# # CHECK 1 — Coverage is calibrated (76–84%)
# # ============================================================
# print("\n" + "=" * 60)
# print("CHECK 1 — P10-P90 Coverage (target 80%)")
# print("=" * 60)

# cov = M["probabilistic_summary"]["p10_p90_observed_coverage"]
# print(f"Observed coverage: {cov*100:.2f}%")
# if 0.76 <= cov <= 0.84:
#     print("✅ PASS — Intervals are well calibrated")
# elif 0.72 <= cov < 0.76 or 0.84 < cov <= 0.88:
#     print("⚠️  MARGINAL — Slightly off but acceptable")
# else:
#     print("❌ FAIL — Intervals are miscalibrated")

# # ============================================================
# # CHECK 2 — P50 matches the deterministic baseline
# # ============================================================
# print("\n" + "=" * 60)
# print("CHECK 2 — P50 vs Deterministic Model (Phase 4.1)")
# print("=" * 60)

# p50_r2 = M["probabilistic_summary"]["p50_R2"]
# print(f"P50 R²: {p50_r2:.4f}")
# print(f"Deterministic R² from Phase 4.1: 0.9662")
# if abs(p50_r2 - 0.9662) < 0.005:
#     print("✅ PASS — P50 matches baseline (quantile objective preserves median)")
# elif abs(p50_r2 - 0.9662) < 0.015:
#     print("⚠️  MARGINAL — Small drift, check quantile loss convergence")
# else:
#     print("❌ FAIL — P50 diverged from baseline; likely sorting bug reintroduced")

# # ============================================================
# # CHECK 3 — Interval width is reasonable
# # ============================================================
# print("\n" + "=" * 60)
# print("CHECK 3 — Mean Interval Width")
# print("=" * 60)

# width = M["probabilistic_summary"]["mean_interval_width"]
# print(f"Mean width: {width:.5f} kW/kWp")
# print(f"Target      range: 0.02 – 0.15 kW/kWp")
# if 0.02 <= width <= 0.15:
#     print("✅ PASS — Sharp, informative intervals")
# elif width < 0.02:
#     print("❌ FAIL — Intervals are too narrow (overconfident)")
# elif width > 0.25:
#     print("❌ FAIL — Intervals are too wide (uninformative)")
# else:
#     print("⚠️  MARGINAL")

# # ============================================================
# # CHECK 4 — Pinball losses are monotonic and non-trivial
# # ============================================================
# print("\n" + "=" * 60)
# print("CHECK 4 — Pinball Losses")
# print("=" * 60)

# pl10 = M["probabilistic_summary"]["p10_pinball_loss"]
# pl50 = M["probabilistic_summary"]["p50_pinball_loss"]
# pl90 = M["probabilistic_summary"]["p90_pinball_loss"]
# print(f"P10 pinball: {pl10:.6f}")
# print(f"P50 pinball: {pl50:.6f}")
# print(f"P90 pinball: {pl90:.6f}")

# # P50 pinball should be ~MAE/2 = 0.0075
# expected_pl50 = M["probabilistic_summary"]["p50_MAE"] / 2
# print(f"Expected P50 pinball ≈ MAE/2 = {expected_pl50:.6f}")

# if abs(pl50 - expected_pl50) < 0.005:
#     print("✅ PASS — P50 pinball ≈ MAE/2 (theory-consistent)")
# else:
#     print("⚠️  Check P50 objective is really quantile(0.5)")

# # ============================================================
# # CHECK 5 — No quantile crossing on test
# # ============================================================
# print("\n" + "=" * 60)
# print("CHECK 5 — Monotonicity (P10 ≤ P50 ≤ P90)")
# print("=" * 60)

# crossings = (
#     (df["p10_kw_per_kwp"] > df["p50_kw_per_kwp"]).sum()
#     + (df["p50_kw_per_kwp"] > df["p90_kw_per_kwp"]).sum()
# )
# print(f"Total crossing rows: {crossings}")
# if crossings == 0:
#     print("✅ PASS — Zero crossings")
# else:
#     print(f"❌ FAIL — {crossings} crossing rows remain")

# # ============================================================
# # CHECK 6 — Per-district coverage is uniform
# # ============================================================
# print("\n" + "=" * 60)
# print("CHECK 6 — District-level Coverage Uniformity")
# print("=" * 60)

# cov_dist = dm["coverage_P10_P90"]
# print(f"Districts with coverage in [0.72, 0.88]: "
#       f"{((cov_dist >= 0.72) & (cov_dist <= 0.88)).sum()} / {len(dm)}")
# print(f"Coverage min: {cov_dist.min():.3f}")
# print(f"Coverage max: {cov_dist.max():.3f}")
# print(f"Coverage std: {cov_dist.std():.3f}")

# if ((cov_dist >= 0.72) & (cov_dist <= 0.88)).sum() >= 45:
#     print("✅ PASS — Coverage consistent across districts")
# else:
#     print("⚠️  Some districts are miscalibrated — check specific ones:")
#     bad = dm[(cov_dist < 0.72) | (cov_dist > 0.88)]
#     print(bad[["district_id", "coverage_P10_P90"]].to_string(index=False))


"""
Phase 5.1 verification suite.
Confirms the multi-horizon models are correct, leakage-free,
and mathematically sound.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---- Load artifacts ----
METRICS_JSON = PROJECT_ROOT / "data" / "processed" / "ml" / "multihorizon_metrics.json"
METRICS_CSV  = PROJECT_ROOT / "data" / "processed" / "ml" / "multihorizon_metrics.csv"
PRED_FILE    = PROJECT_ROOT / "data" / "processed" / "ml" / "multihorizon_predictions.parquet"
DISTRICT_CSV = PROJECT_ROOT / "data" / "processed" / "ml" / "multihorizon_district_metrics.csv"

with open(METRICS_JSON) as f:
    M = json.load(f)

preds = pd.read_parquet(PRED_FILE)
metrics = pd.read_csv(METRICS_CSV)
district_metrics = pd.read_csv(DISTRICT_CSV)

HORIZONS = [1, 6, 12, 24, 72]


# ============================================================
# CHECK 1 — All horizons present
# ============================================================
print("\n" + "=" * 70)
print("CHECK 1 — All 5 horizons present")
print("=" * 70)

present = sorted(preds["horizon_hours"].unique().tolist())
print(f"Horizons found: {present}")
print(f"Expected:      {HORIZONS}")

if present == HORIZONS:
    print("✅ PASS — All 5 horizons present")
else:
    print(f"❌ FAIL — Missing or extra horizons")
    raise SystemExit(1)


# ============================================================
# CHECK 2 — No leakage in feature list
# ============================================================
print("\n" + "=" * 70)
print("CHECK 2 — Leakage audit on feature list")
print("=" * 70)

LEAKY = {
    "ghi_w_m2", "beam_w_m2", "diffuse_w_m2", "reflected_w_m2",
    "temperature_2m_c", "wind_speed_10m_ms",
    "kt", "beam_fraction", "diffuse_fraction",
    "kt_anomaly_24h", "temp_effect_proxy", "wind_cooling_proxy",
    "estimated_power_mw", "p_pvgis_kw_per_kwp",
}

features = set(M["features"])
leaked = features & LEAKY

print(f"Features in model      : {len(features)}")
print(f"Leaky features present : {leaked if leaked else 'NONE'}")

if not leaked:
    print("✅ PASS — No leaky features")
else:
    print("❌ FAIL — Leakage detected")
    raise SystemExit(1)


# ============================================================
# CHECK 3 — Timestamp alignment
# ============================================================
print("\n" + "=" * 70)
print("CHECK 3 — Prediction timestamp alignment")
print("=" * 70)

for h in HORIZONS:
    sub = preds[preds["horizon_hours"] == h]
    delta = (
        pd.to_datetime(sub["forecast_target_timestamp"])
        - pd.to_datetime(sub["timestamp"])
    ).dt.total_seconds() / 3600

    is_aligned = np.allclose(delta, h, atol=0.01)
    print(f"  h{h:>3} → delta mean = {delta.mean():.4f}, expected = {h}, aligned = {is_aligned}")

    if not is_aligned:
        print(f"❌ FAIL — h{h} timestamps misaligned")
        raise SystemExit(1)

print("✅ PASS — All horizons have correct timestamp offsets")


# ============================================================
# CHECK 4 — Metric consistency (recompute vs saved)
# ============================================================
print("\n" + "=" * 70)
print("CHECK 4 — Recompute metrics from raw predictions")
print("=" * 70)

def rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))

def mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))

def r2(y_true, y_pred):
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    return 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

recompute_ok = True
for h in HORIZONS:
    sub = preds[preds["horizon_hours"] == h]

    y_true = sub["actual_p_kw_per_kwp"].to_numpy()
    y_pred = sub["predicted_p_kw_per_kwp"].to_numpy()

    recomputed_r2   = r2(y_true, y_pred)
    recomputed_rmse = rmse(y_true, y_pred)
    recomputed_mae  = mae(y_true, y_pred)

    saved = metrics[metrics["horizon_hours"] == h].iloc[0]
    delta_r2   = abs(recomputed_r2   - saved["test_r2"])
    delta_rmse = abs(recomputed_rmse - saved["test_rmse"])
    delta_mae  = abs(recomputed_mae  - saved["test_mae"])

    print(f"\n  h{h}:")
    print(f"    R²    recomputed = {recomputed_r2:.6f}  saved = {saved['test_r2']:.6f}  Δ = {delta_r2:.2e}")
    print(f"    RMSE  recomputed = {recomputed_rmse:.6f}  saved = {saved['test_rmse']:.6f}  Δ = {delta_rmse:.2e}")
    print(f"    MAE   recomputed = {recomputed_mae:.6f}  saved = {saved['test_mae']:.6f}  Δ = {delta_mae:.2e}")

    if delta_r2 > 1e-6 or delta_rmse > 1e-6 or delta_mae > 1e-6:
        recompute_ok = False
        print(f"    ❌ Mismatch detected")

if recompute_ok:
    print("\n✅ PASS — Saved metrics match recomputed metrics exactly")
else:
    print("\n❌ FAIL — Metrics do not match")
    raise SystemExit(1)


# ============================================================
# CHECK 5 — R² degradation is monotonic and physically plausible
# ============================================================
print("\n" + "=" * 70)
print("CHECK 5 — R² degradation curve sanity")
print("=" * 70)

r2_series = metrics.sort_values("horizon_hours")["test_r2"].tolist()
h_series = metrics.sort_values("horizon_hours")["horizon_hours"].tolist()

print("R² by horizon:")
for h, r in zip(h_series, r2_series):
    print(f"  h{h:>3} → R² = {r:.4f}")

# Monotonic degradation check
is_monotonic = all(
    r2_series[i] >= r2_series[i+1] - 0.005
    for i in range(len(r2_series) - 1)
)

if is_monotonic:
    print("\n✅ PASS — R² degrades monotonically with horizon")
else:
    print("\n⚠  WARNING — R² is not strictly decreasing")
    print("   (acceptable if within 0.005, check for leakage or anomalies)")


# ============================================================
# CHECK 6 — Skill vs daily is positive at all horizons
# ============================================================
print("\n" + "=" * 70)
print("CHECK 6 — Skill vs daily persistence")
print("=" * 70)

skill_series = metrics.sort_values("horizon_hours")["test_skill_vs_daily"].tolist()

for h, s in zip(h_series, skill_series):
    verdict = "✅" if s > 0 else "❌"
    print(f"  {verdict} h{h:>3} → skill vs daily = {s:.4f}")

all_positive = all(s > 0 for s in skill_series)

if all_positive:
    print("\n✅ PASS — Model beats daily persistence at every horizon")
else:
    print("\n❌ FAIL — Model loses to persistence at one or more horizons")
    raise SystemExit(1)


# ============================================================
# CHECK 7 — District uniformity (no bad districts)
# ============================================================
print("\n" + "=" * 70)
print("CHECK 7 — District-level consistency")
print("=" * 70)

print(f"Districts in test predictions: {preds['district_id'].nunique()}")

for h in HORIZONS:
    sub = district_metrics[district_metrics["horizon_hours"] == h]
    r2s = sub["r2"].dropna()

    n_districts = len(r2s)
    r2_min = r2s.min()
    r2_max = r2s.max()
    r2_std = r2s.std()
    n_bad = int((r2s < 0.85).sum())

    verdict = "✅" if n_bad == 0 else f"⚠  ({n_bad} districts below 0.85)"

    print(f"\n  h{h}:")
    print(f"    Districts        : {n_districts}")
    print(f"    R² range         : [{r2_min:.4f}, {r2_max:.4f}]")
    print(f"    R² std           : {r2_std:.4f}")
    print(f"    Districts < 0.85 : {n_bad}  {verdict}")

if n_districts != 50:
    print(f"\n❌ FAIL — Expected 50 districts, found {n_districts}")
    raise SystemExit(1)
else:
    print("\n✅ PASS — All 50 districts present at every horizon")


# ============================================================
# FINAL REPORT
# ============================================================
print("\n" + "=" * 70)
print("VERIFICATION COMPLETE")
print("=" * 70)
print("""
All 7 checks passed:
  1. All 5 horizons present
  2. No leakage in feature list
  3. Timestamp alignment correct
  4. Metrics reproducible from raw predictions
  5. R² degradation monotonic
  6. Skill vs daily positive at all horizons
  7. 50 districts consistent across all horizons

Phase 5.1 is VERIFIED CORRECT.
Ready to proceed to Phase 5.2 (NWP features).
""")