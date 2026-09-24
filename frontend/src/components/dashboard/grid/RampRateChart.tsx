'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
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
  capacity_mw: number;
}

interface QuantileResponse {
  horizon: string;
  points: QuantilePoint[];
}

interface RampDay {
  id: string;
  date: string;
  rampUp: number;
  rampDown: number;
  isHigh: boolean;
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
   Config
   ============================================================ */

// Daily ramp threshold: 30 MW/day for alert (from grid impact summary)
const RAMP_THRESHOLD = 30;

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

  const rampUp = payload.find((p) => p.name === 'rampUp')?.value;
  const rampDown = payload.find((p) => p.name === 'rampDown')?.value;

  return (
    <div className="bg-card border border-border rounded-lg p-3 shadow-xl text-xs space-y-1.5 min-w-[200px]">
      <p className="font-semibold text-foreground border-b border-border pb-1.5">
        {label}
      </p>

      {rampUp !== undefined && rampUp > 0 && (
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">Ramp up</span>
          <span className="font-tabular font-semibold text-primary">
            +{rampUp.toFixed(1)} MW/day
          </span>
        </div>
      )}

      {rampDown !== undefined && rampDown > 0 && (
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">Ramp down</span>
          <span className="font-tabular font-semibold text-accent">
            −{rampDown.toFixed(1)} MW/day
          </span>
        </div>
      )}

      {rampUp !== undefined && rampUp > RAMP_THRESHOLD && (
        <p className="text-[var(--status-critical)] text-2xs pt-1 border-t border-border">
          ⚠ Exceeds {RAMP_THRESHOLD} MW/day threshold
        </p>
      )}

      {rampDown !== undefined && rampDown > RAMP_THRESHOLD && (
        <p className="text-[var(--status-critical)] text-2xs pt-1 border-t border-border">
          ⚠ Exceeds {RAMP_THRESHOLD} MW/day threshold
        </p>
      )}
    </div>
  );
};

/* ============================================================
   Main Component
   ============================================================ */

export default function RampRateChart() {
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
        url.searchParams.set('end', '2022-07-08');

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

  /* ---------- Compute daily ramp from peak values ---------- */
  const rampData = useMemo<RampDay[]>(() => {
    if (!raw?.points?.length) return [];

    // Group by date and find peak P50 per day (take 12:00 UTC samples)
    const byDay = new Map<string, number>();

    for (const p of raw.points) {
      const d = new Date(p.time);
      // Use 12:00 UTC samples (peak of day) — from 00Z + H+12
      if (d.getUTCHours() === 12) {
        const key = d.toISOString().slice(0, 10); // YYYY-MM-DD
        byDay.set(key, p.national_p50);
      }
    }

    const dates = Array.from(byDay.keys()).sort();
    const rows: RampDay[] = [];

    for (let i = 1; i < dates.length; i++) {
      const prev = byDay.get(dates[i - 1]) ?? 0;
      const curr = byDay.get(dates[i]) ?? 0;
      const delta = curr - prev;

      const rampUp = delta > 0 ? Math.abs(delta) : 0;
      const rampDown = delta < 0 ? Math.abs(delta) : 0;

      rows.push({
        id: `ramp-${dates[i]}`,
        date: dates[i].slice(5), // MM-DD
        rampUp: parseFloat(rampUp.toFixed(1)),
        rampDown: parseFloat(rampDown.toFixed(1)),
        isHigh: Math.abs(delta) > RAMP_THRESHOLD,
      });
    }

    return rows;
  }, [raw]);

  /* ---------- Stats ---------- */
  const stats = useMemo(() => {
    if (!rampData.length) return null;

    const all = rampData.flatMap((r) => [r.rampUp, r.rampDown]).filter((v) => v > 0);
    const mean = all.reduce((s, v) => s + v, 0) / all.length;
    const max = Math.max(...all);
    const highCount = rampData.filter((r) => r.isHigh).length;

    return { mean, max, highCount, nDays: rampData.length };
  }, [rampData]);

  /* ---------- Loading ---------- */
  if (loading) {
    return (
      <div className="card-elevated p-5">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw size={14} className="animate-spin" />
          Loading ramp analysis…
        </div>
      </div>
    );
  }

  /* ---------- Error ---------- */
  if (error || !rampData.length) {
    return (
      <div className="card-elevated p-5">
        <div className="flex items-start gap-2 text-sm text-[var(--status-critical)]">
          <AlertCircle size={14} className="mt-0.5" />
          <div>
            <p className="font-semibold">Failed to load ramp data</p>
            <p className="text-xs text-muted-foreground mt-1">
              {error ?? 'No consecutive days in window'}
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
            Daily Peak Ramp · National
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Day-to-day peak change · MW/day · TIGGE 6-hourly resolution
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

      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="bg-muted/30 rounded-lg p-2.5 border border-border">
            <p className="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">
              Mean |ramp|
            </p>
            <p className="text-sm font-tabular font-semibold text-foreground">
              {stats.mean.toFixed(1)}
              <span className="text-2xs text-muted-foreground ml-1">MW/day</span>
            </p>
          </div>
          <div className="bg-muted/30 rounded-lg p-2.5 border border-border">
            <p className="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">
              Max |ramp|
            </p>
            <p className="text-sm font-tabular font-semibold text-foreground">
              {stats.max.toFixed(1)}
              <span className="text-2xs text-muted-foreground ml-1">MW/day</span>
            </p>
          </div>
          <div className="bg-muted/30 rounded-lg p-2.5 border border-border">
            <p className="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">
              High events
            </p>
            <p className="text-sm font-tabular font-semibold text-foreground">
              {stats.highCount}
              <span className="text-2xs text-muted-foreground ml-1">
                / {stats.nDays}
              </span>
            </p>
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center gap-4 mb-3 text-xs">
        <span className="flex items-center gap-1.5 text-muted-foreground">
          <span className="w-2.5 h-2.5 rounded-sm bg-primary opacity-80" />
          Ramp up
        </span>
        <span className="flex items-center gap-1.5 text-muted-foreground">
          <span className="w-2.5 h-2.5 rounded-sm bg-accent opacity-80" />
          Ramp down
        </span>
        <span className="flex items-center gap-1.5 text-muted-foreground ml-auto">
          <span className="w-2.5 h-2.5 rounded-sm bg-[var(--status-critical)] opacity-80" />
          High ({'>'}{RAMP_THRESHOLD} MW/day)
        </span>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={240}>
        <BarChart
          data={rampData}
          margin={{ top: 8, right: 4, bottom: 0, left: 0 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--border)"
            vertical={false}
          />

          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
            axisLine={false}
            tickLine={false}
          />

          <YAxis
            tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `${v}`}
            width={40}
            label={{
              value: 'MW/day',
              angle: -90,
              position: 'insideLeft',
              style: {
                fontSize: 10,
                fill: 'var(--muted-foreground)',
              },
            }}
          />

          <Tooltip content={<CustomTooltip />} />

          <ReferenceLine
            y={RAMP_THRESHOLD}
            stroke="var(--status-critical)"
            strokeDasharray="4 4"
            strokeWidth={1}
            opacity={0.5}
          />

          <Bar dataKey="rampUp" stackId="ramp" radius={[3, 3, 0, 0]} name="rampUp">
            {rampData.map((entry) => (
              <Cell
                key={`up-${entry.id}`}
                fill={
                  entry.rampUp > RAMP_THRESHOLD
                    ? 'var(--status-critical)'
                    : 'var(--chart-primary)'
                }
                opacity={0.85}
              />
            ))}
          </Bar>

          <Bar
            dataKey="rampDown"
            stackId="ramp"
            radius={[3, 3, 0, 0]}
            name="rampDown"
          >
            {rampData.map((entry) => (
              <Cell
                key={`down-${entry.id}`}
                fill={
                  entry.rampDown > RAMP_THRESHOLD
                    ? 'var(--status-critical)'
                    : 'var(--chart-accent, #2dd4aa)'
                }
                opacity={0.85}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Footer */}
      <p className="text-2xs text-muted-foreground mt-3 pt-3 border-t border-border">
        Ramp = day-to-day change in peak forecast. TIGGE is 6-hourly, so hourly
        ramp rates are not computed. Threshold of {RAMP_THRESHOLD} MW/day is a
        decision-support indicator, not an actual STEG grid limit.
      </p>
    </div>
  );
}