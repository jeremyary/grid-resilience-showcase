// This project was developed with assistance from AI tools.

import type { GrowthPrediction } from "../types/growth";

interface GrowthResultsPanelProps {
  prediction: GrowthPrediction | null;
}

function statusBadge(status: string): string {
  if (status === "overloaded") return "grid-risk-badge grid-risk-badge--critical";
  if (status === "at_risk") return "grid-risk-badge grid-risk-badge--medium";
  return "grid-risk-badge grid-risk-badge--low";
}

function utilizationBar(pct: number, status: string): React.CSSProperties {
  const color = status === "overloaded" ? "#A30000" : status === "at_risk" ? "#F0AB00" : "#3E8635";
  return {
    height: 6,
    borderRadius: 3,
    background: "#E0E0E0",
    position: "relative" as const,
    overflow: "hidden",
  };
}

export function GrowthResultsPanel({ prediction }: GrowthResultsPanelProps) {
  if (!prediction) {
    return (
      <div className="grid-card">
        <div className="grid-card__header">Growth Projection</div>
        <div className="grid-card__body" style={{ color: "#6A6E73", fontSize: 12 }}>
          Select a scenario and run a prediction to see results.
        </div>
      </div>
    );
  }

  const flagged = prediction.at_risk_assets.filter((a) => a.status !== "ok");
  const newlyFlagged = flagged.filter((a) => a.newly_at_risk);
  const baselineFlagged = flagged.filter((a) => !a.newly_at_risk);

  return (
    <>
      <div className="grid-card">
        <div className="grid-card__header">Summary</div>
        <div className="grid-card__body">
          <div style={{ fontSize: 13, lineHeight: 1.5, marginBottom: 12 }}>{prediction.summary}</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 12 }}>
            <div className="grid-metric" style={{ borderLeftColor: "#0066CC" }}>
              <div className="grid-metric__label">New Load (added demand)</div>
              <div className="grid-metric__value" style={{ fontSize: 18 }}>{prediction.total_new_load_mw} MW</div>
            </div>
            <div className="grid-metric" style={{ borderLeftColor: "#F0AB00" }}>
              <div className="grid-metric__label">Corridor Util (% of total capacity)</div>
              <div className="grid-metric__value" style={{ fontSize: 18 }}>{prediction.corridor_utilization_pct}%</div>
            </div>
            <div className="grid-metric" style={{ borderLeftColor: "#A30000" }}>
              <div className="grid-metric__label">Newly At Risk</div>
              <div className="grid-metric__value" style={{ fontSize: 18 }}>{newlyFlagged.length}</div>
            </div>
          </div>
          {flagged.length > 0 && (
            <div style={{
              padding: "10px 14px",
              background: flagged.some((a) => a.status === "overloaded") ? "#F8D7DA" : "#FFF3CD",
              borderRadius: 4,
              fontSize: 13,
              lineHeight: 1.5,
            }}>
              <strong>Recommendation: </strong>
              {newlyFlagged.length > 0 && `${newlyFlagged.length} impacted by this scenario. `}
              {baselineFlagged.length > 0 && `${baselineFlagged.length} already at risk at baseline. `}
              {`${flagged.length} transformer${flagged.length > 1 ? "s" : ""} require upgrade — see details below.`}
            </div>
          )}
        </div>
      </div>

      <div className="grid-card">
        <div className="grid-card__header">Feeder Projections</div>
        <div className="grid-card__body--flush" style={{ overflowX: "auto" }}>
          <table className="grid-risk-table">
            <thead>
              <tr>
                <th>Feeder</th>
                <th>Current</th>
                <th>Projected</th>
                <th>Capacity</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {prediction.feeders.map((f) => (
                <tr key={f.feeder_id}>
                  <td className="grid-mono">{f.feeder_id}</td>
                  <td>{f.current_load_mw} MW ({f.current_utilization_pct}%)</td>
                  <td>{f.projected_load_mw} MW ({f.projected_utilization_pct}%)</td>
                  <td>{f.normal_capacity_mw} MW</td>
                  <td><span className={statusBadge(f.status)}>{f.status.replace("_", " ")}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {flagged.length > 0 && (
        <div className="grid-card">
          <div className="grid-card__header">
            Transformers Requiring Attention ({flagged.length})
          </div>
          <div className="grid-card__body--flush" style={{ overflowX: "auto" }}>
            <table className="grid-risk-table">
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Feeder</th>
                  <th>Current</th>
                  <th>Projected</th>
                  <th>Status</th>
                  <th>Recommendation</th>
                </tr>
              </thead>
              <tbody>
                {flagged.map((a) => (
                  <tr key={a.asset_id}>
                    <td className="grid-mono">
                      {a.asset_id}
                      {a.newly_at_risk ? (
                        <span style={{ marginLeft: 4, fontSize: 9, color: "#A30000", fontWeight: 600 }}>SCENARIO</span>
                      ) : a.status !== "ok" ? (
                        <span style={{ marginLeft: 4, fontSize: 9, color: "#6A6E73", fontWeight: 600 }}>BASELINE</span>
                      ) : null}
                    </td>
                    <td className="grid-mono">{a.feeder_id}</td>
                    <td>{a.rated_kva} kVA → {a.current_utilization_pct}%</td>
                    <td style={{ fontWeight: 600 }}>{a.projected_utilization_pct}%</td>
                    <td><span className={statusBadge(a.status)}>{a.status.replace("_", " ")}</span></td>
                    <td style={{ fontSize: 11 }}>{a.recommendation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
