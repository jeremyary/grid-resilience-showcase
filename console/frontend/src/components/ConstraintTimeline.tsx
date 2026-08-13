// This project was developed with assistance from AI tools.

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { FeederProjection, YearlySnapshot } from "../types/growth";

interface ConstraintTimelineProps {
  feeders: FeederProjection[];
  yearlyProjections: YearlySnapshot[];
  horizonYears: number;
}

const FEEDER_COLORS: Record<string, string> = {
  "F-11": "#2a78d6",
  "F-12": "#eb6834",
  "F-13": "#1baf7a",
  "F-14": "#eda100",
};

function buildChartData(
  feeders: FeederProjection[],
  snapshots: YearlySnapshot[],
): Record<string, number | string>[] {
  const feederIds = feeders.map((f) => f.feeder_id);
  const currentYear = new Date().getFullYear();

  const year0: Record<string, number | string> = { year: currentYear };
  for (const f of feeders) {
    year0[f.feeder_id] = f.current_utilization_pct;
  }

  const rows = [year0];
  for (const snap of snapshots) {
    const row: Record<string, number | string> = { year: currentYear + snap.year };
    for (const fid of feederIds) {
      row[fid] = snap.feeder_utilization_pct[fid] ?? 0;
    }
    rows.push(row);
  }

  return rows;
}

export function ConstraintTimeline({ feeders, yearlyProjections, horizonYears }: ConstraintTimelineProps) {
  if (!yearlyProjections || yearlyProjections.length === 0) return null;

  const feederIds = feeders.map((f) => f.feeder_id);
  const chartData = buildChartData(feeders, yearlyProjections);

  const xInterval = horizonYears > 15 ? Math.ceil(horizonYears / 6) - 1 : 0;

  return (
    <div className="grid-card">
      <div className="grid-card__header">Constraint Timeline</div>
      <div className="grid-card__body">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E0E0E0" />
            <XAxis dataKey="year" tick={{ fontSize: 11 }} interval={xInterval} />
            <YAxis domain={[0, "auto"]} tick={{ fontSize: 11 }} unit="%" width={50} />
            <Tooltip
              contentStyle={{
                fontFamily: "Inter, sans-serif",
                fontSize: 12,
                border: "1px solid #E0E0E0",
                borderRadius: 4,
              }}
              formatter={(value: number, name: string) => [`${value.toFixed(1)}%`, name]}
              labelFormatter={(label: number) => `Year ${label}`}
            />
            <ReferenceLine
              y={80}
              stroke="#F0AB00"
              strokeDasharray="6 3"
              label={{ value: "80%", position: "right", fontSize: 10, fill: "#F0AB00" }}
            />
            <ReferenceLine
              y={100}
              stroke="#EE0000"
              strokeDasharray="6 3"
              label={{ value: "100%", position: "right", fontSize: 10, fill: "#EE0000" }}
            />
            {feederIds.map((id) => (
              <Line
                key={id}
                type="monotone"
                dataKey={id}
                stroke={FEEDER_COLORS[id] || "#6A6E73"}
                strokeWidth={2}
                dot={{ r: 2 }}
                activeDot={{ r: 4 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
        <div style={{ display: "flex", gap: 16, justifyContent: "center", marginTop: 4 }}>
          {feederIds.map((id) => {
            const feeder = feeders.find((f) => f.feeder_id === id);
            return (
              <div key={id} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11 }}>
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: FEEDER_COLORS[id] || "#6A6E73",
                    display: "inline-block",
                  }}
                />
                <span className="grid-mono">{id}</span>
                {feeder && <span style={{ color: "#6A6E73" }}>({feeder.feeder_name})</span>}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
