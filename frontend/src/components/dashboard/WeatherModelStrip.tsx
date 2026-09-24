'use client';

import { Wind, Thermometer, Cloud, Cpu, CheckCircle, Activity } from 'lucide-react';

import { useWeatherModelStrip } from '@/hooks/useWeatherModelStrip';

// ============================================================
// HELPERS
// ============================================================

const fmt = (n: number | null | undefined, digits = 1) =>
  n === null || n === undefined
    ? '—'
    : n.toLocaleString('en-US', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });

// ============================================================
// COMPONENT
// ============================================================

export default function WeatherModelStrip() {
  const { districts, metrics, loading, error } = useWeatherModelStrip('h12');



  // ---------- Loading ----------
  if (loading) {
    return (
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 card-elevated p-4 h-40 animate-pulse bg-muted/20" />
        <div className="card-elevated p-4 h-40 animate-pulse bg-muted/20" />
      </div>
    );
  }

  // ---------- Error ----------
  if (error || !metrics) {
    return (
      <div className="card-elevated p-5">
        <p className="text-sm text-[var(--status-critical)]">
          Failed to load weather and model data: {error}
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          Ensure the FastAPI backend is running.
        </p>
      </div>
    );
  }

  // ---------- All districts ----------
  const allDistricts = districts;

  // ---------- Model status ----------
  const models = [
    {
      id: 'lightgbm-h12',
      name: 'LightGBM · H+12',
      status: 'Ready',
      rmse: `${(metrics.nwp.h12_rmse * 100).toFixed(2)}%`,
      ran: 'Verified',
      improvement: metrics.improvement_pct.h12,
    },
    {
      id: 'lightgbm-h24',
      name: 'LightGBM · H+24',
      status: 'Ready',
      rmse: `${(metrics.nwp.h24_rmse * 100).toFixed(2)}%`,
      ran: 'Verified',
      improvement: metrics.improvement_pct.h24,
    },
    {
      id: 'lightgbm-h72',
      name: 'LightGBM · H+72',
      status: 'Ready',
      rmse: `${(metrics.nwp.h72_rmse * 100).toFixed(2)}%`,
      ran: 'Verified',
      improvement: metrics.improvement_pct.h72,
    },
  ];

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      {/* -------- All 50 Districts NWP Weather -------- */}
      <div className="xl:col-span-2 card-elevated p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              NWP Forecast · All Districts · H+12
            </p>
            <p className="text-2xs text-muted-foreground mt-0.5">
              {allDistricts.length} Prosol districts · TIGGE / ECMWF
            </p>
          </div>
          <span className="flex items-center gap-1.5 text-2xs text-primary">
            <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
            Real forecast
          </span>
        </div>

        {allDistricts.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No district data available at this timestamp.
          </p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-5 gap-2">
            {allDistricts.map((d) => (
              <div
                key={d.district_id}
                className="bg-muted/40 rounded-lg p-2.5 space-y-1"
              >
                <p
                  className="text-2xs font-semibold text-foreground truncate"
                  title={d.district_name}
                >
                  {d.district_name}
                </p>

                {/* Cloud (proxy for irradiance) */}
                <div className="flex items-center gap-1 text-accent">
                  <Activity size={10} />
                  <span className="font-tabular text-2xs font-semibold">
                    {Math.round(d.utilization * 100)}
                  </span>
                  <span className="text-2xs text-muted-foreground">%</span>
                </div>

                {/* Temperature + Wind */}
                <div className="flex items-center gap-2 text-2xs text-muted-foreground">
                  <span className="flex items-center gap-0.5">
                    <Thermometer size={9} />
                    {fmt(d.temperature_2m_c, 0)}°
                  </span>
                  <span className="flex items-center gap-0.5">
                    <Wind size={9} />
                    {fmt(d.wind_speed_10m_ms, 0)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        <p className="text-2xs text-muted-foreground mt-3 pt-2 border-t border-border">
          Source: ECMWF TIGGE NWP forecast · temperature (°C), wind speed (m/s),
          cloud cover (%) · Real forecast values, not observed weather.
        </p>
      </div>

      {/* -------- Model Status -------- */}
      <div className="card-elevated p-4">
        <div className="flex items-center gap-2 mb-3">
          <Cpu size={14} className="text-primary" />
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            LightGBM NWP Models
          </p>
        </div>

        <div className="space-y-2.5">
          {models.map((m) => (
            <div
              key={m.id}
              className="flex items-center justify-between bg-muted/40 rounded-lg px-3 py-2"
            >
              <div>
                <p className="text-xs font-semibold text-foreground">
                  {m.name}
                </p>
                <p className="text-2xs text-muted-foreground">
                  {m.ran} · {m.improvement.toFixed(2)}% improvement
                </p>
              </div>
              <div className="text-right">
                <div className="flex items-center gap-1 justify-end">
                  <CheckCircle size={11} className="text-primary" />
                  <span className="text-2xs font-medium text-primary">
                    {m.status}
                  </span>
                </div>
                <p className="font-tabular text-2xs text-muted-foreground">
                  RMSE {m.rmse}
                </p>
              </div>
            </div>
          ))}
        </div>

        <p className="text-2xs text-muted-foreground mt-3 pt-2 border-t border-border">
          {metrics.verification} · Source: {metrics.nwp_source}
        </p>
      </div>
    </div>
  );
}