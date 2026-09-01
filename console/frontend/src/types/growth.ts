// This project was developed with assistance from AI tools.

export interface GrowthScenario {
  name: string;
  description: string;
  feeder_ids: string[];
  new_residential: number;
  ev_adoption_pct: number;
  der_solar_kw: number;
  annual_growth_pct: number;
  horizon_years: number;
}

export interface FeederProjection {
  feeder_id: string;
  feeder_name: string;
  current_load_mw: number;
  projected_load_mw: number;
  normal_capacity_mw: number;
  emergency_capacity_mw: number;
  current_utilization_pct: number;
  projected_utilization_pct: number;
  status: "ok" | "at_risk" | "overloaded";
  overload_year: number | null;
  headroom_mw: number;
}

export interface MitigationOption {
  type: string;
  label: string;
  description: string;
  available: boolean;
  unavailable_reason: string | null;
  cost_low: number | null;
  cost_high: number | null;
  capacity_added_kva: number | null;
  load_transferred_kva: number | null;
  resulting_utilization_pct: number | null;
  resulting_status: "ok" | "at_risk" | "overloaded" | null;
  target_asset_id: string | null;
  target_before_utilization_pct: number | null;
  target_after_utilization_pct: number | null;
  years_gained: number | null;
  recommended: boolean;
  most_durable: boolean;
  note: string;
}

export interface AssetProjection {
  asset_id: string;
  asset_type: string;
  feeder_id: string;
  rated_kva: number;
  current_load_kva: number;
  projected_load_kva: number;
  current_utilization_pct: number;
  projected_utilization_pct: number;
  baseline_status: "ok" | "at_risk" | "overloaded";
  status: "ok" | "at_risk" | "overloaded";
  newly_at_risk: boolean;
  overload_year: number | null;
  mitigations: MitigationOption[];
  lat: number;
  lon: number;
}

export interface YearlySnapshot {
  year: number;
  feeder_utilization_pct: Record<string, number>;
  feeder_load_mw: Record<string, number>;
  asset_utilization_pct: Record<string, number>;
}

export interface GrowthPrediction {
  scenario: GrowthScenario;
  feeders: FeederProjection[];
  at_risk_assets: AssetProjection[];
  summary: string;
  total_new_load_mw: number;
  corridor_utilization_pct: number;
  yearly_projections: YearlySnapshot[];
}
