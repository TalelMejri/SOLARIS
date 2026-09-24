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
} from 'recharts';
import { RefreshCw, AlertCircle, BarChart3 } from 'lucide-react';

/* ============================================================
   API
   ============================================================ */

const API_URL =
  'http://localhost:5000';

/* ============================================================
   Types
   ============================================================ */

type Horizon = 'h12' | 'h24' | 'h72';

interface RegionRow {
  region_id: number;
  region_name: string;
  capacity_mw: number;
  forecast_mw: number;
  regional_mw_true: number | null;
}

interface RegionApiResponse {
  timestamp: string;
  horizon: string;
  regions: RegionRow[];
}

interface ChartRow {
  id: string;
  zone: string;
  forecast: number;
  actual: number | null;
  capacity: number;
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
   Short labels — keeps the X-axis readable
   ============================================================ */

const SHORT_REGION_NAME: Record<string, string> = {
  'NORD OUEST': 'N.Ouest',
  'SUD OUEST': 'S.Ouest',
  CENTRE: 'Centre',
  NORD: 'Nord',
  SUD: 'Sud',
  SFAX: 'Sfax',
  TUNIS: 'Tunis',
};

const shorten = (name: string) => SHORT_REGION_NAME[name] ?? name;

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

  const forecast = payload.find((p) => p.name === 'forecast')?.value ?? 0;
  const actual = payload.find((p) => p.name === 'actual')?.value;
  const capacity =
    (payload[0] as any)?.payload?.capacity ?? 0;

  const error =
    actual !== undefined && actual !== null && actual > 0
      ? ((forecast - actual) / actual) * 100
      : null;

  const cf =
    capacity > 0 ? ((forecast / capacity) * 100).toFixed(1) : '—';

  return (
    <div className="bg-card border border-border rounded-lg p-3 shadow-xl text-xs space-y-1.5 min-w-[200px]">
      <p className="font-semibold text-foreground border-b border-border pb-1.5">
        {label}
      </p>

      <div className="flex justify-between gap-4">
        <span className="text-muted-foreground">Forecast P50</span>
        <span className="font-tabular font-semibold text-primary">
          {forecast.toFixed(2)} MW
        </span>
      </div>

      {actual !== undefined && actual !== null && (
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">Actual</span>
          <span className="font-tabular font-semibold text-accent">
            {actual.toFixed(2)} MW
          </span>
        </div>
      )}

      {error !== null && (
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">Error</span>
          <span
            className={`font-tabular font-semibold ${Math.abs(error) < 10
                ? 'text-primary'
                : Math.abs(error) < 25
                  ? 'text-amber-500'
                  : 'text-[var(--status-critical)]'
              }`}
          >
            {error > 0 ? '+' : ''}
            {error.toFixed(1)}%
          </span>
        </div>
      )}

      <div className="flex justify-between gap-4 pt-1 border-t border-border">
        <span className="text-muted-foreground">Capacity</span>
        <span className="font-tabular text-foreground">
          {capacity.toFixed(1)} MW
        </span>
      </div>

      <div className="flex justify-between gap-4">
        <span className="text-muted-foreground">Capacity factor</span>
        <span className="font-tabular text-foreground">{cf}%</span>
      </div>
    </div>
  );
};

/* ============================================================
   Main Component
   ============================================================ */

export default function ZoneBreakdownChart() {
  const [horizon, setHorizon] = useState<Horizon>('h12');
  const [data, setData] = useState<RegionRow[]>([]);
  const [timestamp, setTimestamp] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* ---------- Fetch regions for the selected horizon ---------- */
  useEffect(() => {
    let cancelled = false;

    const fetchRegions = async () => {
      setLoading(true);
      setError(null);

      try {
        // Use a fixed verification timestamp in the test set
        const ts = '2022-07-01T12:00:00+00:00';

        const url = new URL(`${API_URL}/api/regions`);
        url.searchParams.set('horizon', horizon);
        url.searchParams.set('timestamp', ts);

        const res = await fetch(url.toString());
        if (!res.ok) {
          throw new Error(`API ${res.status}`);
        }

        const json: RegionApiResponse = await res.json();

        if (!cancelled) {
          setData(json.regions ?? []);
          setTimestamp(json.timestamp ?? ts);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Fetch failed');
          setLoading(false);
        }
      }
    };

    fetchRegions();
    return () => {
      cancelled = true;
    };
  }, [horizon]);

  /* ---------- Transform to chart rows ---------- */
  const chartData = useMemo<ChartRow[]>(() => {
    if (!data.length) return [];

    return data
      .map((r) => ({
        id: `region-${r.region_id}`,
        zone: shorten(r.region_name),
        forecast: r.forecast_mw ?? 0,
        actual:
          typeof r.regional_mw_true === 'number'
            ? r.regional_mw_true
            : null,
        capacity: r.capacity_mw ?? 0,
      }))
      .sort((a, b) => b.forecast - a.forecast);
  }, [data]);

  /* ---------- Aggregate stats ---------- */
  const stats = useMemo(() => {
    if (!chartData.length) return null;

    const totalForecast = chartData.reduce((s, r) => s + r.forecast, 0);
    const totalActual = chartData
      .filter((r) => r.actual !== null)
      .reduce((s, r) => s + (r.actual ?? 0), 0);

    const totalCapacity = chartData.reduce((s, r) => s + r.capacity, 0);

    return {
      totalForecast,
      totalActual,
      totalCapacity,
      nRegions: chartData.length,
    };
  }, [chartData]);

  /* ---------- Loading ---------- */
  if (loading) {
    return (
      <div className="card-elevated p-5 h-full">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw size={14} className="animate-spin" />
          Loading regional forecast…
        </div>
      </div>
    );
  }

  /* ---------- Error ---------- */
  if (error || !chartData.length) {
    return (
      <div className="card-elevated p-5 h-full">
        <div className="flex items-start gap-2 text-sm text-[var(--status-critical)]">
          <AlertCircle size={14} className="mt-0.5" />
          <div>
            <p className="font-semibold">Failed to load regions</p>
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
    <div className="card-elevated p-5 h-full">
      {/* Header */}
      <div className="flex items-start justify-between mb-5 flex-wrap gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <BarChart3 size={14} className="text-primary" />
            Production by Region · {HORIZON_LABEL[horizon]}
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {stats
              ? `${stats.nRegions} regions · ${stats.totalCapacity.toFixed(0)} MW total capacity`
              : ''}
          </p>
        </div>

        <div className="flex items-center gap-3">
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

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-sm bg-primary opacity-80" />
              Forecast
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-sm bg-accent opacity-80" />
              Actual
            </span>
          </div>
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={280}>
        <BarChart
          data={chartData}
          margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
          barCategoryGap="25%"
          barGap={3}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--border)"
            vertical={false}
          />
          <XAxis
            dataKey="zone"
            tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `${v}`}
            width={36}
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

          <Bar
            dataKey="forecast"
            fill="var(--chart-primary)"
            radius={[3, 3, 0, 0]}
            opacity={0.85}
            name="forecast"
          />

          <Bar
            dataKey="actual"
            fill="var(--chart-accent, #2dd4aa)"
            radius={[3, 3, 0, 0]}
            opacity={0.8}
            name="actual"
          />
        </BarChart>
      </ResponsiveContainer>

      {/* Footer */}
      <div className="mt-4 pt-3 border-t border-border flex items-center justify-between flex-wrap gap-2">
        <p className="text-2xs text-muted-foreground">
          {stats
            ? `Total: ${stats.totalForecast.toFixed(1)} MW forecast${stats.totalActual > 0
              ? ` · ${stats.totalActual.toFixed(1)} MW actual`
              : ''
            }`
            : ''}
        </p>
        <p className="text-2xs text-muted-foreground">
          Source: LightGBM quantile models + ECMWF TIGGE NWP · verified test set
        </p>
      </div>
    </div>
  );
}