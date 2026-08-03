// This project was developed with assistance from AI tools.

import { useCallback, useRef, useState } from "react";
import { Masthead } from "./components/Masthead";
import { ScenarioControls } from "./components/ScenarioControls";
import { CustomerImpactBanner } from "./components/CustomerImpactBanner";
import { OperationsView } from "./views/OperationsView";
import { GrowthView } from "./views/GrowthView";
import { PlatformView } from "./views/PlatformView";
import { WhatsNextView } from "./views/WhatsNextView";
import { useEventStream } from "./hooks/useEventStream";
import "@patternfly/react-core/dist/styles/base.css";
import "./styles/grid-ops.css";

type ViewId = "operations" | "growth" | "platform" | "whatsnext";

export default function App() {
  const [activeView, setActiveView] = useState<ViewId>("operations");
  const [beat, setBeat] = useState("idle");
  const [overlayDismissed, setOverlayDismissed] = useState(false);
  const prevBeat = useRef("idle");
  const stream = useEventStream();

  const handleBeatChange = useCallback((newBeat: string) => {
    if (newBeat !== prevBeat.current) {
      setOverlayDismissed(false);
    }
    prevBeat.current = newBeat;
    setBeat(newBeat);
  }, []);

  const dismissOverlay = useCallback(() => setOverlayDismissed(true), []);

  const handleReset = useCallback(() => {
    stream.reset();
    setBeat("idle");
    prevBeat.current = "idle";
    setOverlayDismissed(false);
  }, [stream]);

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <Masthead activeView={activeView} onViewChange={(v) => setActiveView(v as ViewId)} connected={stream.connected} />
      <CustomerImpactBanner impact={stream.customerImpact} />
      <div style={{ flex: 1, overflow: "hidden" }}>
        {activeView === "operations" && (
          <OperationsView
            stream={stream}
            beat={beat}
            overlayDismissed={overlayDismissed}
            onDismissOverlay={dismissOverlay}
          />
        )}
        {activeView === "growth" && <GrowthView />}
        {activeView === "platform" && <PlatformView />}
        {activeView === "whatsnext" && <WhatsNextView />}
      </div>
      <ScenarioControls onReset={handleReset} onBeatChange={handleBeatChange} />
    </div>
  );
}
