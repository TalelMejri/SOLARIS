'use client';

import React, { useEffect, useState, useMemo } from 'react';
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { RefreshCw, AlertCircle, Activity } from 'lucide-react';

/* ============================================================
   API
   ============================================================ */

const API_URL =
  'http://localhost:5000';

/* ============================================================
   Types
   ============================================================ */

type Horizon = 'h12' | 'h24' | 'h72';

interface QuantilePoint {
  time: string;
  national_p10: number;
  national_p50: number;
  national_p90: number;
  national_true: number;
  capacity_mw: number;
}

interface QuantileResponse {
  horizon: string;
  window_start: string;
  window_end: string;
  points: QuantilePoint[];
}

interface ChartPoint {
  time: string;
  fullLabel: string;
  p10: number;
  p50: number;
  p90: number;
  actual: number | null;
  band: number;
}

const HORIZON_LABEL: Record<Horizon, string> = {
  h12: 'H+12',
  h24: 'H+24',
  h72: 'H+72',
};

/* ============================================================
   Tooltip
   ============================================================ */

const CustomTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) => {
  if (!active || !payload?.length) return null;

  const p10 = payload.find((p) => p.name === 'p10')?.value ?? 0;
  const p50 = payload.find((p) => p.name === 'p50')?.value ?? 0;
  const p90 = payload.find((p) => p.name === 'p90')?.value ?? 0;
  const actual = payload.find((p) => p.name === 'actual')?.value;

  const width = p90 - p10;

  return (
    <div className="bg-card border border-border rounded-lg p-3 shadow-xl text-xs space-y-1.5 min-w-[190px]">
      <p className="font-semibold text-foreground border-b border-border pb-1.5">
        {label}
      </p>

      <div className="flex justify-between gap-4">
        <span className="text-muted-foreground">P50 forecast</span>
        <span className="font-tabular font-semibold text-primary">
          {p50.toFixed(1)} MW
        </span>
      </div>

      <div className="flex justify-between gap-4">
        <span className="text-muted-foreground">P10 – P90</span>
        <span className="font-tabular text-muted-foreground">
          {p10.toFixed(1)} – {p90.toFixed(1)}
        </span>
      </div>

      <div className="flex justify-between gap-4">
        <span className="text-muted-foreground">Interval width</span>
        <span className="font-tabular text-foreground">
          {width.toFixed(1)} MW
        </span>
      </div>

      {actual !== undefined && actual !== null && (
        <div className="flex justify-between gap-4 pt-1 border-t border-border">
          <span className="text-muted-foreground">Actual</span>
          <span className="font-tabular font-semibold text-accent">
            {actual.toFixed(1)} MW
          </span>
        </div>
      )}
    </div>
  );
};

/* ============================================================
   Main Component
   ============================================================ */

export default function FrequencyChart() {
  const [horizon, setHorizon] = useState<Horizon>('h12');
  const [raw, setRaw] = useState<QuantileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        const url = new URL(`${API_URL}/api/forecast/national/quantile`);
        url.searchParams.set('horizon', horizon);
        url.searchParams.set('start', '2022-07-01');
        url.searchParams.set('end', '2022-07-05');

        console.log('[FrequencyChart] fetching:', url.toString());

        const res = await fetch(url.toString());
        if (!res.ok) throw new Error(`API ${res.status}`);

        const json: QuantileResponse = await res.json();

        console.log(
          '[FrequencyChart] received points:',
          json.points?.length ?? 0,
        );
        if (json.points?.[0]) {
          console.log('[FrequencyChart] first point:', json.points[0]);
          console.log('[FrequencyChart] second point:', json.points[1]);
        }

        if (!cancelled) {
          setRaw(json);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : 'Fetch failed';
          console.error('[FrequencyChart] fetch failed:', msg);
          setError(msg);
          setLoading(false);
        }
      }
    };

    fetchData();
    return () => {
      cancelled = true;
    };
  }, [horizon]);

  const chartData = useMemo<ChartPoint[]>(() => {
    if (!raw?.points || raw.points.length === 0) return [];

    return raw.points.map((p, idx) => {
      const d = new Date(p.time);
      const localHour = (d.getUTCHours() + 1) % 24;
      const label = `${String(localHour).padStart(2, '0')}:00`;
      const dayOffset = Math.floor(idx / 2);
      const dayLabel =
        dayOffset === 0
          ? 'Today'
          : dayOffset === 1
            ? 'Tomorrow'
            : `D+${dayOffset}`;

      const actual =
        typeof p.national_true === 'number' && p.national_true >= 0
          ? p.national_true
          : null;

      return {
        time: label,
        fullLabel: `${dayLabel} ${label}`,
        p10: parseFloat(p.national_p10.toFixed(1)),
        p50: parseFloat(p.national_p50.toFixed(1)),
        p90: parseFloat(p.national_p90.toFixed(1)),
        actual: actual !== null ? parseFloat(actual.toFixed(1)) : null,
        band: parseFloat((p.national_p90 - p.national_p10).toFixed(1)),
      };
    });
  }, [raw]);

  const ticks = chartData.map((d) => d.fullLabel);

  /* ---------- Debug summary ---------- */
  const debugInfo = useMemo(() => {
    if (chartData.length === 0) return null;
    const peak = Math.max(...chartData.map((d) => d.p50));
    const min = Math.min(...chartData.map((d) => d.p50));
    return { count: chartData.length, peak, min };
  }, [chartData]);

  /* ---------- Loading ---------- */
  if (loading) {
    return (
      <div className="card-elevated p-5">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw size={14} className="animate-spin" />
          Loading national forecast…
        </div>
      </div>
    );
  }

  /* ---------- Error ---------- */
  if (error || !chartData.length) {
    return (
      <div className="card-elevated p-5">
        <div className="flex items-start gap-2 text-sm text-[var(--status-critical)]">
          <AlertCircle size={14} className="mt-0.5" />
          <div>
            <p className="font-semibold">Failed to load forecast</p>
            <p className="text-xs text-muted-foreground mt-1">
              {error ?? 'No data returned from API'}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Backend: <code>{API_URL}</code>
            </p>
          </div>
        </div>
      </div>
    );
  }

  /* ---------- Render ---------- */
  return (
    <div className="card-elevated p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Activity size={13} className="text-primary" />
            National Rooftop PV Forecast
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            P10 / P50 / P90 · ECMWF TIGGE · verified test set 2022 ·{' '}
            {debugInfo?.count} points · peak {debugInfo?.peak.toFixed(0)} MW
          </p>
        </div>

        <div className="flex items-center gap-1">
          {(['h12', 'h24', 'h72'] as Horizon[]).map((h) => (
            <button
              key={h}
              onClick={() => setHorizon(h)}
              className={`text-xs font-medium px-2.5 py-1 rounded-lg transition-all ${horizon === h
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
                }`}
            >
              {HORIZON_LABEL[h]}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart
          data={chartData}
          margin={{ top: 8, right: 4, bottom: 0, left: 0 }}
        >
          <defs>
            <linearGradient id="gradBand" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="5%"
                stopColor="var(--chart-primary)"
                stopOpacity={0.2}
              />
              <stop
                offset="95%"
                stopColor="var(--chart-primary)"
                stopOpacity={0.05}
              />
            </linearGradient>
          </defs>

          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--border)"
            vertical={false}
          />

          <XAxis
            dataKey="fullLabel"
            tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />

          <YAxis
            tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `${v}`}
            width={40}
            label={{
              value: 'MW',
              angle: -90,
              position: 'insideLeft',
              style: {
                fontSize: 10,
                fill: 'var(--muted-foreground)',
              },
            }}
          />

          <Tooltip content={<CustomTooltip />} />

          <Legend
            wrapperStyle={{ fontSize: 10, paddingTop: 8 }}
            iconType="line"
            iconSize={10}
          />

          {/* P10–P90 band */}
          <Area
            type="monotone"
            dataKey="p90"
            stroke="none"
            fill="url(#gradBand)"
            name="P90"
          />
          <Area
            type="monotone"
            dataKey="p10"
            stroke="none"
            fill="hsl(var(--background))"
            name="P10"
          />

          {/* P50 forecast */}
          <Line
            type="monotone"
            dataKey="p50"
            stroke="var(--chart-primary)"
            strokeWidth={2.5}
            dot={{ r: 3, fill: 'var(--chart-primary)' }}
            activeDot={{ r: 4, fill: 'var(--chart-primary)', strokeWidth: 0 }}
            name="P50"
          />

          {/* Actual */}
          <Line
            type="monotone"
            dataKey="actual"
            stroke="var(--chart-accent, #2dd4aa)"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            dot={{ r: 2, fill: 'var(--chart-accent, #2dd4aa)' }}
            name="Actual"
            connectNulls={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Footer */}
      <p className="text-2xs text-muted-foreground mt-3 pt-3 border-t border-border">
        Source: LightGBM quantile models trained on ECMWF TIGGE NWP forecasts ·
        50 districts aggregated to national · verified on untouched 2022 test set
      </p>
    </div>
  );
}