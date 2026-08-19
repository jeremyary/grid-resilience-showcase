// This project was developed with assistance from AI tools.

import type { AssetProjection, MitigationOption } from "../types/growth";

interface MitigationModalProps {
  asset: AssetProjection | null;
  horizonYears: number;
  onClose: () => void;
}

const STATUS_COLOR: Record<string, string> = {
  overloaded: "#A30000",
  at_risk: "#F0AB00",
  ok: "#3E8635",
};

function statusColor(status: string | null): string {
  return (status && STATUS_COLOR[status]) || "#6A6E73";
}

function formatCost(low: number | null, high: number | null): string {
  if (low == null || high == null) return "—";
  const fmt = (n: number) => `$${(n / 1000).toFixed(0)}K`;
  return `${fmt(low)}–${fmt(high)}`;
}

function MitigationCard({ option, horizonYears }: { option: MitigationOption; horizonYears: number }) {
  const dim = !option.available;
  const midCost =
    option.cost_low != null && option.cost_high != null
      ? (option.cost_low + option.cost_high) / 2
      : null;
  const perYear = midCost != null && option.years_gained ? midCost / option.years_gained : null;

  const borderColor = option.recommended ? "#3E8635" : option.most_durable ? "#0066CC" : null;
  const headerBg = option.recommended ? "#EAF3EA" : option.most_durable ? "#E7F1FB" : "#F3F3F3";

  return (
    <div
      style={{
        flex: "1 1 0",
        minWidth: 200,
        border: borderColor ? `2px solid ${borderColor}` : "1px solid #E0E0E0",
        borderRadius: 6,
        background: dim ? "#F7F7F7" : "#FFFFFF",
        opacity: dim ? 0.7 : 1,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "10px 12px",
          background: headerBg,
          borderBottom: "1px solid #E0E0E0",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "'Public Sans', sans-serif" }}>
          {option.label}
        </span>
        {option.recommended && (
          <span style={{ ...badge, background: "#3E8635" }}>BEST VALUE</span>
        )}
        {option.most_durable && (
          <span style={{ ...badge, background: "#0066CC" }}>MOST DURABLE</span>
        )}
      </div>

      <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: 10, flex: 1 }}>
        {!option.available ? (
          <div style={{ fontSize: 12, color: "#6A6E73", lineHeight: 1.5 }}>
            <div style={{ fontWeight: 600, color: "#A30000", marginBottom: 4 }}>Not available</div>
            {option.unavailable_reason}
          </div>
        ) : (
          <>
            <div style={{ fontSize: 12, color: "#151515", fontWeight: 600 }}>{option.description}</div>

            <div>
              <div style={metricLabel}>Planning-level cost estimate</div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>{formatCost(option.cost_low, option.cost_high)}</div>
            </div>

            <div>
              <div style={metricLabel}>Resulting utilization</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: statusColor(option.resulting_status) }}>
                {option.resulting_utilization_pct}%
              </div>
            </div>

            {option.years_gained != null && (
              <div>
                <div style={metricLabel}>Headroom beyond outlook</div>
                <div style={{ fontSize: 16, fontWeight: 700 }}>
                  +{option.years_gained} {option.years_gained === 1 ? "yr" : "yrs"}
                </div>
                <div style={{ fontSize: 11, color: "#151515", fontWeight: 600, marginTop: 1 }}>
                  past {horizonYears}-yr outlook
                  {perYear != null && `: ~$${(perYear / 1000).toFixed(1)}K/yr of headroom`}
                </div>
              </div>
            )}

            {option.capacity_added_kva != null && (
              <div>
                <div style={metricLabel}>Capacity added</div>
                <div style={{ fontSize: 13 }}>+{option.capacity_added_kva.toFixed(0)} kVA</div>
              </div>
            )}

            {option.load_transferred_kva != null && (
              <div>
                <div style={metricLabel}>Load transferred</div>
                <div style={{ fontSize: 13 }}>{option.load_transferred_kva.toFixed(0)} kVA</div>
              </div>
            )}

            {option.target_asset_id && (
              <div>
                <div style={metricLabel}>Receiving transformer</div>
                <div style={{ fontSize: 12 }}>
                  <span className="grid-mono">{option.target_asset_id}</span>{" "}
                  <span style={{ color: "#6A6E73" }}>
                    {option.target_before_utilization_pct}% → {option.target_after_utilization_pct}%
                  </span>
                </div>
              </div>
            )}

            {option.note && (
              <div
                style={{
                  fontSize: 11,
                  color: option.note.startsWith("Good") ? "#3E8635" : "#8A6D00",
                  fontWeight: 600,
                  lineHeight: 1.4,
                  marginTop: "auto",
                }}
              >
                {option.note.startsWith("Good") ? "" : "⚠ "}
                {option.note}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

const metricLabel: React.CSSProperties = {
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: 0.5,
  color: "#6A6E73",
  marginBottom: 2,
};

const badge: React.CSSProperties = {
  fontSize: 9,
  fontWeight: 700,
  letterSpacing: 0.5,
  color: "#fff",
  padding: "2px 6px",
  borderRadius: 3,
  whiteSpace: "nowrap",
};

export function MitigationModal({ asset, horizonYears, onClose }: MitigationModalProps) {
  if (!asset) return null;
  const hasLoadTransfer = asset.mitigations.some((m) => m.type === "load_transfer" && m.available);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(21,21,21,0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          borderRadius: 8,
          maxWidth: 860,
          width: "100%",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 8px 32px rgba(0,0,0,0.35)",
          fontFamily: "Inter, sans-serif",
        }}
      >
        <div
          style={{
            padding: "14px 18px",
            borderBottom: "1px solid #E0E0E0",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, fontFamily: "'Public Sans', sans-serif" }}>
              Mitigation Options
            </div>
            <div style={{ fontSize: 12, color: "#6A6E73", marginTop: 2 }}>
              <span className="grid-mono">{asset.asset_id}</span> · {asset.rated_kva} kVA · projected{" "}
              <span style={{ fontWeight: 700, color: statusColor(asset.status) }}>
                {asset.projected_utilization_pct}%
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "#6A6E73",
              cursor: "pointer",
              fontSize: 20,
              lineHeight: 1,
              padding: 4,
            }}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div style={{ padding: 18, overflowY: "auto" }}>
          <div style={{ fontSize: 12, color: "#6A6E73", lineHeight: 1.5, marginBottom: 12 }}>
            Each option is sized against the projected load at the end of the {horizonYears}-year
            outlook, and is only offered when its resulting utilization lands below the 80% planning
            threshold. "Headroom beyond outlook" estimates the additional years of growth the fix
            absorbs past the outlook at the scenario's growth rate. <strong>Best value</strong> is
            the lowest cost per year of headroom; when a load transfer wins on value, the
            longest-lived capital fix is flagged <strong>most durable</strong> so the fix-now vs
            fix-right tradeoff stays your call.
          </div>

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {asset.mitigations.map((m) => (
              <MitigationCard key={m.type} option={m} horizonYears={horizonYears} />
            ))}
          </div>

          <div style={{ fontSize: 11, color: "#6A6E73", lineHeight: 1.5, marginTop: 16 }}>
            Cost figures are planning-level order-of-magnitude estimates for early screening, not
            engineered quotes.
            {hasLoadTransfer && (
              <>
                {" "}
                Load transfer impact is estimated arithmetically; v1 does not validate switching
                feasibility or re-solve the post-transfer network with power flow.
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
