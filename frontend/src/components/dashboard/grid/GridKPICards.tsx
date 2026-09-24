import { useEffect, useMemo, useState } from 'react';
import MetricCard from '@/components/ui/MetricCard';
import {
  Zap,
  BarChart2,
  AlertTriangle,
  Sun,
  Activity,
} from 'lucide-react';

/* ============================================================
   API — env-aware, default port 8000
   ============================================================ */

const API_URL =
  'http://localhost:5000';

/* ============================================================
   Realistic thresholds for a distributed rooftop PV fleet.
   Tunisia rooftop utilization peaks at 55–65% at noon in July.
   ============================================================ */

const HIGH_UTIL_THRESHOLD = 0.55;
const CRITICAL_UTIL_THRESHOLD = 0.65;

/* ============================================================
   Types
   ============================================================ */

interface GridImpact {
  diurnal_swing_mw?: number;
  mean_peak_mw?: number;
  max_peak_mw?: number;
  reserve_proxy_mw?: number;
  note?: string;
}

interface BatteryData {
  peak_reduction_mw: number;
  peak_reduction_pct: number;
  mean_soc: number;
  total_charged_mwh?: number;
  total_discharged_mwh?: number;
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

/* ============================================================
   Component
   ============================================================ */

export default function GridKPICards() {
  const [grid, setGrid] = useState<GridImpact | null>(null);
  const [battery, setBattery] = useState<BatteryData | null>(null);
  const [regions, setRegions] = useState<RegionRow[]>([]);
  const [quantile, setQuantile] = useState<QuantilePoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const fetchAll = async () => {
      try {
        const [gRes, bRes, rRes, qRes] = await Promise.all([
          fetch(`${API_URL}/api/grid/impact`).catch(() => null),
          fetch(`${API_URL}/api/battery/simulation?horizon=h12`).catch(
            () => null,
          ),
          fetch(
            `${API_URL}/api/regions?horizon=h12&timestamp=2022-07-01T12:00:00+00:00`,
          ).catch(() => null),
          fetch(
            `${API_URL}/api/forecast/national/quantile?horizon=h12&start=2022-07-01&end=2022-07-05`,
          ).catch(() => null),
        ]);

        if (cancelled) return;

        if (gRes?.ok) setGrid(await gRes.json());
        if (bRes?.ok) setBattery(await bRes.json());
        if (rRes?.ok) {
          const j = await rRes.json();
          setRegions(j.regions ?? []);
        }
        if (qRes?.ok) {
          const j = await qRes.json();
          setQuantile(j.points ?? []);
        }

        setLoading(false);
      } catch (e) {
        if (!cancelled) setLoading(false);
      }
    };

    fetchAll();
    return () => {
      cancelled = true;
    };
  }, []);

  /* ---------- Derived metrics ---------- */

  const metrics = useMemo(() => {
    let peakP50 = 0;
    let peakP10 = 0;
    let peakP90 = 0;
    let capacity = 515.1;

    if (quantile.length > 0) {
      const peak = quantile.reduce((max, p) =>
        p.national_p50 > max.national_p50 ? p : max,
      );
      peakP50 = peak.national_p50;
      peakP10 = peak.national_p10;
      peakP90 = peak.national_p90;
      capacity = peak.capacity_mw;
    }

    const highUtilRegions = regions.filter((r) => {
      const util = r.capacity_mw > 0 ? r.forecast_mw / r.capacity_mw : 0;
      return util > HIGH_UTIL_THRESHOLD;
    });
    const criticalRegions = regions.filter((r) => {
      const util = r.capacity_mw > 0 ? r.forecast_mw / r.capacity_mw : 0;
      return util > CRITICAL_UTIL_THRESHOLD;
    });

    const peakCF = capacity > 0 ? (peakP50 / capacity) * 100 : 0;
    const intervalWidth = peakP90 - peakP10;

    const nationalMeanUtil =
      regions.length > 0
        ? regions.reduce((sum, r) => {
            const util =
              r.capacity_mw > 0 ? r.forecast_mw / r.capacity_mw : 0;
            return sum + util;
          }, 0) / regions.length
        : 0;

    return {
      peakP50,
      peakP10,
      peakP90,
      intervalWidth,
      capacity,
      peakCF,
      highUtilRegions: highUtilRegions.length,
      criticalRegions: criticalRegions.length,
      totalRegions: regions.length || 7,
      nationalMeanUtil,
    };
  }, [quantile, regions]);

  /* ---------- Loading skeleton ---------- */

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-6">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={`skeleton-${i}`}
            className={`card-elevated h-[100px] animate-pulse bg-muted/20 ${
              i < 3 ? 'lg:col-span-2' : 'lg:col-span-3'
            }`}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-6">
      {/* Row 1 — 3 cards */}

      <MetricCard
        label="National Peak P50"
        value={metrics.peakP50.toFixed(0)}
        unit="MW"
        trend={metrics.peakCF}
        trendLabel={`${metrics.peakCF.toFixed(1)}% capacity factor`}
        icon={<Sun size={18} />}
        className="lg:col-span-2"
      />

      <MetricCard
        label="Prediction Interval"
        value={metrics.intervalWidth.toFixed(0)}
        unit="MW"
        trend={0}
        trendLabel={`P10–P90 at peak (${metrics.peakP10.toFixed(
          0,
        )}–${metrics.peakP90.toFixed(0)})`}
        icon={<Activity size={18} />}
        className="lg:col-span-2"
      />

      <MetricCard
        label="Peak Reduction · Battery"
        value={battery ? battery.peak_reduction_mw.toFixed(1) : '—'}
        unit="MW"
        trend={battery?.peak_reduction_pct ?? 0}
        trendLabel={
          battery
            ? `${battery.peak_reduction_pct.toFixed(
                1,
              )}% · mean SOC ${(battery.mean_soc * 100).toFixed(0)}%`
            : 'not available'
        }
        icon={<Zap size={18} />}
        className="lg:col-span-2"
      />

      {/* Row 2 — 2 cards */}

      <MetricCard
        label="Diurnal Swing"
        value={grid?.diurnal_swing_mw?.toFixed(0) ?? '—'}
        unit="MW"
        trend={0}
        trendLabel="night vs noon (Phase 6.1 proxy)"
        icon={<BarChart2 size={18} />}
        className="lg:col-span-3"
      />

    
    </div>
  );
}