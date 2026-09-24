import { useEffect, useState, useMemo } from 'react';
import MetricCard from '@/components/ui/MetricCard';
import { Radio, Zap, AlertTriangle, MapPin } from 'lucide-react';

/* ============================================================
   API — env-aware, default port 8000
   ============================================================ */

const API_URL =
  'http://localhost:5000';

/* ============================================================
   Types
   ============================================================ */

interface DistrictRow {
  district_id: number;
  district_name: string;
  region_name: string;
  capacity_mw: number;
  forecast_mw: number;
  forecast_p50: number;
}

interface RegionRow {
  region_id: number;
  region_name: string;
  capacity_mw: number;
  forecast_mw: number;
  n_districts: number;
}

/* ============================================================
   Component
   ============================================================ */

export default function InstallationKPICards() {
  const [districts, setDistricts] = useState<DistrictRow[]>([]);
  const [regions, setRegions] = useState<RegionRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      try {
        const [dRes, rRes] = await Promise.all([
          fetch(
            `${API_URL}/api/districts/quantile?horizon=h12&timestamp=2022-07-01T12:00:00+00:00`,
          ).catch(() => null),
          fetch(
            `${API_URL}/api/regions?horizon=h12&timestamp=2022-07-01T12:00:00+00:00`,
          ).catch(() => null),
        ]);

        if (cancelled) return;

        if (dRes?.ok) {
          const j = await dRes.json();
          const raw: any[] = j.districts ?? [];

          // Dedupe + normalize
          const seen = new Set<number>();
          const cleaned: DistrictRow[] = [];
          for (const d of raw) {
            const id = Number(d.district_id);
            if (seen.has(id)) continue;
            seen.add(id);

            const cap = Number(d.capacity_mw) || 0;
            const p50 = Number(d.forecast_p50 ?? d.forecast_mw) || 0;

            cleaned.push({
              district_id: id,
              district_name: String(d.district_name ?? ''),
              region_name: String(d.region_name ?? ''),
              capacity_mw: cap,
              forecast_mw: p50,
              forecast_p50: p50,
            });
          }
          setDistricts(cleaned);
        }

        if (rRes?.ok) {
          const j = await rRes.json();
          setRegions(j.regions ?? []);
        }

        setLoading(false);
      } catch {
        if (!cancelled) setLoading(false);
      }
    };

    fetchData();
    return () => {
      cancelled = true;
    };
  }, []);

  /* ---------- Derived metrics ---------- */

  const metrics = useMemo(() => {
    if (!districts.length) {
      return {
        totalCapacity: 0,
        activeDistricts: 0,
        highUtilDistricts: 0,
        regionsCount: 0,
        meanUtil: 0,
      };
    }

    const totalCapacity = districts.reduce(
      (s, d) => s + d.capacity_mw,
      0,
    );

    // Realistic threshold for distributed rooftop PV.
    // Fleet utilization peaks at 55–65% at noon in Tunisia.
    const HIGH_UTIL_THRESHOLD = 0.5;

    const activeDistricts = districts.filter(
      (d) => d.forecast_mw > 0.01,
    ).length;

    const highUtil = districts.filter((d) => {
      const util =
        d.capacity_mw > 0 ? d.forecast_mw / d.capacity_mw : 0;
      return util > HIGH_UTIL_THRESHOLD;
    }).length;

    const meanUtil =
      districts.reduce((s, d) => {
        const util =
          d.capacity_mw > 0 ? d.forecast_mw / d.capacity_mw : 0;
        return s + util;
      }, 0) / districts.length;

    return {
      totalCapacity,
      activeDistricts,
      highUtilDistricts: highUtil,
      regionsCount: regions.length || 7,
      meanUtil,
    };
  }, [districts, regions]);

  /* ---------- Loading ---------- */

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="card-elevated h-[100px] animate-pulse bg-muted/20"
          />
        ))}
      </div>
    );
  }

  /* ---------- Render ---------- */

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard
        label="Total Registered Capacity"
        value={metrics.totalCapacity.toFixed(1)}
        unit="MWp"
        trend={0}
        trendLabel="Prosol July 2026 snapshot"
        icon={<Zap size={18} />}
        subValue={`${districts.length}`}
        subLabel="districts"
      />
      <MetricCard
        label="Regions"
        value={metrics.regionsCount.toString()}
        unit="of 7"
        trend={0}
        trendLabel="District → Region → Tunisia"
        icon={<MapPin size={18} />}
      />
    </div>
  );
}