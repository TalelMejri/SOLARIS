'use client';

import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { Hud } from './solar_hero';
import { MODES, type CloudMode } from './solar';

/* ============================================================
   API
   ============================================================ */

const API_URL =
  'http://localhost:5000';

/* ============================================================
   Chart geometry
   ============================================================ */

const CW = 400;
const BASE = 96;
const TOP = 8;

// Chart Y scale is set dynamically from the data
const X = (t: number) => t * CW;

const TICKS: { x: number; label: string; anchor: 'start' | 'middle' }[] = [
  { x: 0, label: '06:00', anchor: 'start' },
  { x: 118.5, label: '09:00', anchor: 'middle' },
  { x: 207.4, label: '12:00', anchor: 'middle' },
  { x: 296.3, label: '15:00', anchor: 'middle' },
  { x: 385.2, label: '18:00', anchor: 'middle' },
];

/* ============================================================
   Types
   ============================================================ */

interface QuantilePoint {
  time: string;
  national_p10: number;
  national_p50: number;
  national_p90: number;
  capacity_mw: number;
}

interface ForecastDockProps {
  hud: Hud;
  mode: CloudMode;
  playing: boolean;
  onMode: (m: CloudMode) => void;
  onPlaying: (p: boolean) => void;
  onTime: (t: number) => void;
  className?: string;
}

/* ============================================================
   Helpers
   ============================================================ */

const fmt = (n: number, digits = 1) =>
  Number.isFinite(n)
    ? n.toLocaleString('en-US', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
    : '—';

/* ============================================================
   Component
   ============================================================ */

export function ForecastDock({
  hud,
  mode,
  playing,
  onMode,
  onPlaying,
  onTime,
  className,
}: ForecastDockProps) {
  const [points, setPoints] = useState<QuantilePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* ---------- Fetch real quantile forecast ---------- */
  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        const url = new URL(`${API_URL}/api/forecast/national/quantile`);
        url.searchParams.set('horizon', 'h12');
        url.searchParams.set('start', '2022-07-01');
        url.searchParams.set('end', '2022-07-05');

        const res = await fetch(url.toString());
        if (!res.ok) throw new Error(`API ${res.status}`);

        const json = await res.json();
        const raw: QuantilePoint[] = json.points ?? [];

        // Convert UTC → Africa/Tunis (UTC+1) and sort by local hour
        const converted = raw
          .map((p) => {
            const d = new Date(p.time);
            const localHour = (d.getUTCHours() + 1) % 24;
            return {
              ...p,
              localHour,
              timeMs: d.getTime(),
            };
          })
          .filter((p) => p.localHour >= 6 && p.localHour <= 20) // daytime only
          .sort((a, b) => a.timeMs - b.timeMs);

        if (!cancelled) {
          setPoints(converted);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Fetch failed');
          setLoading(false);
        }
      }
    };

    fetchData();
    return () => {
      cancelled = true;
    };
  }, []);

  /* ---------- Compute Y scale from data ---------- */
  const yScale = useMemo(() => {
    const maxValue = points.reduce(
      (max, p) => Math.max(max, p.national_p90),
      100,
    );
    return (v: number) => BASE - (v / (maxValue * 1.06)) * (BASE - TOP);
  }, [points]);

  /* ---------- Build chart paths ---------- */
  const { median, band, peakP50 } = useMemo(() => {
    if (!points.length) return { median: '', band: '', peakP50: 0 };

    const N = points.length;
    let med = '';
    let up = '';
    const lo: string[] = [];
    let peak = 0;

    for (let i = 0; i < N; i++) {
      const p = points[i];
      // Normalize x to 0..1 across the daytime window
      const t = i / Math.max(1, N - 1);
      const x = X(t).toFixed(1);

      med += `${i ? 'L' : 'M'}${x} ${yScale(p.national_p50).toFixed(1)}`;
      up += `${i ? 'L' : 'M'}${x} ${yScale(p.national_p90).toFixed(1)}`;
      lo.push(`L${x} ${yScale(p.national_p10).toFixed(1)}`);

      if (p.national_p50 > peak) peak = p.national_p50;
    }

    return {
      median: med,
      band: `${up}${lo.reverse().join('')}Z`,
      peakP50: peak,
    };
  }, [points, yScale]);

  /* ---------- Current values at hud.t ---------- */
  const current = useMemo(() => {
    if (!points.length) {
      return { p10: 0, p50: 0, p90: 0, label: '—' };
    }
    const idx = Math.round(hud.t * (points.length - 1));
    const clampedIdx = Math.max(0, Math.min(points.length - 1, idx));
    const p = points[clampedIdx];

    const localDate = new Date(new Date(p.time).getTime() + 60 * 60 * 1000);
    const hourLabel = `${String(localDate.getUTCHours()).padStart(2, '0')}:${String(
      localDate.getUTCMinutes(),
    ).padStart(2, '0')}`;

    return {
      p10: p.national_p10,
      p50: p.national_p50,
      p90: p.national_p90,
      label: hourLabel,
    };
  }, [points, hud.t]);

  /* ---------- Cursor position ---------- */
  const cursorX = X(hud.t);
  const cursorY = yScale(current.p50);

  /* ---------- Loading ---------- */
  if (loading) {
    return (
      <aside
        aria-label="Live forecast demonstration"
        className={cn(
          'rounded-[22px] border border-white/20 bg-[#091c3a]/60 p-4 text-white shadow-2xl backdrop-blur-xl',
          className,
        )}
      >
        <p className="text-sm text-white/80">Loading real forecast…</p>
      </aside>
    );
  }

  /* ---------- Error ---------- */
  if (error || !points.length) {
    return (
      <aside
        aria-label="Live forecast demonstration"
        className={cn(
          'rounded-[22px] border border-white/20 bg-[#091c3a]/60 p-4 text-white shadow-2xl backdrop-blur-xl',
          className,
        )}
      >
        <p className="text-sm text-amber-300">
          Forecast unavailable{error ? `: ${error}` : ''}
        </p>
        <p className="mt-1 text-xs text-white/70">
          Backend must be running on {API_URL}
        </p>
      </aside>
    );
  }

  /* ---------- Render ---------- */
  return (
    <aside
      aria-label="National rooftop PV forecast"
      className={cn(
        'rounded-[22px] border border-white/20 bg-[#091c3a]/60 p-4 pb-3.5 text-white shadow-[0_24px_60px_-24px_rgba(3,10,26,0.6)] backdrop-blur-xl backdrop-saturate-150 dark:bg-[#051024]/70',
        className,
      )}
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold tracking-tight text-white/90">
            National Rooftop PV · H+12
          </p>
          <p className="mt-0.5 text-2xs text-white/60">
            Real model output · 50 districts · ECMWF TIGGE
          </p>
        </div>

        <div
          role="radiogroup"
          aria-label="Display mode"
          className="inline-flex gap-0.5 rounded-full bg-white/10 p-[3px]"
        >
          {MODES.map((m, i) => (
            <button
              key={m.label}
              type="button"
              role="radio"
              aria-checked={mode === i}
              onClick={() => onMode(i as CloudMode)}
              className={cn(
                'rounded-full px-3 py-2 text-[0.8rem] font-semibold leading-none transition-all duration-200',
                mode === i
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-white/80 hover:bg-white/10 hover:text-white',
              )}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Numeric readouts */}
      <div className="mb-1 mt-3.5 grid grid-cols-3 gap-3">
        <div>
          <p className="mb-0.5 text-xs text-white/75">Time</p>
          <p className="text-2xl font-bold leading-tight tracking-tight tabular-nums">
            {current.label}
          </p>
        </div>
        <div>
          <p className="mb-0.5 text-xs text-white/75">Forecast P50</p>
          <p className="text-2xl font-bold leading-tight tracking-tight tabular-nums">
            {fmt(current.p50, 1)}
            <small className="ml-1 text-[0.8rem] font-semibold text-white/75">
              MW
            </small>
          </p>
        </div>
        <div>
          <p className="mb-0.5 text-xs text-white/75">Peak P50</p>
          <p className="text-2xl font-bold leading-tight tracking-tight tabular-nums">
            {fmt(peakP50, 1)}
            <small className="ml-1 text-[0.8rem] font-semibold text-white/75">
              MW
            </small>
          </p>
          <p className="mt-0.5 text-xs tabular-nums text-white/75">
            P10–P90: {fmt(current.p10, 0)}–{fmt(current.p90, 0)}
          </p>
        </div>
      </div>

      {/* Chart */}
      <svg
        viewBox="0 0 400 118"
        role="img"
        aria-label="National PV forecast with P10–P90 band"
        className="mx-[9px] mt-0.5 block h-auto w-[calc(100%-18px)] overflow-visible"
      >
        <defs>
          <linearGradient id="bandGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(255,182,39,.45)" />
            <stop offset="100%" stopColor="rgba(255,182,39,.12)" />
          </linearGradient>
        </defs>

        <line
          x1="0"
          y1={BASE}
          x2={CW}
          y2={BASE}
          stroke="rgba(255,255,255,.28)"
        />

        {/* Band + P50 */}
        <g key={mode}>
          <path d={band} fill="url(#bandGrad)" />
          <path
            d={median}
            fill="none"
            stroke="#FFB627"
            strokeWidth={2}
            strokeLinejoin="round"
          />
        </g>

        {/* Cursor */}
        <line
          x1={cursorX}
          x2={cursorX}
          y1="6"
          y2={BASE}
          stroke="rgba(255,255,255,.45)"
          strokeDasharray="3 3"
        />
        <circle
          cx={cursorX}
          cy={cursorY}
          r="5.5"
          fill="#fff"
          stroke="#FFB627"
          strokeWidth={3}
          className="drop-shadow-[0_0_6px_rgba(255,182,39,.6)]"
        />

        {TICKS.map((tk) => (
          <text
            key={tk.label}
            x={tk.x}
            y="112"
            textAnchor={tk.anchor}
            fill="rgba(244,248,252,.78)"
            fontSize="10"
            fontWeight={500}
          >
            {tk.label}
          </text>
        ))}
      </svg>

      {/* Slider */}
      <input
        type="range"
        min={0}
        max={1000}
        step={4}
        value={Math.round(hud.t * 1000)}
        onChange={(e) => onTime(Number(e.target.value) / 1000)}
        aria-label="Time of day"
        className={cn(
          'block h-6 w-full cursor-pointer appearance-none bg-transparent focus-visible:outline-none',
          '[&::-webkit-slider-runnable-track]:h-1 [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-white/30',
          '[&::-webkit-slider-thumb]:-mt-[7px] [&::-webkit-slider-thumb]:h-[18px] [&::-webkit-slider-thumb]:w-[18px] [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-[3px] [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:bg-amber-400 [&::-webkit-slider-thumb]:shadow-md',
          '[&::-moz-range-track]:h-1 [&::-moz-range-track]:rounded-full [&::-moz-range-track]:bg-white/30',
          '[&::-moz-range-thumb]:h-3 [&::-moz-range-thumb]:w-3 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-[3px] [&::-moz-range-thumb]:border-white [&::-moz-range-thumb]:bg-amber-400',
        )}
      />

      {/* Footer */}
      <div className="mt-0.5 flex items-center justify-between gap-3">
        <p className="text-xs leading-snug text-white/75">
          Verified LightGBM model · 50 districts aggregated to national
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPlaying(!playing)}
          className="shrink-0 rounded-full border-white/40 bg-white/5 text-white transition-all duration-200 hover:-translate-y-0.5 hover:border-white hover:bg-white/15 hover:text-white"
        >
          {playing ? 'Pause' : 'Play day'}
        </Button>
      </div>
    </aside>
  );
}