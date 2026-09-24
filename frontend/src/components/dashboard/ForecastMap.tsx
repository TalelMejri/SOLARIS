import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as RPointerEvent,
} from 'react';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { clamp01, css, hex, mix, type RGB } from '@/components/Landing/solar';
import {
  REGIONS,
  hourLabel,
  metricValue,
  type Metric,
  type RegionState,
} from '@/types/grid';
import { useIsDark } from '@/types/useDark';
import { TUNISIA_GEO } from '@/types/Tunisiageo';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';

/* ============================================================
   API
   ============================================================ */

const API_URL =
  'http://localhost:5000';

/* ============================================================
   Types & Constants
   ============================================================ */

type MapMode = 'region' | 'district';
type Horizon = 'h12' | 'h24' | 'h72';
type Band = 'p50' | 'p10' | 'p90';

interface DistrictQuantile {
  district_id: number;
  district_name: string;
  region_name: string;
  latitude: number;
  longitude: number;
  capacity_mw: number;
  forecast_p10: number;
  forecast_p50: number;
  forecast_p90: number;
  forecast_normalized: number;
  utilization: number;
  temperature_2m_c: number | null;
  wind_speed_10m_ms: number | null;
  cloud_cover_fraction: number | null;
}

interface RegionQuantile {
  region_id: number;
  region_name: string;
  capacity_mw: number;
  regional_mw_p10: number;
  regional_mw_p50: number;
  regional_mw_p90: number;
  n_districts: number;
}

/* ============================================================
   GOVERNORATE → PROSOL REGION MAPPING
   The map polygons are named after governorates.
   The API returns 7 Prosol regions.
   Every governorate inherits its region's value.
   ============================================================ */

const GOVERNORATE_TO_REGION: Record<string, string> = {
  // TUNIS region
  Tunis: 'TUNIS',
  'Ben Arous (Tunis Sud)': 'TUNIS',
  Manubah: 'TUNIS',

  // NORD region
  Bizerte: 'NORD',
  Nabeul: 'NORD',
  Zaghouan: 'NORD',

  // NORD OUEST region
  Béja: 'NORD OUEST',
  Jendouba: 'NORD OUEST',
  'Le Kef': 'NORD OUEST',
  Siliana: 'NORD OUEST',

  // CENTRE region
  Sousse: 'CENTRE',
  Monastir: 'CENTRE',
  Mahdia: 'CENTRE',
  Kairouan: 'CENTRE',
  'Sidi Bou Zid': 'CENTRE',

  // SFAX region
  Sfax: 'SFAX',

  // SUD OUEST region
  Gafsa: 'SUD OUEST',
  Tozeur: 'SUD OUEST',
  Kebili: 'SUD OUEST',

  // SUD region
  Gabès: 'SUD',
  Médenine: 'SUD',
  Tataouine: 'SUD',
};

const HORIZON_LABEL: Record<Horizon, string> = {
  h12: 'H+12',
  h24: 'H+24',
  h72: 'H+72',
};

const BAND_LABEL: Record<Band, string> = {
  p10: 'P10',
  p50: 'P50',
  p90: 'P90',
};

const LABELED = new Set(REGIONS.map((r) => r.key));

const RAMPS: Record<'dark' | 'light', Record<Metric, [RGB, RGB]>> = {
  dark: {
    solar: [hex(0x17325c), hex(0xffb627)],
    load: [hex(0x17325c), hex(0x62b4ff)],
    share: [hex(0x17325c), hex(0x4fe3b0)],
  },
  light: {
    solar: [hex(0xe3ebf5), hex(0xf59e0b)],
    load: [hex(0xe3ebf5), hex(0x2563eb)],
    share: [hex(0xe3ebf5), hex(0x059669)],
  },
};

const COPY = {
  title: 'National Forecast Map',
  subtitle: 'Rooftop solar · P10 / P50 / P90 · per-region and district',
  mapShows: 'Map shows',
  metrics: { solar: 'Solar', load: 'Load', share: 'Share' } as Record<Metric, string>,
  band: 'Band',
  play: 'Play',
  pause: 'Pause',
  region: {
    cap: 'Installed',
    p10: 'P10 (low)',
    p50: 'P50 (central)',
    p90: 'P90 (high)',
    util: 'Utilization',
    districts: 'Districts',
  },
  district: {
    region: 'Region',
    cap: 'Installed',
    p10: 'P10',
    p50: 'P50',
    p90: 'P90',
    util: 'Utilization',
  },
};

const fmt = (n: number, digits = 1) =>
  Number.isFinite(n)
    ? n.toLocaleString('en-US', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })
    : '—';

/* ============================================================
   Helpers
   ============================================================ */

function geoToSvg(lat: number, lon: number, w: number, h: number) {
  const MIN_LAT = 30.0;
  const MAX_LAT = 37.6;
  const MIN_LON = 7.5;
  const MAX_LON = 12.5;
  const x = ((lon - MIN_LON) / (MAX_LON - MIN_LON)) * w;
  const y = h - ((lat - MIN_LAT) / (MAX_LAT - MIN_LAT)) * h;
  return { x, y };
}

function hourToISO(h: number): string {
  const d = new Date('2022-07-01T00:00:00Z');
  d.setUTCHours(Math.floor(h), Math.floor((h % 1) * 60), 0, 0);
  return d.toISOString();
}

/* ============================================================
   Segmented control
   ============================================================ */

function Segmented<T extends string>(props: {
  label: string;
  value: T;
  options: { v: T; l: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        {props.label}
      </span>
      <div
        role="radiogroup"
        className="inline-flex gap-0.5 rounded-full bg-muted p-[3px]"
      >
        {props.options.map((o) => (
          <button
            key={o.v}
            type="button"
            role="radio"
            aria-checked={props.value === o.v}
            onClick={() => props.onChange(o.v)}
            className={cn(
              'rounded-full px-3 py-1.5 text-xs font-semibold leading-none transition-colors',
              props.value === o.v
                ? 'bg-foreground text-background'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {o.l}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ============================================================
   Main Component
   ============================================================ */

export default function ForecastMap() {
  const dark = useIsDark();

  const [hour, setHour] = useState(12);
  const [metric, setMetric] = useState<Metric>('solar');
  const [band, setBand] = useState<Band>('p50');
  const [mapMode, setMapMode] = useState<MapMode>('region');
  const [horizon, setHorizon] = useState<Horizon>('h12');
  const [selKey, setSelKey] = useState('Sfax');
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number } | null>(null);
  const [playing, setPlaying] = useState(false);

  const [regions, setRegions] = useState<RegionQuantile[]>([]);
  const [districts, setDistricts] = useState<DistrictQuantile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const wrapRef = useRef<HTMLDivElement>(null);
  const debouncedHour = useDebouncedValue(hour, 250);

  /* ---------- Fetch ---------- */
  useEffect(() => {
    let cancelled = false;
    const ctrl = new AbortController();

    const fetchAll = async () => {
      setLoading(true);
      setError(null);

      try {
        const ts = hourToISO(debouncedHour);

        const [rRes, dRes] = await Promise.all([
          fetch(
            `${API_URL}/api/regions/quantile?horizon=${horizon}&timestamp=${encodeURIComponent(ts)}`,
            { signal: ctrl.signal },
          ).catch(() => null),
          fetch(
            `${API_URL}/api/districts/quantile?horizon=${horizon}&timestamp=${encodeURIComponent(ts)}`,
            { signal: ctrl.signal },
          ).catch(() => null),
        ]);

        const rJson = rRes?.ok ? await rRes.json() : { regions: [] };
        const dJson = dRes?.ok ? await dRes.json() : { districts: [] };

        if (cancelled) return;

        // ---- Clean regions ----
        const rawRegions = (rJson.regions ?? []) as RegionQuantile[];
        setRegions(rawRegions);

        // ---- Clean + dedupe districts ----
        const rawDistricts = (dJson.districts ?? []) as DistrictQuantile[];
        const seen = new Set<number>();
        const uniqueDistricts: DistrictQuantile[] = [];

        for (const d of rawDistricts) {
          const id = Number(d.district_id);
          if (seen.has(id)) continue;
          seen.add(id);
          uniqueDistricts.push({
            ...d,
            district_id: id,
            capacity_mw: Number(d.capacity_mw) || 0,
            forecast_p10: Number(d.forecast_p10) || 0,
            forecast_p50: Number(d.forecast_p50) || 0,
            forecast_p90: Number(d.forecast_p90) || 0,
            utilization: Number(d.utilization) || 0,
          });
        }

        setDistricts(uniqueDistricts);
        setLoading(false);
      } catch (e: any) {
        if (cancelled || e?.name === 'AbortError') return;
        setError(e?.message ?? 'Fetch failed');
        setLoading(false);
      }
    };

    fetchAll();
    return () => {
      cancelled = true;
      ctrl.abort();
    };
  }, [debouncedHour, horizon]);

  /* ---------- Play ---------- */
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      setHour((h) => (h + dt * 1.2 > 21 ? 5 : h + dt * 1.2));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  /* ---------- Lookups ---------- */
  const regionByName = useMemo(() => {
    const m = new Map<string, RegionQuantile>();
    for (const r of regions) m.set(r.region_name, r);
    return m;
  }, [regions]);

  const districtByName = useMemo(() => {
    const m = new Map<string, DistrictQuantile>();
    for (const d of districts) m.set(d.district_name, d);
    return m;
  }, [districts]);

  /* ---------- Region states for the SVG ---------- */
  const states = useMemo(
    () =>
      REGIONS.map((r) => {
        const prosolRegion = GOVERNORATE_TO_REGION[r.key];
        const snap = prosolRegion ? regionByName.get(prosolRegion) : undefined;

        const p50 = snap?.regional_mw_p50 ?? 0;
        const p10 = snap?.regional_mw_p10 ?? 0;
        const p90 = snap?.regional_mw_p90 ?? 0;
        const cap = snap?.capacity_mw ?? 0;

        const selected = band === 'p10' ? p10 : band === 'p90' ? p90 : p50;

        const s: RegionState = {
          pv: selected,
          sv: cap > 0 ? selected / cap : 0,
          load: 0,
          c: cap,
          u: cap > 0 ? selected / cap : 0,
          pvLo: p10,
          pvHi: p90,
        };

        return { r, s, snap, prosolRegion };
      }),
    [regionByName, band],
  );

  const sel = states.find((x) => x.r.key === selKey) ?? states[0];
  const hovered = hoverKey ? states.find((x) => x.r.key === hoverKey) : undefined;
  const selDistrict = districtByName.get(selKey);

  const selRegionData = useMemo(() => {
    const prosolRegion = GOVERNORATE_TO_REGION[selKey];
    return prosolRegion ? regionByName.get(prosolRegion) : undefined;
  }, [selKey, regionByName]);

  const selGovernorateName =
    REGIONS.find((r) => r.key === selKey)?.name ?? selKey;

  /* ---------- Color ramp — amplified for better visual contrast ---------- */

  const ramps = RAMPS[dark ? 'dark' : 'light'][metric];
  const fillFor = (v: number) => {
    // Utilization range in Tunisia rooftop PV is roughly 0.4–0.7.
    // Stretch this range to 0–1 for a richer color map.
    const normalized = (v - 0.35) / 0.4;
    return css(mix(ramps[0], ramps[1], Math.pow(clamp01(normalized), 0.85)));
  };

  const onMapMove = (e: RPointerEvent<SVGPathElement>, key: string) => {
    const box = wrapRef.current?.getBoundingClientRect();
    if (!box) return;
    setHoverKey(key);
    setTip({ x: e.clientX - box.left, y: e.clientY - box.top });
  };

  /* ---------- Loading / Error ---------- */
  if (loading && regions.length === 0) {
    return (
      <div className="card-elevated p-5">
        <p className="text-sm text-muted-foreground">Loading map…</p>
      </div>
    );
  }

  if (error && regions.length === 0) {
    return (
      <div className="card-elevated p-5 space-y-2">
        <p className="text-sm text-[var(--status-critical)]">
          Failed to load map: {error}
        </p>
        <p className="text-xs text-muted-foreground">
          Backend: <code>{API_URL}</code>
        </p>
      </div>
    );
  }

  /* ---------- Render ---------- */
  return (
    <div className="card-elevated overflow-hidden">
      {/* Header */}
      <div className="flex flex-col gap-4 border-b border-border px-5 pb-4 pt-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold tracking-tight text-foreground">
            {COPY.title}
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {COPY.subtitle} · {hourLabel(hour)} local ·{' '}
            {regions.length} regions, {districts.length} districts
          </p>
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <Segmented
            label="Map mode"
            value={mapMode}
            onChange={setMapMode}
            options={[
              { v: 'region', l: `Regions (${regions.length || 7})` },
              { v: 'district', l: `Districts (${districts.length || 50})` },
            ]}
          />
          <Segmented
            label={COPY.band}
            value={band}
            onChange={setBand}
            options={[
              { v: 'p10', l: 'P10' },
              { v: 'p50', l: 'P50' },
              { v: 'p90', l: 'P90' },
            ]}
          />
          <Segmented
            label="Horizon"
            value={horizon}
            onChange={setHorizon}
            options={[
              { v: 'h12', l: 'H+12' },
              { v: 'h24', l: 'H+24' },
              { v: 'h72', l: 'H+72' },
            ]}
          />
        </div>
      </div>

      {/* Map */}
      <div className="grid grid-cols-1 items-start gap-6 p-5 lg:grid-cols-[minmax(260px,340px)_1fr] lg:gap-8">
        <div className="mx-auto w-full max-w-[360px] lg:mx-0 lg:max-w-none">
          <div ref={wrapRef} className="relative">
            <svg
              viewBox={`0 0 ${TUNISIA_GEO.w} ${TUNISIA_GEO.h}`}
              className="block h-auto w-full overflow-visible"
            >
              {mapMode === 'region' ? (
                <>
                  {states.map(({ r, s }) => (
                    <path
                      key={r.key}
                      d={r.d}
                      role="button"
                      tabIndex={0}
                      aria-label={r.name}
                      aria-pressed={r.key === selKey}
                      fill={fillFor(metricValue(metric, s))}
                      className="cursor-pointer stroke-background outline-none transition-[fill] duration-100 focus-visible:stroke-foreground"
                      strokeWidth={1}
                      vectorEffect="non-scaling-stroke"
                      onClick={() => setSelKey(r.key)}
                      onPointerEnter={(e) => onMapMove(e, r.key)}
                      onPointerMove={(e) => onMapMove(e, r.key)}
                      onPointerLeave={() => {
                        setHoverKey(null);
                        setTip(null);
                      }}
                    />
                  ))}

                  <path
                    d={sel.r.d}
                    fill="none"
                    className="pointer-events-none stroke-foreground"
                    strokeWidth={2.6}
                    strokeLinejoin="round"
                    vectorEffect="non-scaling-stroke"
                  />

                  {REGIONS.filter((r) => LABELED.has(r.key)).map((r) => (
                    <text
                      key={r.key}
                      x={r.cx}
                      y={r.cy}
                      textAnchor="middle"
                      className="pointer-events-none fill-foreground stroke-background text-[9px] font-semibold [paint-order:stroke]"
                      strokeWidth={2.4}
                      strokeLinejoin="round"
                    >
                      {r.name}
                    </text>
                  ))}
                </>
              ) : (
                <>
                  {districts.map((d) => {
                    const { x, y } = geoToSvg(
                      d.latitude,
                      d.longitude,
                      TUNISIA_GEO.w,
                      TUNISIA_GEO.h,
                    );
                    const selected =
                      band === 'p10'
                        ? d.forecast_p10
                        : band === 'p90'
                          ? d.forecast_p90
                          : d.forecast_p50;
                    const sv =
                      d.capacity_mw > 0 ? selected / d.capacity_mw : 0;
                    const isSel = selKey === d.district_name;

                    return (
                      <circle
                        key={d.district_id}
                        cx={x}
                        cy={y}
                        r={isSel ? 5.5 : 3.5}
                        fill={fillFor(sv)}
                        stroke="hsl(var(--background))"
                        strokeWidth={1}
                        className="cursor-pointer transition-all"
                        onClick={() => setSelKey(d.district_name)}
                        onPointerEnter={(e) =>
                          onMapMove(
                            e as unknown as RPointerEvent<SVGPathElement>,
                            d.district_name,
                          )
                        }
                        onPointerMove={(e) =>
                          onMapMove(
                            e as unknown as RPointerEvent<SVGPathElement>,
                            d.district_name,
                          )
                        }
                        onPointerLeave={() => {
                          setHoverKey(null);
                          setTip(null);
                        }}
                      />
                    );
                  })}
                </>
              )}
            </svg>

            {/* Tooltip: region */}
            {hovered && tip && mapMode === 'region' && (() => {
              const snap = hovered.snap;
              if (!snap) return null;
              return (
                <div
                  className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[120%] whitespace-nowrap rounded-lg border border-border/70 bg-card/95 px-3 py-2 text-xs shadow-xl backdrop-blur-md"
                  style={{ left: tip.x, top: tip.y }}
                >
                  <b className="block font-semibold">{hovered.r.name}</b>
                  <span className="block text-muted-foreground text-2xs">
                    {hovered.prosolRegion} region
                  </span>
                  <span className="text-muted-foreground">
                    P10 {fmt(snap.regional_mw_p10, 1)} · P50{' '}
                    {fmt(snap.regional_mw_p50, 1)} · P90{' '}
                    {fmt(snap.regional_mw_p90, 1)} MW
                  </span>
                </div>
              );
            })()}

            {/* Tooltip: district */}
            {hoverKey && tip && mapMode === 'district' && (() => {
              const hd = districtByName.get(hoverKey);
              if (!hd) return null;
              return (
                <div
                  className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[120%] whitespace-nowrap rounded-lg border border-border/70 bg-card/95 px-3 py-2 text-xs shadow-xl backdrop-blur-md"
                  style={{ left: tip.x, top: tip.y }}
                >
                  <b className="block font-semibold">{hd.district_name}</b>
                  <span className="text-muted-foreground">
                    P10 {fmt(hd.forecast_p10, 2)} · P50{' '}
                    {fmt(hd.forecast_p50, 2)} · P90{' '}
                    {fmt(hd.forecast_p90, 2)} MW
                  </span>
                  <span className="block text-muted-foreground mt-0.5">
                    {hd.region_name}
                  </span>
                </div>
              );
            })()}
          </div>

          {/* Legend */}
          <div className="mt-4">
            <p className="mb-2 text-2xs text-muted-foreground">
              Utilization ({BAND_LABEL[band]} / capacity)
            </p>
            <div
              className="h-2 rounded-full"
              style={{
                background: `linear-gradient(90deg, ${fillFor(0.35)}, ${fillFor(0.75)})`,
              }}
            />
            <div className="mt-1.5 flex justify-between text-2xs tabular-nums text-muted-foreground">
              <span>35%</span>
              <span>75%</span>
            </div>
          </div>
        </div>

        {/* Right panel — selected detail */}
        <div className="min-w-0">
          {/* Region detail */}
          {mapMode === 'region' && selRegionData && (
            <div>
              <div className="flex items-center justify-between gap-3 mb-1">
                <h3 className="text-base font-semibold text-foreground">
                  {selGovernorateName}
                </h3>
                <span className="text-2xs text-muted-foreground font-tabular">
                  {hourLabel(hour)} · {HORIZON_LABEL[horizon]}
                </span>
              </div>
              <p className="text-2xs text-muted-foreground mb-3">
                Prosol region: {selRegionData.region_name} ·{' '}
                {selRegionData.n_districts} districts
              </p>

              {/* P10 / P50 / P90 cards */}
              <div className="grid grid-cols-3 gap-3 mb-4">
                <BandCard
                  label={COPY.region.p10}
                  value={fmt(selRegionData.regional_mw_p10, 1)}
                  unit="MW"
                  tone="low"
                  active={band === 'p10'}
                  onClick={() => setBand('p10')}
                />
                <BandCard
                  label={COPY.region.p50}
                  value={fmt(selRegionData.regional_mw_p50, 1)}
                  unit="MW"
                  tone="mid"
                  active={band === 'p50'}
                  onClick={() => setBand('p50')}
                />
                <BandCard
                  label={COPY.region.p90}
                  value={fmt(selRegionData.regional_mw_p90, 1)}
                  unit="MW"
                  tone="high"
                  active={band === 'p90'}
                  onClick={() => setBand('p90')}
                />
              </div>

              <dl className="grid grid-cols-2 gap-x-6 gap-y-3">
                <StatBlock
                  label={COPY.region.cap}
                  value={`${fmt(selRegionData.capacity_mw, 1)} MWp`}
                />
                <StatBlock
                  label={COPY.region.util}
                  value={`${(
                    (selRegionData.regional_mw_p50 /
                      Math.max(selRegionData.capacity_mw, 0.001)) *
                    100
                  ).toFixed(1)} %`}
                />
                <StatBlock
                  label={COPY.region.districts}
                  value={`${selRegionData.n_districts}`}
                />
                <StatBlock
                  label="Interval width"
                  value={`${fmt(
                    selRegionData.regional_mw_p90 -
                      selRegionData.regional_mw_p10,
                    1,
                  )} MW`}
                />
              </dl>
            </div>
          )}

          {mapMode === 'region' && !selRegionData && (
            <p className="text-xs text-muted-foreground">
              No data for {selGovernorateName}.
            </p>
          )}

          {/* District detail */}
          {mapMode === 'district' && selDistrict && (
            <div>
              <div className="flex items-center justify-between gap-3 mb-3">
                <h3 className="text-base font-semibold text-foreground">
                  {selDistrict.district_name}
                </h3>
                <span className="text-2xs text-muted-foreground font-tabular">
                  {selDistrict.region_name} · {HORIZON_LABEL[horizon]}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-3 mb-4">
                <BandCard
                  label={COPY.district.p10}
                  value={fmt(selDistrict.forecast_p10, 2)}
                  unit="MW"
                  tone="low"
                  active={band === 'p10'}
                  onClick={() => setBand('p10')}
                />
                <BandCard
                  label={COPY.district.p50}
                  value={fmt(selDistrict.forecast_p50, 2)}
                  unit="MW"
                  tone="mid"
                  active={band === 'p50'}
                  onClick={() => setBand('p50')}
                />
                <BandCard
                  label={COPY.district.p90}
                  value={fmt(selDistrict.forecast_p90, 2)}
                  unit="MW"
                  tone="high"
                  active={band === 'p90'}
                  onClick={() => setBand('p90')}
                />
              </div>

              <dl className="grid grid-cols-2 gap-x-6 gap-y-3">
                <StatBlock
                  label={COPY.district.cap}
                  value={`${fmt(selDistrict.capacity_mw, 2)} MW`}
                />
                <StatBlock
                  label={COPY.district.util}
                  value={`${(selDistrict.utilization * 100).toFixed(1)} %`}
                />
                {selDistrict.temperature_2m_c !== null && (
                  <StatBlock
                    label="Temperature"
                    value={`${fmt(selDistrict.temperature_2m_c, 1)} °C`}
                  />
                )}
                {selDistrict.cloud_cover_fraction !== null && (
                  <StatBlock
                    label="Cloud cover"
                    value={`${Math.round(
                      selDistrict.cloud_cover_fraction * 100,
                    )} %`}
                  />
                )}
              </dl>
            </div>
          )}

          {mapMode === 'district' && !selDistrict && (
            <p className="text-xs text-muted-foreground">
              Click a district on the map.
            </p>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center gap-3 border-t border-border px-5 py-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="rounded-full"
          onClick={() => setPlaying((p) => !p)}
        >
          {playing ? COPY.pause : COPY.play}
        </Button>

        <input
          id="grid-hour"
          type="range"
          min={0}
          max={23}
          step={1}
          value={hour}
          onChange={(e) => {
            setPlaying(false);
            setHour(Number(e.target.value));
          }}
          className="h-5 flex-1 cursor-pointer appearance-none bg-transparent"
        />

        <output
          htmlFor="grid-hour"
          className="min-w-[3.7ch] text-right text-sm font-bold tabular-nums text-foreground"
        >
          {hourLabel(hour)}
        </output>
      </div>
    </div>
  );
}

/* ============================================================
   Sub-components
   ============================================================ */

function BandCard({
  label,
  value,
  unit,
  tone,
  active,
  onClick,
}: {
  label: string;
  value: string;
  unit: string;
  tone: 'low' | 'mid' | 'high';
  active: boolean;
  onClick: () => void;
}) {
  const toneClass =
    tone === 'low'
      ? 'border-blue-500/30 text-blue-500'
      : tone === 'mid'
        ? 'border-primary/40 text-primary'
        : 'border-amber-500/30 text-amber-500';

  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-lg border p-3 text-left transition-all',
        active
          ? 'bg-foreground/5 ring-1 ring-foreground/20'
          : 'bg-muted/20 hover:bg-muted/40',
        toneClass,
      )}
    >
      <p className="text-2xs uppercase tracking-wider opacity-70">{label}</p>
      <p className="mt-1 text-base font-bold tabular-nums">
        {value}
        <span className="ml-1 text-2xs font-medium opacity-70">{unit}</span>
      </p>
    </button>
  );
}

function StatBlock({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-2xs font-semibold uppercase text-muted-foreground">
        {label}
      </dt>
      <dd className="text-sm font-bold tabular-nums text-foreground">
        {value}
      </dd>
    </div>
  );
}