'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle,
  RefreshCw,
  ShieldCheck,
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

type AlertSeverity = 'critical' | 'warning' | 'info' | 'resolved';

interface Alert {
  id: string;
  severity: AlertSeverity;
  zone: string;
  message: string;
  time: string;
  acknowledged: boolean;
}

interface RegionRow {
  region_id: number;
  region_name: string;
  capacity_mw: number;
  forecast_mw: number;
  n_districts: number;
}

interface QuantilePoint {
  time: string;
  national_p10: number;
  national_p50: number;
  national_p90: number;
  capacity_mw: number;
}

interface Phase52Results {
  improvement_pct: { h12: number; h24: number; h72: number };
  districts_improved: number;
  districts_total: number;
  verification: string;
  nwp_source: string;
}

interface BatterySummary {
  peak_reduction_mw: number;
  peak_reduction_pct: number;
  mean_soc: number;
}

interface GridImpact {
  diurnal_swing_mw?: number;
  mean_peak_mw?: number;
  max_peak_mw?: number;
  reserve_proxy_mw?: number;
}

/* ============================================================
   Severity styling
   ============================================================ */

const severityIcon: Record<AlertSeverity, React.ReactNode> = {
  critical: <AlertCircle size={13} />,
  warning: <AlertTriangle size={13} />,
  info: <Info size={13} />,
  resolved: <CheckCircle size={13} />,
};

const severityClass: Record<AlertSeverity, string> = {
  critical: 'text-[var(--status-critical)] bg-status-critical',
  warning: 'text-accent bg-status-warning',
  info: 'text-[var(--status-watch)] bg-status-watch',
  resolved: 'text-primary bg-status-normal',
};

/* ============================================================
   Helpers
   ============================================================ */

const nowTime = () => {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(
    d.getMinutes(),
  ).padStart(2, '0')}`;
};

/**
 * Derive alerts from real pipeline data.
 * Each alert is traceable to a specific verified artifact.
 */
function buildAlerts(
  regions: RegionRow[],
  quantile: QuantilePoint[],
  phase52: Phase52Results | null,
  battery: BatterySummary | null,
  grid: GridImpact | null,
): Alert[] {
  const alerts: Alert[] = [];
  const time = nowTime();

  /* ---------- 1. Verification status ---------- */
  if (phase52?.verification) {
    alerts.push({
      id: 'verify-001',
      severity: 'resolved',
      zone: 'System',
      message: `${phase52.verification} · NWP pipeline verified`,
      time,
      acknowledged: true,
    });
  }

  /* ---------- 2. District improvement ---------- */
  if (phase52) {
    const pct = (
      (phase52.districts_improved / phase52.districts_total) *
      100
    ).toFixed(0);
    alerts.push({
      id: 'districts-001',
      severity: 'info',
      zone: 'National',
      message: `${phase52.districts_improved}/${phase52.districts_total} districts improved (${pct}%) with ${phase52.nwp_source}`,
      time,
      acknowledged: false,
    });
  }

  /* ---------- 3. Region utilization warnings ---------- */
  for (const r of regions) {
    const utilization =
      r.capacity_mw > 0 ? r.forecast_mw / r.capacity_mw : 0;

    if (utilization > 0.85) {
      alerts.push({
        id: `region-util-${r.region_id}`,
        severity: 'critical',
        zone: r.region_name,
        message: `High utilization ${(utilization * 100).toFixed(1)}% — ${r.forecast_mw.toFixed(1)} MW of ${r.capacity_mw.toFixed(1)} MW capacity`,
        time,
        acknowledged: false,
      });
    } else if (utilization > 0.7) {
      alerts.push({
        id: `region-util-${r.region_id}`,
        severity: 'warning',
        zone: r.region_name,
        message: `Elevated utilization ${(utilization * 100).toFixed(1)}% — monitor grid load`,
        time,
        acknowledged: false,
      });
    }
  }

  /* ---------- 4. National interval width ---------- */
  if (quantile.length > 0) {
    const peak = quantile.reduce(
      (max, p) => (p.national_p50 > max.national_p50 ? p : max),
      quantile[0],
    );
    const width = peak.national_p90 - peak.national_p10;
    const widthPct =
      peak.national_p50 > 0 ? (width / peak.national_p50) * 100 : 0;

    if (widthPct > 50) {
      alerts.push({
        id: 'interval-001',
        severity: 'warning',
        zone: 'National',
        message: `P10–P90 interval is ${width.toFixed(1)} MW at peak (${widthPct.toFixed(0)}% of P50) — high forecast uncertainty`,
        time,
        acknowledged: false,
      });
    } else {
      alerts.push({
        id: 'interval-001',
        severity: 'info',
        zone: 'National',
        message: `Peak P50 forecast: ${peak.national_p50.toFixed(1)} MW (P10–P90: ${peak.national_p10.toFixed(1)}–${peak.national_p90.toFixed(1)} MW)`,
        time,
        acknowledged: false,
      });
    }
  }

  /* ---------- 5. Battery decision support ---------- */
  if (battery) {
    alerts.push({
      id: 'battery-001',
      severity: 'info',
      zone: 'Battery',
      message: `Battery simulation: ${battery.peak_reduction_mw.toFixed(1)} MW peak reduction (${battery.peak_reduction_pct.toFixed(1)}%) · mean SOC ${(battery.mean_soc * 100).toFixed(1)}%`,
      time,
      acknowledged: false,
    });
  }

  /* ---------- 6. Grid impact ---------- */
  if (grid?.diurnal_swing_mw) {
    alerts.push({
      id: 'grid-001',
      severity: 'info',
      zone: 'Grid Impact',
      message: `Diurnal swing: ${grid.diurnal_swing_mw.toFixed(0)} MW · reserve proxy ${grid.reserve_proxy_mw?.toFixed(0) ?? '—'} MW`,
      time,
      acknowledged: false,
    });
  }

  /* ---------- 7. Reserve proxy warning ---------- */
  if (grid?.reserve_proxy_mw && grid.reserve_proxy_mw > 80) {
    alerts.push({
      id: 'reserve-001',
      severity: 'warning',
      zone: 'Grid Impact',
      message: `Reserve proxy ${grid.reserve_proxy_mw.toFixed(1)} MW — plan dispatch margin`,
      time,
      acknowledged: false,
    });
  }

  return alerts;
}

/* ============================================================
   Main Component
   ============================================================ */

export default function AlertFeed() {
  const [regions, setRegions] = useState<RegionRow[]>([]);
  const [quantile, setQuantile] = useState<QuantilePoint[]>([]);
  const [phase52, setPhase52] = useState<Phase52Results | null>(null);
  const [battery, setBattery] = useState<BatterySummary | null>(null);
  const [grid, setGrid] = useState<GridImpact | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [acknowledged, setAcknowledged] = useState<Set<string>>(new Set());

  /* ---------- Fetch all sources ---------- */
  useEffect(() => {
    let cancelled = false;

    const fetchAll = async () => {
      setLoading(true);
      setError(null);

      try {
        const [regRes, qRes, p52Res, batRes, gridRes] = await Promise.all([
          fetch(
            `${API_URL}/api/regions?horizon=h12&timestamp=2022-07-01T12:00:00+00:00`,
          ),
          fetch(
            `${API_URL}/api/forecast/national/quantile?horizon=h12&start=2022-07-01&end=2022-07-05`,
          ),
          fetch(`${API_URL}/api/methodology/phase52`),
          fetch(`${API_URL}/api/battery/simulation?horizon=h12`),
          fetch(`${API_URL}/api/grid/impact`).catch(() => null),
        ]);

        if (!regRes.ok) throw new Error(`Regions ${regRes.status}`);

        const regJson = await regRes.json();
        const qJson = qRes.ok ? await qRes.json() : { points: [] };
        const p52Json = p52Res.ok ? await p52Res.json() : null;
        const batJson = batRes.ok ? await batRes.json() : null;
        const gridJson = gridRes && gridRes.ok ? await gridRes.json() : null;

        if (!cancelled) {
          setRegions(regJson.regions ?? []);
          setQuantile(qJson.points ?? []);
          setPhase52(p52Json);
          setBattery(batJson);
          setGrid(gridJson);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Fetch failed');
          setLoading(false);
        }
      }
    };

    fetchAll();
    return () => {
      cancelled = true;
    };
  }, []);

  /* ---------- Build alerts from real data ---------- */
  const allAlerts = useMemo(
    () => buildAlerts(regions, quantile, phase52, battery, grid),
    [regions, quantile, phase52, battery, grid],
  );

  /* ---------- Apply acknowledgment ---------- */
  const alerts = useMemo(
    () =>
      allAlerts.map((a) => ({
        ...a,
        acknowledged: a.acknowledged || acknowledged.has(a.id),
      })),
    [allAlerts, acknowledged],
  );

  const acknowledge = (id: string) => {
    setAcknowledged((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    toast.success('Alert acknowledged');
  };

  const unacknowledged = alerts.filter((a) => !a.acknowledged).length;

  /* ---------- Loading ---------- */
  if (loading) {
    return (
      <div className="card-elevated flex flex-col h-full">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <h2 className="text-sm font-semibold text-foreground">Live Alerts</h2>
        </div>
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <RefreshCw size={14} className="animate-spin" />
            Loading alerts…
          </div>
        </div>
      </div>
    );
  }

  /* ---------- Error ---------- */
  if (error) {
    return (
      <div className="card-elevated flex flex-col h-full">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <h2 className="text-sm font-semibold text-foreground">Live Alerts</h2>
        </div>
        <div className="flex-1 p-5">
          <p className="text-sm text-[var(--status-critical)]">
            Failed to load alerts: {error}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Ensure the FastAPI backend is running on {API_URL}
          </p>
        </div>
      </div>
    );
  }

  /* ---------- Render ---------- */
  return (
    <div className="card-elevated flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
        <div>
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <ShieldCheck size={13} className="text-primary" />
            System Alerts
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {unacknowledged > 0 ? (
              <span className="text-accent font-medium">
                {unacknowledged} unacknowledged
              </span>
            ) : (
              'All acknowledged'
            )}
          </p>
        </div>
        <span className="text-xs text-muted-foreground">
          {alerts.length} total
        </span>
      </div>

      {/* Feed */}
      <div className="flex-1 overflow-y-auto divide-y divide-border">
        {alerts.length === 0 ? (
          <div className="p-5 text-xs text-muted-foreground">
            No alerts. All systems nominal.
          </div>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.id}
              className={`px-4 py-3 flex gap-3 transition-colors duration-150 ${
                alert.acknowledged ? 'opacity-50' : 'hover:bg-muted/30'
              }`}
            >
              <span
                className={`mt-0.5 shrink-0 p-1 rounded-md ${severityClass[alert.severity]}`}
              >
                {severityIcon[alert.severity]}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {alert.zone}
                  </span>
                  <span className="text-2xs text-muted-foreground font-tabular shrink-0">
                    {alert.time}
                  </span>
                </div>
                <p className="text-xs text-foreground mt-0.5 leading-relaxed">
                  {alert.message}
                </p>
                {!alert.acknowledged && (
                  <button
                    onClick={() => acknowledge(alert.id)}
                    className="mt-1.5 text-2xs font-medium text-primary hover:text-primary/80 transition-colors"
                  >
                    Acknowledge →
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-border shrink-0">
        <p className="text-2xs text-muted-foreground">
          Alerts derived from verified Phase 5.2 → 6.2 pipeline · not live STEG data
        </p>
      </div>
    </div>
  );
}