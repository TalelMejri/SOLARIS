'use client';

import { useState, useEffect, useMemo } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { Clock, RefreshCw, AlertCircle } from 'lucide-react';

type Horizon = 'h12' | 'h24' | 'h72';

/* ============================================================
   API
   ============================================================ */

const API_URL =
  'http://localhost:5000';

/* ============================================================
   Types — matching the real quantile endpoint
   ============================================================ */

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
  forecast: number;   // P50
  ciUpper: number;    // P90
  ciLower: number;    // P10
  actual: number | null;
  capacity: number;
  hourIndex: number;
}

/* ============================================================
   Horizon labels
   ============================================================ */

const HORIZON_LABEL: Record<Horizon, string> = {
  h12: 'H+12',
  h24: 'H+24',
  h72: 'H+72',
};

/* ============================================================
   Custom Tooltip
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

  const forecast = payload.find((p) => p.name === 'forecast')?.value ?? 0;
  const ciUpper = payload.find((p) => p.name === 'ciUpper')?.value ?? 0;
  const ciLower = payload.find((p) => p.name === 'ciLower')?.value ?? 0;
  const actual = payload.find((p) => p.name === 'actual')?.value;

  const band = Math.max(0, ciUpper - ciLower);

  return (
    <div className="bg-card border border-border rounded-lg p-3 shadow-xl text-xs space-y-1.5 min-w-[200px]">
      <p className="font-semibold text-foreground border-b border-border pb-1.5">
        {label}
      </p>

      <div className="flex justify-between gap-4">
        <span className="text-muted-foreground">Forecast P50</span>
        <span className="font-tabular font-semibold text-primary">
          {forecast.toFixed(1)} MW
        </span>
      </div>

      <div className="flex justify-between gap-4">
        <span className="text-muted-foreground">P10 – P90</span>
        <span className="font-tabular text-muted-foreground">
          {ciLower.toFixed(1)} – {ciUpper.toFixed(1)} MW
        </span>
      </div>

      <div className="flex justify-between gap-4">
        <span className="text-muted-foreground">Interval width</span>
        <span className="font-tabular text-foreground">
          {band.toFixed(1)} MW
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

export default function ForecastChart() {
  const [horizon, setHorizon] = useState<Horizon>('h12');
  const [rawData, setRawData] = useState<QuantileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchForecast = async () => {
      setLoading(true);
      setError(null);

      try {
        const url = new URL(`${API_URL}/api/forecast/national/quantile`);
        url.searchParams.set('horizon', horizon);
        url.searchParams.set('start', '2022-07-01');
        url.searchParams.set('end', '2022-07-05');

        const res = await fetch(url.toString());
        if (!res.ok) {
          throw new Error(`API returned ${res.status}`);
        }

        const json: QuantileResponse = await res.json();
        if (!cancelled) {
          setRawData(json);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Fetch failed');
          setLoading(false);
        }
      }
    };

    fetchForecast();
    return () => {
      cancelled = true;
    };
  }, [horizon]);

  /* ---------- Transform API → chart points ---------- */

  const chartData = useMemo<ChartPoint[]>(() => {
    if (!rawData?.points) return [];

    return rawData.points.map((p, idx) => {
      const d = new Date(p.time);

      // Convert UTC → Africa/Tunis (UTC+1, no DST)
      const localHour = (d.getUTCHours() + 1) % 24;
      const label = `${String(localHour).padStart(2, '0')}:00`;

      // Two samples per day (00 and 12 UTC)
      const dayOffset = Math.floor(idx / 2);
      const dayLabel =
        dayOffset === 0
          ? 'Today'
          : dayOffset === 1
            ? 'Tomorrow'
            : `D+${dayOffset}`;

      // Real quantiles from trained and calibrated models
      const forecast = p.national_p50 ?? 0;
      const ciLower = p.national_p10 ?? 0;
      const ciUpper = p.national_p90 ?? 0;

      // Actual only shown for test period observations
      const actual =
        typeof p.national_true === 'number' && p.national_true >= 0
          ? p.national_true
          : null;

      return {
        time: label,
        fullLabel: `${dayLabel} ${label}`,
        forecast: parseFloat(forecast.toFixed(1)),
        ciUpper: parseFloat(ciUpper.toFixed(1)),
        ciLower: parseFloat(ciLower.toFixed(1)),
        actual: actual !== null ? parseFloat(actual.toFixed(1)) : null,
        capacity: p.capacity_mw ?? 515.1,
        hourIndex: idx,
      };
    });
  }, [rawData]);

  /* ---------- Stats ---------- */

  const stats = useMemo(() => {
    if (!chartData.length) return null;

    const peak = Math.max(...chartData.map((d) => d.forecast));
    const mean =
      chartData.reduce((s, d) => s + d.forecast, 0) / chartData.length;
    const capacity = chartData[0].capacity;

    // Mean interval width
    const meanWidth =
      chartData.reduce((s, d) => s + (d.ciUpper - d.ciLower), 0) /
      chartData.length;

    return {
      peak,
      mean,
      capacity,
      peakCF: capacity > 0 ? peak / capacity : 0,
      meanWidth,
    };
  }, [chartData]);

  const ticks = chartData
    .filter((d) => d.hourIndex % 4 === 0)
    .map((d) => d.fullLabel);

  /* ---------- Loading ---------- */

  if (loading) {
    return (
      <div className="card-elevated p-5">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw size={14} className="animate-spin" />
          Loading forecast from API…
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
            <p className="text-xs text-muted-foreground mt-1">{error}</p>
            <p className="text-xs text-muted-foreground mt-1">
              Ensure the FastAPI backend is running on {API_URL}
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
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div>
          <h2 className="text-sm font-semibold text-foreground">
            Rooftop Solar Forecast · National
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            ECMWF TIGGE NWP · Trained quantile P10 / P50 / P90
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Clock size={13} className="text-muted-foreground" />
          {(['h12', 'h24', 'h72'] as Horizon[]).map((h) => (
            <button
              key={h}
              onClick={() => setHorizon(h)}
              className={`text-xs font-medium px-3 py-1.5 rounded-lg transition-all duration-150 active:scale-95 ${
                horizon === h
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:text-foreground hover:bg-muted/80'
              }`}
            >
              {HORIZON_LABEL[h]}
            </button>
          ))}
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
          <StatCard
            label="Peak P50"
            value={stats.peak.toFixed(0)}
            unit="MW"
          />
          <StatCard
            label="Mean P50"
            value={stats.mean.toFixed(0)}
            unit="MW"
          />
          <StatCard
            label="Installed"
            value={stats.capacity.toFixed(0)}
            unit="MW"
          />
          <StatCard
            label="Peak CF"
            value={(stats.peakCF * 100).toFixed(1)}
            unit="%"
          />
          <StatCard
            label="Mean interval"
            value={stats.meanWidth.toFixed(1)}
            unit="MW"
          />
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center gap-5 mb-4 text-xs text-muted-foreground flex-wrap">
        <span className="flex items-center gap-1.5">
          <span className="w-6 h-0.5 bg-primary rounded" />
          Forecast P50
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="w-6 h-2 rounded"
            style={{ background: 'rgba(45,212,170,0.15)' }}
          />
          P10 – P90 interval
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-6 h-0.5 bg-accent rounded" />
          Actual (test set)
        </span>
        <span className="flex items-center gap-1.5 ml-auto">
          <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
          Verified Phase 5.2 quantiles
        </span>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart
          data={chartData}
          margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
        >
          <defs>
            <linearGradient id="gradForecast" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--chart-primary)" stopOpacity={0.25} />
              <stop offset="95%" stopColor="var(--chart-primary)" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gradCI" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-primary)" stopOpacity={0.15} />
              <stop offset="100%" stopColor="var(--chart-primary)" stopOpacity={0.05} />
            </linearGradient>
          </defs>

          <CartesianGrid
            strokeDasharray="3 3"
            stroke="hsl(var(--border))"
            vertical={false}
          />

          <XAxis
            dataKey="fullLabel"
            ticks={ticks}
            tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
            axisLine={false}
            tickLine={false}
          />

          <YAxis
            tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
            axisLine={false}
            tickLine={false}
            width={36}
            tickFormatter={(v) => `${v}`}
          />

          <Tooltip content={<CustomTooltip />} />

          {/* Interval band (P10 lower bound in background color) */}
          <Area
            type="monotone"
            dataKey="ciUpper"
            stroke="none"
            fill="url(#gradCI)"
            name="ciUpper"
          />
          <Area
            type="monotone"
            dataKey="ciLower"
            stroke="none"
            fill="hsl(var(--background))"
            name="ciLower"
          />

          {/* P50 forecast line */}
          <Area
            type="monotone"
            dataKey="forecast"
            stroke="var(--chart-primary)"
            strokeWidth={2}
            fill="url(#gradForecast)"
            dot={false}
            activeDot={{ r: 4, fill: 'var(--chart-primary)', strokeWidth: 0 }}
            name="forecast"
          />

          {/* Actual observed (test set) */}
          <Area
            type="monotone"
            dataKey="actual"
            stroke="var(--chart-accent, #2dd4aa)"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            fill="none"
            dot={false}
            name="actual"
            connectNulls={false}
          />

          <ReferenceLine
            y={0}
            stroke="hsl(var(--muted-foreground))"
            strokeOpacity={0.3}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Footer */}
      <p className="text-2xs text-muted-foreground mt-4 pt-3 border-t border-border">
        Source: LightGBM quantile models trained on ECMWF TIGGE NWP forecasts
        (2018–2021). Calibrated on the first half of 2022 and verified on the
        untouched second half. Interval width is the trained P10–P90 interval,
        not a synthetic confidence band.
      </p>
    </div>
  );
}

/* ============================================================
   Stat Card
   ============================================================ */

function StatCard({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit: string;
}) {
  return (
    <div className="bg-muted/30 rounded-lg p-3 border border-border">
      <p className="text-2xs uppercase tracking-wider text-muted-foreground mb-1">
        {label}
      </p>
      <p className="text-lg font-tabular font-semibold text-foreground">
        {value}
        <span className="text-2xs text-muted-foreground ml-1">{unit}</span>
      </p>
    </div>
  );
}