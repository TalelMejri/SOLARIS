// src/types/api.ts
export type Horizon = 'h12' | 'h24' | 'h72';

export interface RegionSnapshot {
  region_id: number;
  region_name: string;
  capacity_mw: number;
  forecast_mw: number;
  forecast_normalized?: number;   // present if backend returns it
  n_districts: number;
}

export interface DistrictSnapshot {
  district_id: number;
  district_name: string;
  region_id: number;
  region_name: string;
  latitude: number;
  longitude: number;
  capacity_mw: number;
  forecast_mw: number;
  forecast_normalized: number;
}

export interface NationalTimeline {
  hours: number[];
  load_mw: number[];
  pv_mw: number[];
  pv_lo_mw: number[];
  pv_hi_mw: number[];
}

export interface NationalSnapshot {
  pv: number;
  load: number;
  net: number;
  pvLo: number;
  pvHi: number;
  share: number;
  rampNextHour: number;
}