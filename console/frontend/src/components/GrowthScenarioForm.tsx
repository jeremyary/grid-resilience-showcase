// This project was developed with assistance from AI tools.

import { useEffect, useState } from "react";
import type { GrowthScenario } from "../types/growth";

const API_BASE = "";

interface GrowthScenarioFormProps {
  onSubmit: (scenario: GrowthScenario) => void;
  loading: boolean;
}

const EMPTY_SCENARIO: GrowthScenario = {
  name: "Custom Scenario",
  description: "",
  feeder_ids: [],
  new_residential: 0,
  ev_adoption_pct: 0,
  der_solar_kw: 0,
  annual_growth_pct: 0,
  horizon_years: 5,
};

const FEEDER_OPTIONS = ["F-11", "F-12", "F-13", "F-14"];

export function GrowthScenarioForm({ onSubmit, loading }: GrowthScenarioFormProps) {
  const [presets, setPresets] = useState<GrowthScenario[]>([]);
  const [scenario, setScenario] = useState<GrowthScenario>(EMPTY_SCENARIO);
  const [selectedPreset, setSelectedPreset] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/api/growth/presets`)
      .then((r) => r.json())
      .then((data) => setPresets(data))
      .catch(() => {});
  }, []);

  const handlePresetChange = (name: string) => {
    setSelectedPreset(name);
    if (name === "") {
      setScenario(EMPTY_SCENARIO);
      return;
    }
    const preset = presets.find((p) => p.name === name);
    if (preset) setScenario({ ...preset });
  };

  const update = (field: keyof GrowthScenario, value: string | number | string[]) => {
    setSelectedPreset("");
    setScenario((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <div className="grid-card">
      <div className="grid-card__header">Growth Scenario</div>
      <div className="grid-card__body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <label style={{ fontSize: 11, fontWeight: 600, color: "#6A6E73", textTransform: "uppercase" }}>
          Preset
          <select
            value={selectedPreset}
            onChange={(e) => handlePresetChange(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 4, padding: "6px 8px", fontSize: 13, border: "1px solid #E0E0E0", borderRadius: 4 }}
          >
            <option value="">Custom</option>
            {presets.map((p) => (
              <option key={p.name} value={p.name}>{p.name}</option>
            ))}
          </select>
        </label>

        <label style={{ fontSize: 11, fontWeight: 600, color: "#6A6E73", textTransform: "uppercase" }}>
          Target Feeders
          <select
            multiple
            value={scenario.feeder_ids}
            onChange={(e) => update("feeder_ids", Array.from(e.target.selectedOptions, (o) => o.value))}
            style={{ display: "block", width: "100%", marginTop: 4, padding: "4px 8px", fontSize: 13, border: "1px solid #E0E0E0", borderRadius: 4, height: 72 }}
          >
            {FEEDER_OPTIONS.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
          <span style={{ fontSize: 10, color: "#6A6E73", fontWeight: 400 }}>Leave empty for all feeders</span>
        </label>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: "#6A6E73", textTransform: "uppercase" }}>
            New Homes
            <input
              type="number" min={0} value={scenario.new_residential}
              onChange={(e) => update("new_residential", parseInt(e.target.value) || 0)}
              style={{ display: "block", width: "100%", marginTop: 4, padding: "6px 8px", fontSize: 13, border: "1px solid #E0E0E0", borderRadius: 4 }}
            />
          </label>
          <label style={{ fontSize: 11, fontWeight: 600, color: "#6A6E73", textTransform: "uppercase" }}>
            EV Adoption %
            <input
              type="number" min={0} max={100} step={5} value={scenario.ev_adoption_pct}
              onChange={(e) => update("ev_adoption_pct", parseFloat(e.target.value) || 0)}
              style={{ display: "block", width: "100%", marginTop: 4, padding: "6px 8px", fontSize: 13, border: "1px solid #E0E0E0", borderRadius: 4 }}
            />
          </label>
          <label style={{ fontSize: 11, fontWeight: 600, color: "#6A6E73", textTransform: "uppercase" }}>
            Solar (kW)
            <input
              type="number" min={0} step={100} value={scenario.der_solar_kw}
              onChange={(e) => update("der_solar_kw", parseFloat(e.target.value) || 0)}
              style={{ display: "block", width: "100%", marginTop: 4, padding: "6px 8px", fontSize: 13, border: "1px solid #E0E0E0", borderRadius: 4 }}
            />
          </label>
          <label style={{ fontSize: 11, fontWeight: 600, color: "#6A6E73", textTransform: "uppercase" }}>
            Annual Growth %
            <input
              type="number" min={0} max={20} step={0.5} value={scenario.annual_growth_pct}
              onChange={(e) => update("annual_growth_pct", parseFloat(e.target.value) || 0)}
              style={{ display: "block", width: "100%", marginTop: 4, padding: "6px 8px", fontSize: 13, border: "1px solid #E0E0E0", borderRadius: 4 }}
            />
          </label>
        </div>

        <label style={{ fontSize: 11, fontWeight: 600, color: "#6A6E73", textTransform: "uppercase" }}>
          Horizon (years): {scenario.horizon_years}
          <input
            type="range" min={1} max={30} value={scenario.horizon_years}
            onChange={(e) => update("horizon_years", parseInt(e.target.value))}
            style={{ display: "block", width: "100%", marginTop: 4 }}
          />
        </label>

        <button
          onClick={() => onSubmit(scenario)}
          disabled={loading}
          className="grid-controls__button grid-controls__button--primary"
          style={{ width: "100%", padding: "8px 16px", fontSize: 13 }}
        >
          {loading ? "Running Prediction..." : "Run Prediction"}
        </button>
      </div>
    </div>
  );
}
