// This project was developed with assistance from AI tools.

import { useCallback, useEffect, useMemo, useState } from "react";
import { GridMap } from "../components/GridMap";
import { MapLegend } from "../components/MapLegend";
import { ForecastPipeline } from "../components/ForecastPipeline";
import { TriageOverlay } from "../components/TriageOverlay";
import { DispatchOverlay } from "../components/DispatchOverlay";
import { StormOverlay } from "../components/StormOverlay";
import { SubstationPanel } from "../components/SubstationPanel";
import { RiskTable } from "../components/RiskTable";
import { FindingsPanel } from "../components/FindingsPanel";
import { EventStream } from "../components/EventStream";
import type { TopologyData } from "../types/events";
import type { useEventStream } from "../hooks/useEventStream";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

interface OperationsViewProps {
  stream: ReturnType<typeof useEventStream>;
  beat: string;
  overlayDismissed: boolean;
  onDismissOverlay: () => void;
}

const KIT_SIGNALING_URL_DEFAULT = "kit-substation-grid-ops-ai.apps.g4h4d3j7q1c9f7m.cimo.p1.openshiftapps.com";

const EMPTY_TOPOLOGY: TopologyData = { feeders: [], assets: [], segments: [], cameras: [] };

export function OperationsView({ stream, beat, overlayDismissed, onDismissOverlay }: OperationsViewProps) {
  const [topology, setTopology] = useState<TopologyData>(EMPTY_TOPOLOGY);
  const [topologyError, setTopologyError] = useState(false);
  const [kitUrl, setKitUrl] = useState(KIT_SIGNALING_URL_DEFAULT);

  const fetchTopology = useCallback(async (signal?: AbortSignal) => {
    setTopologyError(false);
    try {
      const resp = await fetch(`${API_BASE}/api/topology`, { signal });
      if (resp.ok) {
        setTopology(await resp.json());
      } else {
        setTopologyError(true);
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setTopologyError(true);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchTopology(ctrl.signal);
    (async () => {
      try {
        const cfg = await fetch("/config.json", { signal: ctrl.signal });
        if (cfg.ok) {
          const data = await cfg.json();
          if (data.kitSignalingServer) setKitUrl(data.kitSignalingServer);
        }
      } catch {
        /* config not available — use default */
      }
    })();
    return () => ctrl.abort();
  }, [fetchTopology]);

  const scenarioActive = stream.events.length > 0;
  const forecastPublished = useMemo(
    () => stream.events.some((e) => e.title?.toLowerCase().includes("corrdiff")),
    [stream.events],
  );

  const showForecast = beat === "forecast" && !overlayDismissed;
  const showTriage = beat === "triage" && !overlayDismissed;
  const showDispatch = beat === "dispatch" && !overlayDismissed;
  const showStorm = beat === "trace" && !overlayDismissed;

  return (
    <div className="grid-layout">
      <div className="grid-layout__left" style={{ position: "relative" }}>
        <MapLegend />
        <ForecastPipeline
          active={showForecast}
          forecastPublished={forecastPublished}
          riskCount={stream.riskScores.size}
          onClose={onDismissOverlay}
        />
        <TriageOverlay
          active={showTriage}
          riskScores={stream.riskScores}
          onClose={onDismissOverlay}
        />
        <DispatchOverlay
          active={showDispatch}
          dispatches={stream.dispatches}
          onClose={onDismissOverlay}
        />
        <StormOverlay
          active={showStorm}
          impact={stream.customerImpact}
          onClose={onDismissOverlay}
        />
        {topologyError && (
          <div style={{ position: "absolute", top: 12, left: 12, right: 12, zIndex: 800 }}>
            <div className="grid-card" style={{ margin: 0 }}>
              <div className="grid-card__body" style={{ color: "#A30000", fontSize: 13, display: "flex", alignItems: "center", gap: 8 }}>
                <span>Failed to load grid topology</span>
                <button onClick={() => fetchTopology()} style={{ color: "#A30000", textDecoration: "underline", background: "none", border: "none", cursor: "pointer", fontSize: 13, padding: 0 }}>Retry</button>
              </div>
            </div>
          </div>
        )}
        <GridMap
          assets={topology.assets}
          segments={topology.segments}
          cameras={topology.cameras}
          riskScores={stream.riskScores}
          faults={stream.faults}
          dispatches={stream.dispatches}
          scenarioActive={scenarioActive}
        />
      </div>
      <div className="grid-layout__right">
        <SubstationPanel signalingServer={kitUrl} />
        <RiskTable riskScores={stream.riskScores} />
        <FindingsPanel findings={stream.findings} />
        <EventStream events={stream.events} />
      </div>
    </div>
  );
}
