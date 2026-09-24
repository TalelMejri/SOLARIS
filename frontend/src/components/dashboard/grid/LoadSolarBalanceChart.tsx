'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { RefreshCw, AlertCircle, Zap } from 'lucide-react';

import { loadNat } from '@/types/grid';

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
  capacity_mw: number;
}

interface QuantileResponse {
  horizon: string;
  points: QuantilePoint[];
}

interface ChartPoint {
  time: string;
  fullLabel: string;
  load: number;
  solar: number;
  solarP10: number;
  solarP90: number;
  thermal: number;
  share: number;
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

  const load = payload.find((p) => p.name === 'load')?.value ?? 0;
  const solar = payload.find((p) => p.name === 'solar')?.value ?? 0;
  const solarP10 = payload.find((p) => p.name === 'solarP10')?.value;
  const solarP90 = payload.find((p) => p.name === 'solarP90')?.value;
  const thermal = payload.find((p) => p.name === 'thermal')?.value ?? 0;

  const share = load > 0 ? (solar / load) * 100 : 0;

  return (
    <div className="bg-card border border-border rounded-lg p-3 shadow-xl text-xs space-y-1.5 min-w-[200px]">
      <p className="font-semibold text-foreground border-b border-border pb-1.5">
        {label}
      </p>

      <div className="flex justify-between gap-4">
        <span className="text-muted-foreground">Total load</span>
        <span className="font-tabular" style={{ color: 'var(--chart-blue)' }}>
          {load.toFixed(0)} MW
        </span>
      </div>

      <div className="flex justify-between gap-4">
        <span className="text-muted-foreground">Solar (P50)</span>
        <span
          className="font-tabular font-semibold"
          style={{ color: 'var(--chart-primary)' }}
        >
          {solar.toFixed(1)} MW
        </span>
      </div>

      {solarP10 !== undefined && solarP90 !== undefined && (
        <div className="flex justify-between gap-4 text-2xs pl-3">
          <span className="text-muted-foreground">P10 – P90</span>
          <span className="font-tabular text-muted-foreground">
            {solarP10.toFixed(1)} – {solarP90.toFixed(1)}
          </span>
        </div>
      )}

      <div className="flex justify-between gap-4">
        <span className="text-muted-foreground">Thermal / other</span>
        <span
          className="font-tabular"
          style={{ color: 'var(--chart-orange)' }}
        >
          {thermal.toFixed(0)} MW
        </span>
      </div>

      <div className="flex justify-between gap-4 pt-1 border-t border-border">
        <span className="text-muted-foreground">Solar share</span>
        <span className="font-tabular font-semibold text-primary">
          {share.toFixed(1)}%
        </span>
      </div>
    </div>
  );
};

/* ============================================================
   Main Component
   ============================================================ */

export default function LoadSolarBalanceChart() {
  const [horizon, setHorizon] = useState<Horizon>('h12');
  const [raw, setRaw] = useState<QuantileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* ---------- Fetch real solar forecast ---------- */
  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        const url = new URL(`${API_URL}/api/forecast/national/quantile`);
        url.searchParams.set('horizon', horizon);
        url.searchParams.set('start', '2022-07-01');
        url.searchParams.set('end', '2022-07-02');

        const res = await fetch(url.toString());
        if (!res.ok) throw new Error(`API ${res.status}`);

        const json: QuantileResponse = await res.json();
        if (!cancelled) {
          setRaw(json);
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
  }, [horizon]);

  /* ---------- Build chart points ---------- */
  const chartData = useMemo<ChartPoint[]>(() => {
    if (!raw?.points?.length) return [];

    return raw.points.map((p, idx) => {
      const d = new Date(p.time);
      const localHour = (d.getUTCHours() + 1) % 24;
      const label = `${String(localHour).padStart(2, '0')}:00`;

      // Load comes from the shape model (labeled synthetic)
      const load = loadNat(localHour);

      const solar = Math.max(0, p.national_p50);
      const solarP10 = Math.max(0, p.national_p10);
      const solarP90 = Math.max(0, p.national_p90);

      // Thermal = residual (load that solar doesn't cover)
      const thermal = Math.max(0, load - solar);

      const share = load > 0 ? solar / load : 0;

      return {
        time: label,
        fullLabel: label,
        load,
        solar: parseFloat(solar.toFixed(1)),
        solarP10: parseFloat(solarP10.toFixed(1)),
        solarP90: parseFloat(solarP90.toFixed(1)),
        thermal: parseFloat(thermal.toFixed(1)),
        share,
      };
    });
  }, [raw]);

  /* ---------- Peak share ---------- */
  const peakShare = useMemo(() => {
    if (!chartData.length) return 0;
    return Math.max(...chartData.map((d) => d.share)) * 100;
  }, [chartData]);

  /* ---------- Loading ---------- */
  if (loading) {
    return (
      <div className="card-elevated p-5">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw size={14} className="animate-spin" />
          Loading load-balance data…
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
            <p className="font-semibold">Failed to load balance chart</p>
            <p className="text-xs text-muted-foreground mt-1">{error}</p>
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
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Zap size={13} className="text-primary" />
            Grid Load vs Solar Injection
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            24-hour profile · MW · load curve is synthetic shape, solar is real model output
          </p>
        </div>

        <div className="flex items-center gap-1">
          {(['h12', 'h24', 'h72'] as Horizon[]).map((h) => (
            <button
              key={h}
              onClick={() => setHorizon(h)}
              className={`text-xs font-medium px-2.5 py-1 rounded-lg transition-all ${
                horizon === h
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              {HORIZON_LABEL[h]}
            </button>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-5 mb-4 text-xs text-muted-foreground flex-wrap">
        <span className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded-sm opacity-80"
            style={{ background: 'var(--chart-blue)' }}
          />
          Total Load (shape model)
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded-sm opacity-80"
            style={{ background: 'var(--chart-primary)' }}
          />
          Solar Injection (real model)
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded-sm opacity-80"
            style={{ background: 'var(--chart-orange)' }}
          />
          Thermal / Other
        </span>
        <span className="flex items-center gap-1.5 ml-auto text-primary">
          Peak solar share {peakShare.toFixed(1)}%
        </span>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart
          data={chartData}
          margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
        >
          <defs>
            <linearGradient id="gradLoad" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="5%"
                stopColor="var(--chart-blue)"
                stopOpacity={0.3}
              />
              <stop
                offset="95%"
                stopColor="var(--chart-blue)"
                stopOpacity={0.05}
              />
            </linearGradient>
            <linearGradient id="gradSolar" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="5%"
                stopColor="var(--chart-primary)"
                stopOpacity={0.4}
              />
              <stop
                offset="95%"
                stopColor="var(--chart-primary)"
                stopOpacity={0.05}
              />
            </linearGradient>
            <linearGradient id="gradThermal" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="5%"
                stopColor="var(--chart-orange)"
                stopOpacity={0.2}
              />
              <stop
                offset="95%"
                stopColor="var(--chart-orange)"
                stopOpacity={0.02}
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
          />

          <YAxis
            tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `${v}`}
            width={44}
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

          {/* P10–P90 solar band */}
          <Area
            type="monotone"
            dataKey="solarP90"
            stroke="none"
            fill="var(--chart-primary)"
            fillOpacity={0.08}
            name="solarP90"
          />
          <Area
            type="monotone"
            dataKey="solarP10"
            stroke="none"
            fill="hsl(var(--background))"
            fillOpacity={1}
            name="solarP10"
          />

          {/* Total load */}
          <Area
            type="monotone"
            dataKey="load"
            stroke="var(--chart-blue)"
            strokeWidth={2}
            fill="url(#gradLoad)"
            dot={false}
            name="load"
          />

          {/* Solar injection — real model output */}
          <Area
            type="monotone"
            dataKey="solar"
            stroke="var(--chart-primary)"
            strokeWidth={2.5}
            fill="url(#gradSolar)"
            dot={false}
            name="solar"
          />

          {/* Thermal / other */}
          <Area
            type="monotone"
            dataKey="thermal"
            stroke="var(--chart-orange)"
            strokeWidth={1.5}
            fill="url(#gradThermal)"
            dot={false}
            name="thermal"
            strokeDasharray="4 4"
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Footer */}
      <p className="text-2xs text-muted-foreground mt-3 pt-3 border-t border-border">
        Solar injection is real output from verified Phase 5.2 quantile models
        (ECMWF TIGGE NWP). The load curve is a synthetic daily shape used only
        to illustrate grid balance — it is not measured STEG demand. Thermal =
        load − solar (residual).
      </p>
    </div>
  );
}