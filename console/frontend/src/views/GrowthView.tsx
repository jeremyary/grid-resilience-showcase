// This project was developed with assistance from AI tools.

import { useState } from "react";
import { GrowthScenarioForm } from "../components/GrowthScenarioForm";
import { GrowthResultsPanel } from "../components/GrowthResultsPanel";
import type { GrowthScenario, GrowthPrediction } from "../types/growth";

const API_BASE = "";

export function GrowthView() {
  const [prediction, setPrediction] = useState<GrowthPrediction | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (scenario: GrowthScenario) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/api/growth/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scenario),
      });
      if (!resp.ok) {
        throw new Error(`Prediction failed: ${resp.status}`);
      }
      const data: GrowthPrediction = await resp.json();
      setPrediction(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Prediction failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid-layout">
      <div style={{ flex: 1, minWidth: 0, overflow: "auto", padding: 16, paddingBottom: 80, background: "#f5f5f5" }}>
        <GrowthResultsPanel prediction={prediction} />
        {error && (
          <div className="grid-card">
            <div className="grid-card__body" style={{ color: "#A30000", fontSize: 13 }}>
              {error}
            </div>
          </div>
        )}
      </div>
      <div className="grid-layout__right">
        <GrowthScenarioForm onSubmit={handleSubmit} loading={loading} />
        {prediction && (
          <div className="grid-card">
            <div className="grid-card__header">Scenario Details</div>
            <div className="grid-card__body" style={{ fontSize: 12, color: "#6A6E73" }}>
              <div><strong>Name:</strong> {prediction.scenario.name}</div>
              {prediction.scenario.description && (
                <div style={{ marginTop: 4 }}>{prediction.scenario.description}</div>
              )}
              <div style={{ marginTop: 8 }}>
                <strong>Parameters:</strong>
                <div style={{ marginTop: 4, fontFamily: "monospace", fontSize: 11 }}>
                  {prediction.scenario.feeder_ids.length > 0
                    ? `Feeders: ${prediction.scenario.feeder_ids.join(", ")}`
                    : "Feeders: All"}
                </div>
                {prediction.scenario.new_residential > 0 && (
                  <div style={{ fontFamily: "monospace", fontSize: 11 }}>
                    New homes: {prediction.scenario.new_residential}
                  </div>
                )}
                {prediction.scenario.ev_adoption_pct > 0 && (
                  <div style={{ fontFamily: "monospace", fontSize: 11 }}>
                    EV adoption: {prediction.scenario.ev_adoption_pct}%
                  </div>
                )}
                {prediction.scenario.der_solar_kw > 0 && (
                  <div style={{ fontFamily: "monospace", fontSize: 11 }}>
                    Solar: {prediction.scenario.der_solar_kw} kW
                  </div>
                )}
                {prediction.scenario.annual_growth_pct > 0 && (
                  <div style={{ fontFamily: "monospace", fontSize: 11 }}>
                    Annual growth: {prediction.scenario.annual_growth_pct}%
                  </div>
                )}
                <div style={{ fontFamily: "monospace", fontSize: 11 }}>
                  Horizon: {prediction.scenario.horizon_years} years
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
