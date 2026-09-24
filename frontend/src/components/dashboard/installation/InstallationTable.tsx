import { useEffect, useState, useMemo } from 'react';
import StatusBadge from '@/components/ui/StatusBadge';
import {
  Search,
  ChevronUp,
  ChevronDown,
  MapPin,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Download,
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

type DistrictStatus = 'Normal' | 'Watch' | 'Warning' | 'Critical';
type Horizon = 'h12' | 'h24' | 'h72';

interface DistrictRow {
  district_id: number;
  district_name: string;
  region_name: string;
  latitude: number;
  longitude: number;
  capacity_mw: number;
  forecast_mw: number;
  forecast_normalized: number;
}

interface EnrichedDistrict extends DistrictRow {
  status: DistrictStatus;
  utilization: number;
  intervalMw: number;
}

/* ============================================================
   Safe number helpers — handle null/undefined/NaN
   ============================================================ */

const safeNum = (v: unknown, fallback = 0): number => {
  if (v === null || v === undefined) return fallback;
  const n = typeof v === 'number' ? v : Number(v);
  return isNaN(n) || !isFinite(n) ? fallback : n;
};

const fmt = (v: unknown, digits = 2): string => {
  const n = safeNum(v, NaN);
  if (isNaN(n)) return '—';
  return n.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
};

/* ============================================================
   Helpers
   ============================================================ */

function classifyStatus(utilization: number): DistrictStatus {
  if (utilization > 0.85) return 'Critical';
  if (utilization > 0.7) return 'Warning';
  if (utilization > 0.5) return 'Watch';
  return 'Normal';
}

const HORIZON_LABEL: Record<Horizon, string> = {
  h12: 'H+12',
  h24: 'H+24',
  h72: 'H+72',
};

/* ============================================================
   Main Component
   ============================================================ */

type SortKey = keyof EnrichedDistrict;

const STATUS_FILTERS: Array<'All' | DistrictStatus> = [
  'All',
  'Critical',
  'Warning',
  'Watch',
  'Normal',
];

export default function InstallationTable() {
  const [horizon, setHorizon] = useState<Horizon>('h12');
  const [districts, setDistricts] = useState<EnrichedDistrict[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'All' | DistrictStatus>('All');
  const [sortKey, setSortKey] = useState<SortKey>('utilization');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(12);

  /* ---------- Fetch districts ---------- */
  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        const ts = '2022-07-01T12:00:00+00:00';

        const [dRes, rRes] = await Promise.all([
          fetch(
            `${API_URL}/api/districts?horizon=${horizon}&timestamp=${encodeURIComponent(ts)}`,
          ),
          fetch(
            `${API_URL}/api/regions/quantile?horizon=${horizon}&timestamp=${encodeURIComponent(ts)}`,
          ).catch(() => null),
        ]);

        if (!dRes.ok) throw new Error(`Districts ${dRes.status}`);

        const dJson = await dRes.json();
        const raw: DistrictRow[] = dJson.districts ?? [];

        const regionInterval = new Map<string, number>();
        if (rRes?.ok) {
          const rJson = await rRes.json();
          for (const r of rJson.regions ?? []) {
            const interval = safeNum(r.regional_mw_p90) - safeNum(r.regional_mw_p10);
            const nDistricts = safeNum(r.n_districts, 1) || 1;
            regionInterval.set(r.region_name, interval / nDistricts);
          }
        }

        const enriched: EnrichedDistrict[] = raw.map((d) => {
          const capacity = safeNum(d.capacity_mw, 0);
          const forecast = safeNum(d.forecast_mw, 0);
          const util = capacity > 0 ? forecast / capacity : 0;
          const status = classifyStatus(util);
          const intervalMw = regionInterval.get(d.region_name) ?? forecast * 0.1;

          return {
            district_id: safeNum(d.district_id, 0),
            district_name: d.district_name ?? '—',
            region_name: d.region_name ?? '—',
            latitude: safeNum(d.latitude, 0),
            longitude: safeNum(d.longitude, 0),
            capacity_mw: capacity,
            forecast_mw: forecast,
            forecast_normalized: safeNum(d.forecast_normalized, 0),
            utilization: util,
            intervalMw,
            status,
          };
        });

        if (!cancelled) {
          setDistricts(enriched);
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

  /* ---------- Filter ---------- */
  const filtered = useMemo(() => {
    let rows = districts;

    if (statusFilter !== 'All') {
      rows = rows.filter((r) => r.status === statusFilter);
    }

    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(
        (r) =>
          r.district_name.toLowerCase().includes(q) ||
          r.region_name.toLowerCase().includes(q) ||
          String(r.district_id).includes(q),
      );
    }

    return [...rows].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av;
      }
      return sortDir === 'asc'
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
  }, [districts, search, statusFilter, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / perPage));
  const paginated = filtered.slice((page - 1) * perPage, page * perPage);

  /* ---------- Sorting ---------- */
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
      className={`flex items-center gap-1 text-2xs font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground ${align === 'right' ? 'ml-auto' : ''
        }`}
    >
      {children}
      <SortIcon col={col} />
    </button>
  );

  /* ---------- Counts ---------- */
  const counts = useMemo(() => {
    const acc: Record<DistrictStatus, number> = {
      Critical: 0,
      Warning: 0,
      Watch: 0,
      Normal: 0,
    };
    for (const d of districts) acc[d.status]++;
    return acc;
  }, [districts]);

  /* ---------- Loading ---------- */
  if (loading) {
    return (
      <div className="card-elevated overflow-hidden">
        <div className="flex items-center gap-2 border-b border-border px-5 py-4 text-sm text-muted-foreground">
          <RefreshCw size={14} className="animate-spin" />
          Loading district registry…
        </div>
      </div>
    );
  }

  /* ---------- Error ---------- */
  if (error) {
    return (
      <div className="card-elevated overflow-hidden">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-sm font-semibold text-foreground">
            District Registry
          </h2>
        </div>
        <div className="p-5 text-sm text-[var(--status-critical)]">
          Failed to load: {error}
        </div>
      </div>
    );
  }

  /* ---------- Render ---------- */
  return (
    <div className="card-elevated group relative overflow-hidden">
      {/* Header */}
      <div className="relative flex items-start justify-between gap-4 border-b border-border px-5 pb-4 pt-5">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold tracking-tight text-foreground">
            Prosol District Registry
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {filtered.length} of {districts.length} districts ·{' '}
            {HORIZON_LABEL[horizon]} forecast
          </p>
        </div>
        <StatusBadge
          status={counts.Critical > 0 ? 'Warning' : 'Normal'}
          size="sm"
        />
      </div>

      {/* Toolbar */}
      <div className="relative flex flex-col gap-3 border-b border-border px-5 py-4 lg:flex-row lg:items-center">
        <div className="flex min-w-[200px] max-w-xs flex-1 items-center gap-2 rounded-lg border border-border bg-muted px-3 py-2 text-xs text-muted-foreground transition-colors focus-within:border-primary/50">
          <Search size={13} />
          <input
            type="text"
            placeholder="Search district or region…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="flex-1 bg-transparent text-foreground outline-none placeholder:text-muted-foreground"
          />
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => {
                setStatusFilter(s);
                setPage(1);
              }}
              className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-150 ${statusFilter === s
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground'
                }`}
            >
              {s}
              {s !== 'All' && (
                <span className="ml-1.5 font-tabular opacity-70">
                  ({counts[s as DistrictStatus]})
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 lg:ml-auto">
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

          <button
            onClick={() => toast.info('Registry exported as CSV')}
            className="flex items-center gap-1.5 rounded-lg border border-border bg-muted px-3 py-2 text-xs font-medium text-muted-foreground transition-all duration-150 hover:text-foreground"
          >
            <Download size={13} />
            Export
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[900px] text-xs">
          <thead>
            <tr className="border-b border-border bg-muted/40">
              <th className="min-w-[60px] px-4 py-3 text-left">
                <ThBtn col="district_id">ID</ThBtn>
              </th>
              <th className="min-w-[180px] px-4 py-3 text-left">
                <ThBtn col="district_name">District</ThBtn>
              </th>
              <th className="px-4 py-3 text-left">
                <ThBtn col="region_name">Region</ThBtn>
              </th>
              <th className="px-4 py-3 text-left">
                <ThBtn col="status">Status</ThBtn>
              </th>
              <th className="px-4 py-3 text-right">
                <ThBtn col="capacity_mw" align="right">
                  Capacity (MW)
                </ThBtn>
              </th>
              <th className="px-4 py-3 text-right">
                <ThBtn col="forecast_mw" align="right">
                  Forecast (MW)
                </ThBtn>
              </th>
              <th className="px-4 py-3 text-right">
                <ThBtn col="utilization" align="right">
                  Utilization
                </ThBtn>
              </th>
              <th className="px-4 py-3 text-right">
                <ThBtn col="intervalMw" align="right">
                  ± Interval
                </ThBtn>
              </th>
              <th className="px-4 py-3 text-left">
                <ThBtn col="latitude">Location</ThBtn>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {paginated.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-16 text-center">
                  <p className="text-sm font-medium text-foreground">
                    No districts found
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Try adjusting the search or status filter
                  </p>
                </td>
              </tr>
            ) : (
              paginated.map((d) => (
                <tr
                  key={d.district_id}
                  className="transition-colors duration-100 hover:bg-muted/25"
                >
                  <td className="px-4 py-3">
                    <span className="font-mono text-2xs text-muted-foreground">
                      {String(d.district_id).padStart(2, '0')}
                    </span>
                  </td>

                  <td className="px-4 py-3">
                    <p className="font-medium text-foreground">
                      {d.district_name}
                    </p>
                  </td>

                  <td className="px-4 py-3">
                    <span className="text-foreground">{d.region_name}</span>
                  </td>

                  <td className="px-4 py-3">
                    <StatusBadge status={d.status} size="sm" />
                  </td>

                  <td className="px-4 py-3 text-right font-tabular text-foreground">
                    {fmt(d.capacity_mw, 1)}
                  </td>

                  <td className="px-4 py-3 text-right font-tabular font-semibold text-primary">
                    {fmt(d.forecast_mw, 2)}
                  </td>

                  <td className="px-4 py-3 text-right">
                    <span
                      className={`font-tabular font-semibold ${d.utilization > 0.85
                        ? 'text-[var(--status-critical)]'
                        : d.utilization > 0.7
                          ? 'text-accent'
                          : d.utilization > 0.5
                            ? 'text-foreground'
                            : 'text-muted-foreground'
                        }`}
                    >
                      {fmt(d.utilization * 100, 1)}%
                    </span>
                  </td>

                  <td className="px-4 py-3 text-right font-tabular text-muted-foreground">
                    ±{fmt(d.intervalMw / 2, 2)} MW
                  </td>

                  <td className="px-4 py-3">
                    <span className="flex items-center gap-1 text-2xs text-muted-foreground font-tabular">
                      <MapPin size={9} />
                      {fmt(d.latitude, 3)}°N / {fmt(d.longitude, 3)}°E
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="relative flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-3">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>Rows per page:</span>
          <select
            value={perPage}
            onChange={(e) => {
              setPerPage(Number(e.target.value));
              setPage(1);
            }}
            className="cursor-pointer rounded-md border border-border bg-muted px-2 py-1 text-xs text-foreground outline-none focus:border-primary/50"
          >
            {[12, 25, 50].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <span className="font-tabular">
            {filtered.length === 0
              ? '0 of 0'
              : `${(page - 1) * perPage + 1}–${Math.min(
                page * perPage,
                filtered.length,
              )} of ${filtered.length}`}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="rounded-md p-1.5 text-muted-foreground transition-all hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-30"
          >
            <ChevronLeft size={14} />
          </button>

          {Array.from({ length: totalPages }).map((_, i) => {
            const p = i + 1;
            const isActive = p === page;
            const show =
              p === 1 || p === totalPages || Math.abs(p - page) <= 1;

            if (!show) {
              if (p === 2 && page > 3) {
                return (
                  <span
                    key="ellipsis-start"
                    className="px-1 text-xs text-muted-foreground"
                  >
                    …
                  </span>
                );
              }
              return null;
            }

            return (
              <button
                key={`page-${p}`}
                onClick={() => setPage(p)}
                className={`h-7 w-7 rounded-md text-xs font-medium transition-all ${isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`}
              >
                {p}
              </button>
            );
          })}

          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="rounded-md p-1.5 text-muted-foreground transition-all hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-30"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}