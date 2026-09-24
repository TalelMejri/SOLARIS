/**
 * Simulated regional solar + grid-load model for the "grid impact" section.
 * ALL NUMBERS ARE DEMO DATA. Replace `regionAt` / `nationalAt` with your real
 * forecasts (per-governorate PV output, load forecast, uncertainty).
 */

import { TUNISIA_GEO } from "./Tunisiageo";

export type Metric = "solar" | "load" | "share";
export type Weather = "clear" | "front";

/** keys are the Natural Earth names used in tunisia-geo.ts */
const META: Record<string, { name: string; cap: number; share: number }> = {
  Tunis: { name: "Tunis", cap: 95, share: 0.1 },
  "Ben Arous (Tunis Sud)": { name: "Ben Arous", cap: 60, share: 0.06 },
  Manubah: { name: "Manouba", cap: 20, share: 0.03 },
  Bizerte: { name: "Bizerte", cap: 40, share: 0.05 },
  Nabeul: { name: "Nabeul", cap: 55, share: 0.06 },
  Zaghouan: { name: "Zaghouan", cap: 8, share: 0.015 },
  Béja: { name: "Béja", cap: 12, share: 0.03 },
  Jendouba: { name: "Jendouba", cap: 8, share: 0.03 },
  "Le Kef": { name: "Le Kef", cap: 8, share: 0.025 },
  Siliana: { name: "Siliana", cap: 6, share: 0.02 },
  Sousse: { name: "Sousse", cap: 70, share: 0.07 },
  Monastir: { name: "Monastir", cap: 50, share: 0.05 },
  Mahdia: { name: "Mahdia", cap: 25, share: 0.035 },
  Kairouan: { name: "Kairouan", cap: 22, share: 0.045 },
  Kassérine: { name: "Kasserine", cap: 15, share: 0.035 },
  "Sidi Bou Zid": { name: "Sidi Bouzid", cap: 14, share: 0.035 },
  Sfax: { name: "Sfax", cap: 95, share: 0.1 },
  Gafsa: { name: "Gafsa", cap: 18, share: 0.035 },
  Tozeur: { name: "Tozeur", cap: 9, share: 0.012 },
  Kebili: { name: "Kébili", cap: 9, share: 0.015 },
  Gabès: { name: "Gabès", cap: 30, share: 0.035 },
  Médenine: { name: "Médenine", cap: 30, share: 0.04 },
  Tataouine: { name: "Tataouine", cap: 12, share: 0.02 },
};

export interface Region {
  key: string;
  name: string;
  d: string;
  cx: number;
  cy: number;
  /** installed rooftop PV, MWp */
  cap: number;
  /** share of national load, sums to 1 */
  share: number;
  /** 0..1 position used by the cloud front (NW = 1, SE = 0) */
  u: number;
}

const shareSum = Object.values(META).reduce((s, m) => s + m.share, 0);

export const REGIONS: Region[] = TUNISIA_GEO.regions.map((g) => {
  const m = META[g.name] ?? { name: g.name, cap: 10, share: 0.02 };
  return {
    key: g.name,
    name: m.name,
    d: g.d,
    cx: g.cx,
    cy: g.cy,
    cap: m.cap,
    share: m.share / shareSum,
    u: (1 - g.cy / TUNISIA_GEO.h) * 0.6 + (1 - g.cx / TUNISIA_GEO.w) * 0.4,
  };
});

export const TOTAL_CAP = REGIONS.reduce((s, r) => s + r.cap, 0);
const DERATE = 0.8;

/* ---------- national demand + sun ---------- */
const gauss = (h: number, m: number, s: number) => Math.exp(-0.5 * ((h - m) / s) ** 2);

/** national grid load in MW for a decimal hour 0..24 (evening-peak profile) */
export const loadNat = (h: number) =>
  2900 + 850 * gauss(h, 10.5, 3.4) + 1350 * gauss(h, 21, 2.3) + 1350 * gauss(h, -3, 2.3) + 250 * gauss(h, 14, 2);

/** normalised clear-sky irradiance, sunrise 06:00, sunset 19:30 */
export const clearAt = (h: number) => (h <= 6 || h >= 19.5 ? 0 : Math.pow(Math.sin((Math.PI * (h - 6)) / 13.5), 1.15));

export const LMAX = Math.max(...Array.from({ length: 97 }, (_, i) => loadNat(i / 4)));
const MAX_REGION_LOAD = Math.max(...REGIONS.map((r) => r.share)) * LMAX;

/** cloud cover 0..0.85 for a region; the front sweeps from the north-west to the south-east */
export function cloudAt(r: Region, h: number, weather: Weather) {
  if (weather === "clear") return 0;
  const front = 1.3 - 0.11 * (h - 6);
  const z = (r.u - front) / 0.2;
  return 0.85 * Math.exp(-z * z);
}

export interface RegionState {
  pv: number; // MW
  load: number; // MW
  c: number; // cloud cover
  u: number; // relative uncertainty of pv
  pvLo: number;
  pvHi: number;
  /** 0..1 output relative to clear-sky maximum */
  sv: number;
}

export function regionAt(r: Region, h: number, weather: Weather): RegionState {
  const clear = clearAt(h);
  const c = cloudAt(r, h, weather);
  const pv = r.cap * DERATE * clear * (1 - 0.8 * c);
  const u = 0.05 + 0.3 * 4 * c * (1 - c);
  const clearPv = r.cap * DERATE * clear;
  return {
    pv,
    load: loadNat(h) * r.share,
    c,
    u,
    pvLo: pv * (1 - u),
    pvHi: Math.min(clearPv, pv * (1 + u)),
    sv: clear > 0 ? (1 - 0.8 * c) * clear : 0,
  };
}

export interface NationalState {
  pv: number;
  pvLo: number;
  pvHi: number;
  load: number;
  net: number;
  clear: number;
  /** capacity-weighted uncertainty */
  u: number;
}

export function nationalAt(h: number, weather: Weather): NationalState {
  let pv = 0;
  let lo = 0;
  let hi = 0;
  let u = 0;
  for (const r of REGIONS) {
    const s = regionAt(r, h, weather);
    pv += s.pv;
    lo += s.pvLo;
    hi += s.pvHi;
    u += s.u * r.cap;
  }
  const load = loadNat(h);
  return { pv, pvLo: lo, pvHi: hi, load, net: load - pv, clear: clearAt(h), u: u / TOTAL_CAP };
}

/* ---------- map metric ---------- */
export function metricValue(metric: Metric, s: RegionState): number {
  if (metric === "solar") return s.sv;
  if (metric === "load") return s.load / MAX_REGION_LOAD;
  return s.load > 0 ? s.pv / s.load / 0.3 : 0;
}

export function hourLabel(h: number) {
  const hh = Math.floor(h);
  const mm = Math.floor((h - hh) * 60);
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

/** rule-based decision-support sentence (example logic, replace with your own rules) */
export function adviceFor(h: number, weather: Weather, region: Region, rs: RegionState): string {
  const nat = nationalAt(h, weather);
  const next = nationalAt(h + 1, weather);
  const ramp = next.net - nat.net;
  const share = nat.load > 0 ? (nat.pv / nat.load) * 100 : 0;
  const parts: string[] = [];

  if (nat.clear === 0) {
    parts.push("No solar output at this hour, so demand is met entirely by conventional and imported supply.");
  } else if (ramp >= 200) {
    parts.push(`Net load rises by ${Math.round(ramp)} MW in the next hour as solar fades. Bring reserve online before ${hourLabel(h + 1)}.`);
  } else if (nat.u > 0.15) {
    parts.push(`The cloud front makes national solar output uncertain by about ${Math.round(nat.u * 100)} percent. Hold flexible reserve until it passes.`);
  } else {
    parts.push(`Rooftop solar covers ${Math.round(share)} percent of national demand, leaving room to lower conventional dispatch.`);
  }

  if (nat.clear > 0) {
    const local = rs.load > 0 ? Math.round((rs.pv / rs.load) * 100) : 0;
    parts.push(
      `${region.name}: solar covers ${local} percent of local load${rs.c > 0.4 ? ", and cloud is cutting its output right now." : "."}`,
    );
  }
  return parts.join(" ");
}