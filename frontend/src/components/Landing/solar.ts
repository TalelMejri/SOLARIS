/**
 * Solar model + helpers shared by the hero scene, the HUD and the chart.
 * Everything here is a SIMULATION. Replace `forecastAt` with your real model output.
 */

export type RGB = [number, number, number];
export type CloudMode = 0 | 1 | 2;

export interface SimState {
  /** time of day, 0 = 06:00, 1 = 19:30 */
  t: number;
  mode: CloudMode;
  playing: boolean;
  /** live output of the main roof, kW (written by the scene) */
  live: number;
  /** fraction of the main roof in cloud shadow, 0..1 (written by the scene) */
  shaded: number;
}

export const KWP = 5.2; // installed peak of the simulated roof
export const KWMAX = 4.7; // peak AC output
export const MAXEL = (62 * Math.PI) / 180; // max sun elevation used in the scene
export const DAY_SECONDS = 100; // seconds for one simulated day

/** c = mean cloud cover, n = number of cloud objects, s = cloud scale */
export const MODES = [
  { label: "Clear", c: 0, n: 0, s: 1 },
  { label: "Scattered", c: 0.35, n: 4, s: 1 },
  { label: "Overcast", c: 0.8, n: 9, s: 1.45 },
] as const;

export const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
export const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
export const hex = (h: number): RGB => [(h >> 16) & 255, (h >> 8) & 255, h & 255];
export const mix = (a: RGB, b: RGB, k: number): RGB => [
  Math.round(lerp(a[0], b[0], k)),
  Math.round(lerp(a[1], b[1], k)),
  Math.round(lerp(a[2], b[2], k)),
];
export const css = (c: RGB) => `rgb(${c[0]},${c[1]},${c[2]})`;

export const elevation = (t: number) => MAXEL * Math.sin(Math.PI * t);

/** normalised clear-sky irradiance, 0..1 */
export const clearSky = (t: number) => {
  const s = Math.sin(elevation(t)) / Math.sin(MAXEL);
  return s <= 0 ? 0 : Math.pow(s, 1.15);
};

/** median forecast and 10/90 percent range, in kW */
export function forecastAt(t: number, mode: CloudMode) {
  const m = MODES[mode];
  const cs = KWMAX * clearSky(t);
  const p50 = cs * (1 - 0.75 * m.c);
  const w = cs * (0.04 + 0.3 * 4 * m.c * (1 - m.c));
  return { p50, hi: Math.min(cs, p50 + w), lo: Math.max(0, p50 - w) };
}

export function hourString(t: number) {
  const h = 6 + 13.5 * t;
  const hh = Math.floor(h);
  const mm = Math.floor((h - hh) * 60);
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

/* ---------- sky ---------- */
const SKY: Record<"top" | "mid" | "hor", readonly [RGB, RGB]> = {
  top: [hex(0x1a2a55), hex(0x2266b0)],
  mid: [hex(0x7a6a9e), hex(0x4a8fd0)],
  hor: [hex(0xf2a66e), hex(0x8fc0e8)],
};
const NIGHT: RGB = [4, 12, 30];

/** CSS custom properties applied to the hero element (sky gradient + sun position). */
export function skyVars(t: number, dark: boolean, shaded: number): Record<string, string> {
  const k = Math.pow(Math.max(0, Math.sin(Math.PI * t)), 0.75);
  const dk = dark ? 0.22 : 0;
  const pick = (p: readonly [RGB, RGB]) => css(mix(mix(p[0], p[1], k), NIGHT, dk));
  const core = mix([255, 140, 70], [255, 240, 190], k);
  const halo = mix([255, 130, 60], [255, 214, 130], k);
  return {
    "--sky": `linear-gradient(180deg,${pick(SKY.top)} 0%,${pick(SKY.mid)} 52%,${pick(SKY.hor)} 100%)`,
    "--sx": `${lerp(88, 36, t).toFixed(2)}%`,
    "--sy": `${(66 - 50 * Math.sin(Math.PI * t)).toFixed(2)}%`,
    "--sun-core": css(core),
    "--sun-halo": `rgba(${halo.join(",")},.6)`,
    "--sun-o": (1 - 0.5 * shaded).toFixed(3),
  };
}