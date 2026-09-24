from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]

IMPORTANCE_FILE = (
    PROJECT_ROOT
    / "data" / "processed" / "ml" / "phase52"
    / "phase52_nwp_feature_importance.csv"
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "ml" / "phase52"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# LOAD
# ============================================================

print("=" * 80)
print("STEP 18 — FEATURE IMPORTANCE ANALYSIS")
print("=" * 80)

imp = pd.read_csv(IMPORTANCE_FILE)

NWP_FEATURES = [
    "nwp_temperature_2m_c",
    "nwp_wind_speed_10m_ms",
    "nwp_wind_direction_10m_deg",
    "nwp_cloud_cover_fraction",
]


# ============================================================
# TOP 20 FEATURES PER HORIZON
# ============================================================

for h in ["h12", "h24", "h72"]:
    print()
    print("=" * 80)
    print(f"TOP 20 FEATURES — {h.upper()}")
    print("=" * 80)

    sub = imp[imp["horizon"] == h].sort_values("importance", ascending=False)
    total = sub["importance"].sum()

    print()
    print(f"{'Rank':<6} {'Feature':<40} {'Importance':>14} {'Share %':>10}")
    print("-" * 75)
    for i, (_, row) in enumerate(sub.head(20).iterrows(), 1):
        share = 100 * row["importance"] / total
        marker = " ← NWP" if row["feature"] in NWP_FEATURES else ""
        print(
            f"{i:<6} {row['feature']:<40} "
            f"{row['importance']:>14.0f} {share:>9.2f}%{marker}"
        )


# ============================================================
# NWP FEATURES RANK PER HORIZON
# ============================================================

print()
print("=" * 80)
print("NWP FEATURE RANKS PER HORIZON")
print("=" * 80)

print()
print(f"{'Feature':<40} {'H+12':>8} {'H+24':>8} {'H+72':>8}")
print("-" * 70)

for feat in NWP_FEATURES:
    ranks = []
    for h in ["h12", "h24", "h72"]:
        sub = imp[imp["horizon"] == h].sort_values("importance", ascending=False)
        rank = sub[sub["feature"] == feat].index[0] - sub.index[0] + 1
        ranks.append(rank)
    print(f"{feat:<40} {ranks[0]:>8} {ranks[1]:>8} {ranks[2]:>8}")


# ============================================================
# NWP SHARE PER HORIZON
# ============================================================

print()
print("=" * 80)
print("NWP SHARE OF TOTAL IMPORTANCE")
print("=" * 80)
print()
print(f"{'Horizon':<10} {'NWP Share %':>14} {'Safe Share %':>14}")
print("-" * 45)

for h in ["h12", "h24", "h72"]:
    sub = imp[imp["horizon"] == h]
    total = sub["importance"].sum()
    nwp_share = 100 * sub[sub["feature"].isin(NWP_FEATURES)]["importance"].sum() / total
    safe_share = 100 - nwp_share
    print(f"H+{h[1:]:<8} {nwp_share:>13.2f}% {safe_share:>13.2f}%")


print()
print("=" * 80)
print("STEP 18 COMPLETE")
print("=" * 80)