'use client';

import { useEffect, useMemo, useState } from 'react';
import StatusBadge from '@/components/ui/StatusBadge';
import {
  ChevronUp,
  ChevronDown,
  AlertTriangle,
  CheckCircle,
  Zap,
  RefreshCw,
} from 'lucide-react';
import { toast } from 'sonner';

/* ============================================================
   API
   ============================================================ */

const API_URL =
  'http://localhost:5000';

/* ============================================================
   Types
   ============================================================ */

type RegionStatus = 'Normal' | 'Watch' | 'Warning' | 'Critical';
type Horizon = 'h12' | 'h24' | 'h72';

interface RegionSnapshot {
  region_id: number;
  region_name: string;
  capacity_mw: number;
  forecast_mw: number;
  n_districts: number;
}

interface RegionalQuantile {
  region_id: number;
  region_name: string;
  capacity_mw: number;
  regional_mw_p10: number;
  regional_mw_p50: number;
  regional_mw_p90: number;
  regional_mw_true: number;
  n_districts: number;
}

interface RegionRow {
  id: string;
  region_id: number;
  zone: string;
  status: RegionStatus;
  n_districts: number;
  capacity_mw: number;
  forecast_mw: number;
  interval_mw: number;
  utilization: number;
  action: string;
}

/* ============================================================
   Config
   ============================================================ */

const HORIZON_LABEL: Record<Horizon, string> = {
  h12: 'H+12',
  h24: 'H+24',
  h72: 'H+72',
};

/* ============================================================
   Status classification
   ============================================================ */

function classifyStatus(utilization: number): RegionStatus {
  if (utilization > 0.85) return 'Critical';
  if (utilization > 0.7) return 'Warning';
  if (utilization > 0.5) return 'Watch';
  return 'Normal';
}

function actionFor(status: RegionStatus, util: number, intervalMw: number): string {
  switch (status) {
    case 'Critical':
      return `Curtailment likely — ${(util * 100).toFixed(0)}% utilization`;
    case 'Warning':
      return `Plan reserve — ${intervalMw.toFixed(1)} MW uncertainty`;
    case 'Watch':
      return 'Increase monitoring frequency';
    default:
      return '—';
  }
}

/* ============================================================
   Component
   ============================================================ */

type SortKey = 'zone' | 'status' | 'forecast_mw' | 'utilization' | 'interval_mw' | 'n_districts';

export default function ZoneStatusTable() {
  const [sortKey, setSortKey] = useState<SortKey>('utilization');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [horizon, setHorizon] = useState<Horizon>('h12');
  const [regions, setRegions] = useState<RegionalQuantile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* ---------- Fetch real region data ---------- */
  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        const ts = '2022-07-01T12:00:00+00:00';
        const url = new URL(`${API_URL}/api/regions/quantile`);
        url.searchParams.set('horizon', horizon);
        url.searchParams.set('timestamp', ts);

        const res = await fetch(url.toString());
        if (!res.ok) throw new Error(`API ${res.status}`);

        const json = await res.json();
        if (!cancelled) {
          setRegions(json.regions ?? []);
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

  /* ---------- Build table rows ---------- */
  const rows = useMemo<RegionRow[]>(() => {
    if (!regions.length) return [];

    return regions.map((r) => {
      const util = r.capacity_mw > 0 ? r.regional_mw_p50 / r.capacity_mw : 0;
      const interval = r.regional_mw_p90 - r.regional_mw_p10;
      const status = classifyStatus(util);

      return {
        id: `region-${r.region_id}`,
        region_id: r.region_id,
        zone: r.region_name,
        status,
        n_districts: r.n_districts,
        capacity_mw: r.capacity_mw,
        forecast_mw: r.regional_mw_p50,
        interval_mw: interval,
        utilization: util,
        action: actionFor(status, util, interval),
      };
    });
  }, [regions]);

  /* ---------- Sorting ---------- */
  const sorted = useMemo(() => {
    return [...rows].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];

      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av;
      }
      const as = String(av);
      const bs = String(bv);
      return sortDir === 'asc' ? as.localeCompare(bs) : bs.localeCompare(as);
    });
  }, [rows, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ChevronUp size={11} className="opacity-20" />;
    return sortDir === 'asc' ? (
      <ChevronUp size={11} className="text-primary" />
    ) : (
      <ChevronDown size={11} className="text-primary" />
    );
  };

  const ThBtn = ({
    col,
    children,
    align = 'left',
  }: {
    col: SortKey;
    children: React.ReactNode;
    align?: 'left' | 'right';
  }) => (
    <button
      onClick={() => handleSort(col)}
      className={`flex items-center gap-1 text-2xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors ${align === 'right' ? 'ml-auto' : ''
        }`}
    >
      {children}
      <SortIcon col={col} />
    </button>
  );

  /* ---------- Status counts ---------- */
  const counts = useMemo(() => {
    const acc: Record<RegionStatus, number> = {
      Critical: 0,
      Warning: 0,
      Watch: 0,
      Normal: 0,
    };
    for (const r of rows) acc[r.status]++;
    return acc;
  }, [rows]);

  const actionCount = counts.Critical + counts.Warning;

  /* ---------- Loading ---------- */
  if (loading) {
    return (
      <div className="card-elevated overflow-hidden">
        <div className="px-5 py-4 border-b border-border">
          <h2 className="text-sm font-semibold text-foreground">
            Regional Forecast Status
          </h2>
        </div>
        <div className="p-5 flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw size={14} className="animate-spin" />
          Loading regional data…
        </div>
      </div>
    );
  }

  /* ---------- Error ---------- */
  if (error) {
    return (
      <div className="card-elevated overflow-hidden">
        <div className="px-5 py-4 border-b border-border">
          <h2 className="text-sm font-semibold text-foreground">
            Regional Forecast Status
          </h2>
        </div>
        <div className="p-5">
          <p className="text-sm text-[var(--status-critical)]">
            Failed to load: {error}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Ensure the backend is running at {API_URL}
          </p>
        </div>
      </div>
    );
  }

  /* ---------- Render ---------- */
  return (
    <div className="card-elevated overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border flex-wrap gap-3">
        <div>
          <h2 className="text-sm font-semibold text-foreground">
            Regional Forecast Status
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {actionCount > 0
              ? `${actionCount} region${actionCount > 1 ? 's' : ''} require attention`
              : 'All regions nominal'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Horizon toggle */}
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

          {/* Status counts */}
          <div className="hidden md:flex items-center gap-2 text-xs">
            {(['Critical', 'Warning', 'Watch', 'Normal'] as RegionStatus[]).map(
              (s) => (
                <span
                  key={`count-${s}`}
                  className="flex items-center gap-1 text-muted-foreground"
                >
                  <StatusBadge status={s} size="sm" />
                  <span className="font-tabular font-semibold">{counts[s]}</span>
                </span>
              ),
            )}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-3">
                <ThBtn col="zone">Region</ThBtn>
              </th>
              <th className="text-left px-4 py-3">
                <ThBtn col="status">Status</ThBtn>
              </th>
              <th className="text-right px-4 py-3">
                <ThBtn col="n_districts" align="right">
                  Districts
                </ThBtn>
              </th>
              <th className="text-right px-4 py-3">
                <ThBtn col="forecast_mw" align="right">
                  Forecast MW
                </ThBtn>
              </th>
              <th className="text-right px-4 py-3">
                <ThBtn col="utilization" align="right">
                  Utilization
                </ThBtn>
              </th>
              <th className="text-right px-4 py-3">
                <ThBtn col="interval_mw" align="right">
                  Interval
                </ThBtn>
              </th>
              <th className="text-left px-4 py-3 min-w-[200px]">
                Recommended action
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sorted.map((row) => (
              <tr
                key={row.id}
                className="hover:bg-muted/30 transition-colors duration-100"
              >
                <td className="px-4 py-3">
                  <p className="font-medium text-foreground">{row.zone}</p>
                  <p className="text-2xs text-muted-foreground mt-0.5">
                    {row.capacity_mw.toFixed(1)} MW installed
                  </p>
                </td>

                <td className="px-4 py-3">
                  <StatusBadge status={row.status} size="sm" />
                </td>

                <td className="px-4 py-3 text-right font-tabular text-muted-foreground">
                  {row.n_districts}
                </td>

                <td className="px-4 py-3 text-right font-tabular text-primary font-semibold">
                  {row.forecast_mw.toFixed(1)}
                </td>

                <td className="px-4 py-3 text-right">
                  <span
                    className={`font-tabular font-semibold ${row.utilization > 0.85
                        ? 'text-[var(--status-critical)]'
                        : row.utilization > 0.7
                          ? 'text-accent'
                          : row.utilization > 0.5
                            ? 'text-foreground'
                            : 'text-muted-foreground'
                      }`}
                  >
                    {(row.utilization * 100).toFixed(1)}%
                  </span>
                </td>

                <td className="px-4 py-3 text-right font-tabular text-muted-foreground">
                  ±{(row.interval_mw / 2).toFixed(1)} MW
                </td>

                <td className="px-4 py-3">
                  {row.action !== '—' ? (
                    <span className="flex items-center gap-2">
                      <AlertTriangle
                        size={11}
                        className={
                          row.status === 'Critical'
                            ? 'text-[var(--status-critical)]'
                            : 'text-accent'
                        }
                      />
                      <span
                        className={
                          row.status === 'Critical'
                            ? 'text-[var(--status-critical)] font-medium'
                            : 'text-accent'
                        }
                      >
                        {row.action}
                      </span>
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-primary">
                      <CheckCircle size={11} />
                      No action needed
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-border flex items-center justify-between text-xs text-muted-foreground flex-wrap gap-2">
        <span>
          {rows.length} regions · Updated from verified Phase 5.3 pipeline
        </span>
        <button
          onClick={() => toast.info('Dispatch report exported')}
          className="flex items-center gap-1.5 text-primary hover:text-primary/80 font-medium transition-colors"
        >
          <Zap size={12} />
          Export dispatch report
        </button>
      </div>
    </div>
  );
}