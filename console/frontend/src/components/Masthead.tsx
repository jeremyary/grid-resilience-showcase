// This project was developed with assistance from AI tools.

interface MastheadProps {
  activeView: string;
  onViewChange: (view: string) => void;
  connected: boolean;
}

const VIEWS = [
  { id: "operations", label: "Map" },
  { id: "growth", label: "Growth" },
  { id: "whatsnext", label: "At Scale" },
  { id: "platform", label: "Platform" },
];

export function Masthead({ activeView, onViewChange, connected }: MastheadProps) {
  return (
    <div className="grid-masthead">
      <span className="grid-masthead__title">Grid Resilience Ops Center</span>
      <div className="grid-view-toggle">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            className={`grid-view-toggle__pill ${activeView === v.id ? "grid-view-toggle__pill--active" : ""}`}
            onClick={() => onViewChange(v.id)}
          >
            {v.label}
          </button>
        ))}
      </div>
      <span style={{ fontSize: 12, color: connected ? "#3E8635" : "#A30000" }}>
        {connected ? "● Connected" : "● Disconnected"}
      </span>
    </div>
  );
}
