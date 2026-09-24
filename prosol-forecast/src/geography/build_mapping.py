"""
municipality → Prosol district mapping
Every municipality is assigned. No UNMAPPED rows.
"""

import pandas as pd
import re
import unicodedata
import math
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"

MUNI_FILE = REFERENCE_DIR / "municipalities.csv"
DIST_FILE = REFERENCE_DIR / "district_region_mapping.csv"
OUT_FILE = REFERENCE_DIR / "municipality_district_mapping.csv"


def normalize_name(v):
    if pd.isna(v):
        return ""
    v = str(v).strip().upper()
    v = unicodedata.normalize("NFKD", v)
    v = "".join(c for c in v if not unicodedata.combining(c))
    v = v.replace("'", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", v).strip()


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


SAFE_ALIASES = {
    "JEBENIANA": "JBENIANA",
    "MAHRAS": "MAHRES",
    "MEDENINE": "MEDNINE",
    "BEN GUERDANE": "BEN GUERDENE",
    "MENZEL BOUZELFA": "MENZEL B-ZELFA",
    "SIDI BOUZID": "SIDI-BOUZID",
    "EL KRAM": "KRAM",
    "EL MOUROUJ": "MOUROUJ",
    "LE BARDO": "BARDO",
    "SOUSSE VILLE": "SOUSSE",
    "SFAX VILLE": "SFAX VILLE",
}


MANUAL_ANCHORS = {
    "TUNIS VILLE": (36.7981, 10.1803),
    "KRAM": (36.85, 10.30),
    "MOUROUJ": (36.7214, 10.1679),
    "BARDO": (36.8111, 10.1364),
    "SOUSSE": (35.8269, 10.63),
    "SOUSSE NORD": (35.8623, 10.5958),
    "KAIROUAN": (35.6623, 10.0926),
    "KASSERINE": (35.1711, 8.8325),
    "SIDI-BOUZID": (35.0372, 9.4853),
    "GAFSA": (34.4144, 8.7788),
    "KEBILI": (33.7031, 8.9692),
    "TATAOUINE": (32.9297, 10.4514),
    "MEDNINE": (33.3556, 10.4925),
    "SILIANA": (36.0833, 9.3667),
    "BEJA": (36.726069, 9.18284),
    "BIZERTE": (37.2775, 9.8581),
    "GABES": (33.886, 10.102091),
    "GABES NORD": (33.935, 10.07),
    "SFAX NORD": (34.8183, 10.7469),
    "JERBA": (33.8751, 10.845),
    "MAHDIA": (35.5044, 11.0567),
    "MOKNINE": (35.6311, 10.9011),
    "KAIROUAN NORD": (35.68206, 10.088035),
    "EL JEM": (35.2972, 10.7119),
    "METLAOUI": (34.32353, 8.401567),
    "TOZEUR": (33.9197, 8.1336),
    "MAKNASSY": (34.6053, 9.6075),
    "MSAKEN": (35.7275, 10.5803),
    "SBEITLA": (35.237627, 9.124747),
    "ENFIDHA": (36.1353, 10.3817),
    "MONASTIR": (35.762395, 10.79772),
    "MENZEL BOURGUIBA": (37.148475, 9.783838),
    "NABEUL": (36.4561, 10.7358),
    "MENZEL B-ZELFA": (36.6833, 10.5833),
    "MENZEL TEMIME": (36.785242, 11.008863),
    "HAMMAMET": (36.4, 10.6167),
    "JENDOUBA": (36.499947, 8.780953),
    "KEF": (36.1817, 8.71),
    "TABARKA": (36.953204, 8.769581),
    "ZAGHOUAN": (36.4025, 10.1431),
    "ARIANA": (36.86703, 10.18407),
    "EZZAHRA": (36.7497, 10.3127),
    "MANNOUBA": (36.8097, 10.0928),
    "EL MENZAH": (36.8528, 10.1703),
    "ZARZIS": (33.5028, 11.1122),
    "BEN GUERDENE": (33.1386, 11.2175),
    "JBENIANA": (35.0333, 10.9),
    "MAHRES": (34.5292, 10.5053),
    "SFAX SUD": (34.7406, 10.76),
    "SFAX VILLE": (34.7406, 10.76),
}


def main():
    muni = pd.read_csv(MUNI_FILE, dtype=str)
    muni["latitude"] = muni["latitude"].astype(float)
    muni["longitude"] = muni["longitude"].astype(float)
    dist = pd.read_csv(DIST_FILE, dtype=str)

    muni["muni_norm"] = muni["municipality"].map(normalize_name)
    muni_lookup = {
        r["muni_norm"]: (r["latitude"], r["longitude"]) for _, r in muni.iterrows()
    }

    dist["dist_norm"] = dist["district_name"].map(normalize_name)
    dist_lookup = {r["dist_norm"]: r for _, r in dist.iterrows()}

    # ------------- Build anchors for all 50 districts -------------
    anchors = {}
    for _, row in dist.iterrows():
        name = row["district_name"]
        # Priority 1: manual
        if name in MANUAL_ANCHORS:
            lat, lon = MANUAL_ANCHORS[name]
        # Priority 2: same-name municipality
        elif normalize_name(name) in muni_lookup:
            lat, lon = muni_lookup[normalize_name(name)]
        else:
            lat, lon = None, None
        anchors[name] = {
            "district_id": row["district_id"],
            "region_id": row["region_id"],
            "region_name": row["region_name"],
            "lat": lat,
            "lon": lon,
        }

    # Fallback anchor for any district that still has no coords:
    # use region centroid of anchored districts
    for name, a in anchors.items():
        if a["lat"] is None:
            peers = [
                (b["lat"], b["lon"])
                for b in anchors.values()
                if b["region_id"] == a["region_id"] and b["lat"] is not None
            ]
            if peers:
                a["lat"] = sum(p[0] for p in peers) / len(peers)
                a["lon"] = sum(p[1] for p in peers) / len(peers)

    # ------------- Per-parent governorate → allowed regions -------------
    GOV_TO_REGION = {
        "TUNIS": "1",
        "ARIANA": "1",
        "BEN AROUS": "1",
        "MANNOUBA": "1",
        "NABEUL": "2",
        "ZAGHOUAN": "2",
        "BIZERTE": "2",
        "BEJA": "3",
        "JENDOUBA": "3",
        "KEF": "3",
        "SILIANA": "3",
        "SOUSSE": "4",
        "MONASTIR": "4",
        "MAHDIA": "4",
        "KAIROUAN": "4",
        "SFAX": "5",
        "KASSERINE": "6",
        "SIDI BOUZID": "6",
        "GAFSA": "6",
        "TOZEUR": "6",
        "GABES": "7",
        "MEDENINE": "7",
        "KEBILI": "7",
        "TATAOUINE": "7",
    }

    def get_district_exact(name):
        if not name:
            return None
        n = normalize_name(name)
        if n in dist_lookup:
            return dist_lookup[n]
        if n in SAFE_ALIASES:
            t = normalize_name(SAFE_ALIASES[n])
            if t in dist_lookup:
                return dist_lookup[t]
        return None

    def nearest_in_region(lat, lon, region_id):
        best, best_d = None, None
        for n, a in anchors.items():
            if a["lat"] is None:
                continue
            if region_id and str(a["region_id"]) != str(region_id):
                continue
            d = haversine(lat, lon, a["lat"], a["lon"])
            if best_d is None or d < best_d:
                best_d, best = d, n
        return best, best_d

    def nearest_global(lat, lon):
        best, best_d = None, None
        for n, a in anchors.items():
            if a["lat"] is None:
                continue
            d = haversine(lat, lon, a["lat"], a["lon"])
            if best_d is None or d < best_d:
                best_d, best = d, n
        return best, best_d

    results = []

    for _, row in muni.iterrows():
        m_name = str(row["municipality"]).strip()
        parent = str(row["parent_municipality"]).strip()
        lat, lon = row["latitude"], row["longitude"]

        district = None
        status = method = conf = ""
        note = ""

        # Rule 1: DIRECT_NAME
        d = get_district_exact(m_name)
        if d is not None:
            district, status, method, conf = d, "MAPPED", "DIRECT_NAME", "HIGH"
            note = "Municipality name matches a Prosol district or alias."

        # Rule 2: parent is itself a district → prefer nearest district
        # whose name matches the parent but restricted to the correct region.
        if district is None and parent:
            pregion = GOV_TO_REGION.get(normalize_name(parent))
            best, bd = nearest_in_region(lat, lon, pregion) if pregion else (None, None)
            if best:
                a = anchors[best]
                district = dist_lookup[normalize_name(best)]
                status, method = "MAPPED", "GEO_IN_REGION"
                conf = "HIGH" if bd < 15 else ("MEDIUM" if bd < 40 else "LOW")
                note = (
                    f"Assigned to nearest Prosol district in region "
                    f"'{a['region_name']}' ({bd:.1f} km)."
                )
            else:
                best, bd = nearest_global(lat, lon)
                if best:
                    district = dist_lookup[normalize_name(best)]
                    status, method = "MAPPED", "GEO_GLOBAL"
                    conf = "MEDIUM" if bd < 60 else "LOW"
                    note = (
                        f"Assigned to nearest Prosol district globally ({bd:.1f} km)."
                    )

        # Safety net: if still nothing, fall back to the district of the parent
        if district is None and parent:
            pd_ = get_district_exact(parent)
            if pd_ is not None:
                district = pd_
                status, method, conf = "MAPPED", "PARENT_FALLBACK", "LOW"
                note = f"Fallback via parent '{parent}'."

        # Absolute last resort: nearest globally
        if district is None:
            best, bd = nearest_global(lat, lon)
            if best:
                district = dist_lookup[normalize_name(best)]
                status, method, conf = "MAPPED", "GEO_LAST_RESORT", "LOW"
                note = f"Last-resort nearest global ({bd:.1f} km)."

        results.append(
            {
                "municipality": m_name,
                "parent_municipality": parent,
                "prosol_district_id": (
                    district["district_id"] if district is not None else ""
                ),
                "prosol_district_name": (
                    district["district_name"] if district is not None else ""
                ),
                "region_id": district["region_id"] if district is not None else "",
                "region_name": district["region_name"] if district is not None else "",
                "mapping_status": status or "UNMAPPED",
                "mapping_method": method or "NONE",
                "confidence": conf,
                "notes": note,
            }
        )

    out = pd.DataFrame(results)

    # ------------- Special rules: corrections -------------
    # Force JERBA for Djerba island municipalities that had MEDENINE parent
    DJERBA = {"AJIM", "MIDOUN", "HOUMET ESSOUK"}
    j_mask = out["municipality"].str.upper().isin(DJERBA)
    j_row = dist[dist["district_name"] == "JERBA"].iloc[0]
    out.loc[
        j_mask,
        ["prosol_district_id", "prosol_district_name", "region_id", "region_name"],
    ] = [j_row["district_id"], "JERBA", j_row["region_id"], j_row["region_name"]]
    out.loc[j_mask, "mapping_method"] = "GEO_OVERRIDE"
    out.loc[j_mask, "confidence"] = "HIGH"
    out.loc[j_mask, "notes"] = "Djerba island municipality → JERBA."

    # Force MSAKEN for its own municipality (parent SOUSSE)
    msa = out["municipality"].str.upper() == "MSAKEN"
    msa_row = dist[dist["district_name"] == "MSAKEN"].iloc[0]
    out.loc[
        msa, ["prosol_district_id", "prosol_district_name", "region_id", "region_name"]
    ] = [msa_row["district_id"], "MSAKEN", msa_row["region_id"], msa_row["region_name"]]
    out.loc[msa, "mapping_method"] = "DIRECT_NAME"
    out.loc[msa, "confidence"] = "HIGH"
    out.loc[msa, "notes"] = "Municipality is its own Prosol district."

    # Force SBEITLA for its own municipality (parent KASSERINE)
    sbe = out["municipality"].str.upper() == "SBEITLA"
    sbe_row = dist[dist["district_name"] == "SBEITLA"].iloc[0]
    out.loc[
        sbe, ["prosol_district_id", "prosol_district_name", "region_id", "region_name"]
    ] = [
        sbe_row["district_id"],
        "SBEITLA",
        sbe_row["region_id"],
        sbe_row["region_name"],
    ]
    out.loc[sbe, "mapping_method"] = "DIRECT_NAME"
    out.loc[sbe, "confidence"] = "HIGH"
    out.loc[sbe, "notes"] = "Municipality is its own Prosol district."

    # Force ENFIDHA
    enf = out["municipality"].str.upper() == "ENFIDHA"
    enf_row = dist[dist["district_name"] == "ENFIDHA"].iloc[0]
    out.loc[
        enf, ["prosol_district_id", "prosol_district_name", "region_id", "region_name"]
    ] = [
        enf_row["district_id"],
        "ENFIDHA",
        enf_row["region_id"],
        enf_row["region_name"],
    ]
    out.loc[enf, "mapping_method"] = "DIRECT_NAME"
    out.loc[enf, "confidence"] = "HIGH"

    # ------------- Diagnostics -------------
    print("=" * 70)
    print("STATUS COUNTS")
    print(out["mapping_status"].value_counts().to_string())
    print("\nMETHOD COUNTS")
    print(out["mapping_method"].value_counts().to_string())

    mapped_ids = set(out.loc[out["prosol_district_id"] != "", "prosol_district_id"])
    missing = [
        r["district_name"]
        for _, r in dist.iterrows()
        if r["district_id"] not in mapped_ids
    ]
    print(f"\nDistricts with ZERO municipalities: {missing if missing else 'NONE ✅'}")
    print(
        f"Total municipalities: {len(out)}  |  UNMAPPED: {(out['mapping_status']=='UNMAPPED').sum()}"
    )

    out = out.sort_values(
        by=["region_id", "prosol_district_id", "municipality"], na_position="last"
    )
    out.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")
    print(f"\nSaved → {OUT_FILE}")


if __name__ == "__main__":
    main()
