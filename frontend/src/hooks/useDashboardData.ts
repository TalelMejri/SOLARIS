import { useEffect, useState } from 'react';


const API_URL =
  'http://localhost:5000';

/* ============================================================
   Types
   ============================================================ */

export interface ForecastPoint {
  time: string;
  national_p10: number;
  national_p50: number;
  national_p90: number;
  national_true: number;
  capacity_mw: number;
}

export interface ForecastData {
  horizon: string;
  points: ForecastPoint[];
}

export interface Phase52Results {
  baseline: { h12_rmse: number; h24_rmse: number; h72_rmse: number };
  nwp: { h12_rmse: number; h24_rmse: number; h72_rmse: number };
  improvement_pct: { h12: number; h24: number; h72: number };
  districts_improved: number;
  districts_total: number;
  nwp_source: string;
  verification: string;
}

export interface BatteryData {
  peak_reduction_mw: number;
  peak_reduction_pct: number;
  total_charged_mwh: number;
  total_discharged_mwh: number;
  mean_soc: number;
}

export interface DashboardData {
  forecast: ForecastData | null;
  phase52: Phase52Results | null;
  battery: BatteryData | null;
  loading: boolean;
  error: string | null;
}

/* ============================================================
   Hook
   ============================================================ */

export function useDashboardData(horizon: string = 'h12'): DashboardData {
  const [forecast, setForecast] = useState<ForecastData | null>(null);
  const [phase52, setPhase52] = useState<Phase52Results | null>(null);
  const [battery, setBattery] = useState<BatteryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchAll = async () => {
      setLoading(true);
      setError(null);

      try {
        const [forecastRes, phase52Res, batteryRes] = await Promise.all([
          fetch(
            `${API_URL}/api/forecast/national/quantile?horizon=${horizon}&start=2022-07-01&end=2022-07-05`,
          ),
          fetch(`${API_URL}/api/methodology/phase52`),
          fetch(`${API_URL}/api/battery/simulation?horizon=${horizon}`),
        ]);

        if (!forecastRes.ok || !phase52Res.ok || !batteryRes.ok) {
          throw new Error(
            `API ${forecastRes.status}/${phase52Res.status}/${batteryRes.status}`,
          );
        }

        const forecastJson = await forecastRes.json();
        const phase52Json = await phase52Res.json();
        const batteryJson = await batteryRes.json();

        if (!cancelled) {
          setForecast(forecastJson);
          setPhase52(phase52Json);
          setBattery(batteryJson);
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

  return { forecast, phase52, battery, loading, error };
}