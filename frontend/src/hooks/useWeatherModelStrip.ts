import { useEffect, useState } from 'react';


const API_URL =
  'http://localhost:5000';

/* ============================================================
   Types
   ============================================================ */

export interface DistrictWeather {
  district_id: number;
  district_name: string;
  region_name: string;
  capacity_mw: number;
  forecast_mw: number;
  forecast_p10: number;
  forecast_p90: number;
  forecast_normalized: number;
  utilization: number;
  temperature_2m_c: number | null;
  wind_speed_10m_ms: number | null;
  wind_direction_10m_deg: number | null;
  cloud_cover_fraction: number | null;
}

export interface Phase52Metrics {
  improvement_pct: { h12: number; h24: number; h72: number };
  nwp: { h12_rmse: number; h24_rmse: number; h72_rmse: number };
  verification: string;
  nwp_source: string;
}

export interface WeatherModelStripData {
  districts: DistrictWeather[];
  metrics: Phase52Metrics | null;
  loading: boolean;
  error: string | null;
}

/* ============================================================
   Safe number helpers
   ============================================================ */

const safeNum = (v: unknown, fallback = 0): number => {
  if (v === null || v === undefined) return fallback;
  const n = typeof v === 'number' ? v : Number(v);
  return isNaN(n) || !isFinite(n) ? fallback : n;
};

/* ============================================================
   Hook
   ============================================================ */

export function useWeatherModelStrip(
  horizon: string = 'h12',
): WeatherModelStripData {
  const [districts, setDistricts] = useState<DistrictWeather[]>([]);
  const [metrics, setMetrics] = useState<Phase52Metrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchAll = async () => {
      setLoading(true);
      setError(null);

      try {
        const ts = '2022-07-01T12:00:00+00:00';

        const [districtsRes, metricsRes] = await Promise.all([
          fetch(
            `${API_URL}/api/districts?horizon=${horizon}&timestamp=${encodeURIComponent(ts)}`,
          ),
          fetch(`${API_URL}/api/methodology/phase52`),
        ]);

        if (!districtsRes.ok || !metricsRes.ok) {
          throw new Error(
            `API ${districtsRes.status}/${metricsRes.status}`,
          );
        }

        const districtsJson = await districtsRes.json();
        const metricsJson = await metricsRes.json();

        if (cancelled) return;

        // -------- Dedupe + sanitize --------
        const raw: any[] = districtsJson.districts ?? [];
        const seen = new Set<number>();
        const cleaned: DistrictWeather[] = [];

        for (const d of raw) {
          const did = safeNum(d.district_id, -1);
          if (did < 0 || seen.has(did)) continue;
          seen.add(did);

          const capacity = safeNum(d.capacity_mw, 0);
          const forecast = safeNum(d.forecast_mw, 0);
          const rawUtil = safeNum(d.utilization, NaN);

          // Prefer API utilization if present and valid; otherwise compute
          const util =
            !isNaN(rawUtil) && rawUtil >= 0
              ? Math.min(1, rawUtil)
              : capacity > 0
                ? Math.min(1, Math.max(0, forecast / capacity))
                : 0;

          cleaned.push({
            district_id: did,
            district_name: String(d.district_name ?? '—'),
            region_name: String(d.region_name ?? '—'),
            capacity_mw: capacity,
            forecast_mw: forecast,
            forecast_p10: safeNum(d.forecast_p10, forecast),
            forecast_p90: safeNum(d.forecast_p90, forecast),
            forecast_normalized: safeNum(d.forecast_normalized, 0),
            utilization: util,
            temperature_2m_c:
              d.temperature_2m_c !== null && d.temperature_2m_c !== undefined
                ? safeNum(d.temperature_2m_c, NaN)
                : null,
            wind_speed_10m_ms:
              d.wind_speed_10m_ms !== null && d.wind_speed_10m_ms !== undefined
                ? safeNum(d.wind_speed_10m_ms, NaN)
                : null,
            wind_direction_10m_deg:
              d.wind_direction_10m_deg !== null &&
              d.wind_direction_10m_deg !== undefined
                ? safeNum(d.wind_direction_10m_deg, NaN)
                : null,
            cloud_cover_fraction:
              d.cloud_cover_fraction !== null &&
              d.cloud_cover_fraction !== undefined
                ? safeNum(d.cloud_cover_fraction, NaN)
                : null,
          });
        }

        // Sort by district_id for consistent ordering
        cleaned.sort((a, b) => a.district_id - b.district_id);

        if (!cancelled) {
          setDistricts(cleaned);
          setMetrics(metricsJson);
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
  }, [horizon]);

  return { districts, metrics, loading, error };
}