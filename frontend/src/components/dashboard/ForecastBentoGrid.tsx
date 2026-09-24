import MetricCard from '@/components/ui/MetricCard';
import {
  Sun,
  Activity,
  Target,
  Zap,
  Radio,
  AlertCircle,
  TrendingUp,
  Layers,
} from 'lucide-react';

import { useDashboardData } from '@/hooks/useDashboardData';

/* ============================================================
   Helpers
   ============================================================ */

const fmt = (n: number, digits: number = 1) =>
  n.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

/* ============================================================
   Component
   ============================================================ */

export default function ForecastBentoGrid() {
  const { forecast, phase52, battery, loading, error } =
    useDashboardData('h12');

  /* ---------- Loading ---------- */
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 7 }).map((_, i) => (
          <div
            key={i}
            className="card-elevated p-4 h-[140px] animate-pulse bg-muted/20"
          />
        ))}
      </div>
    );
  }

  /* ---------- Error ---------- */
  if (error || !forecast || !phase52 || !battery) {
    return (
      <div className="card-elevated p-5">
        <div className="flex items-start gap-2 text-sm text-[var(--status-critical)]">
          <AlertCircle size={14} className="mt-0.5" />
          <div>
            <p className="font-semibold">Failed to load dashboard data</p>
            <p className="text-xs text-muted-foreground mt-1">{error}</p>
            <p className="text-xs text-muted-foreground mt-1">
              Ensure the FastAPI backend is running on 8000.
            </p>
          </div>
        </div>
      </div>
    );
  }

  /* ---------- Derive real values ---------- */

  // Guard: points may be empty
  if (!forecast.points.length) {
    return (
      <div className="card-elevated p-5">
        <div className="flex items-start gap-2 text-sm text-[var(--status-critical)]">
          <AlertCircle size={14} className="mt-0.5" />
          <div>
            <p className="font-semibold">No forecast data available</p>
            <p className="text-xs text-muted-foreground mt-1">
              The quantile endpoint returned an empty points array.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Pick the peak daytime point (highest P50 across the window)
  const peakPoint = forecast.points.reduce(
    (max, p) => (p.national_p50 > max.national_p50 ? p : max),
    forecast.points[0],
  );

  const capacityMW = peakPoint.capacity_mw ?? 515.1;
  const forecastP50 = peakPoint.national_p50 ?? 0;
  const forecastP10 = peakPoint.national_p10 ?? 0;
  const forecastP90 = peakPoint.national_p90 ?? 0;
  const ciHalfWidth = (forecastP90 - forecastP10) / 2;

  const capacityFactor =
    capacityMW > 0 ? (forecastP50 / capacityMW) * 100 : 0;

  const avgImprovement =
    (phase52.improvement_pct.h12 +
      phase52.improvement_pct.h24 +
      phase52.improvement_pct.h72) /
    3;

  const batteryPeakReduction = battery.peak_reduction_mw;
  /* ---------- Render ---------- */

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {/* Row 1 — large card: aggregate forecast */}
      <div className="sm:col-span-2">
        <MetricCard
          label={`Aggregate Forecast · ${forecast.horizon.toUpperCase()}`}
          value={fmt(forecastP50, 1)}
          unit="MW"
          trend={avgImprovement}
          trendLabel={`vs no-NWP baseline`}
          icon={<Sun size={18} />}
          subValue={`±${fmt(ciHalfWidth, 1)} MW`}
          subLabel="P10–P90 interval"
          className="h-full"
        />
      </div>

      {/* Row 1 — RMSE improvement */}
      <MetricCard
        label="RMSE Improvement vs Baseline"
        value={fmt(avgImprovement, 2)}
        unit="%"
        trend={-avgImprovement}
        trendLabel="NWP vs no-NWP"
        icon={<Target size={18} />}
      />

      {/* Row 2 — capacity factor */}
      <MetricCard
        label="Capacity Factor · H+12"
        value={fmt(capacityFactor, 1)}
        unit="%"
        icon={<Activity size={18} />}
        subValue={`${fmt(capacityMW, 0)} MW`}
        subLabel="installed"
      />

      {/* Row 2 — interval width at peak */}
      <MetricCard
        label="Peak Interval Width"
        value={fmt(ciHalfWidth * 2, 1)}
        unit="MW"
        trend={0}
        trendLabel="P10–P90 width at peak"
        icon={<TrendingUp size={18} />}
        subValue={`P10 ${fmt(forecastP10, 0)} · P90 ${fmt(forecastP90, 0)}`}
        subLabel="bounds"
      />

      {/* Row 2 — battery peak reduction */}
      <MetricCard
        label="Peak Reduction · Battery"
        value={fmt(batteryPeakReduction, 1)}
        unit="MW"
        trend={battery.peak_reduction_pct}
        trendLabel="decision support proxy"
        icon={<Zap size={18} />}
        subValue={`${fmt(battery.mean_soc * 100, 1)}%`}
        subLabel="mean SOC"
      />

      {/* Row 3 — verified district coverage */}
      <MetricCard
        label="District Coverage"
        value={`${phase52.districts_improved}/${phase52.districts_total}`}
        unit="districts"
        icon={<Layers size={18} />}
        trend={0}
        trendLabel={`${((phase52.districts_improved / phase52.districts_total) * 100).toFixed(0)}% improved`}
        subValue="50"
        subLabel="total in dataset"
      />

      {/* Row 3 — verification status */}
      <MetricCard
        label="Verification Status"
        value={phase52.verification.split(' ')[0]}
        unit="checks"
        icon={<Radio size={18} />}
        trend={0}
        trendLabel={phase52.nwp_source}
        subValue="Phase 5.2"
        subLabel="verified"
      />
    </div>
  );
}