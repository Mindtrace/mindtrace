"use client";

import dynamic from "next/dynamic";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

const StageGraphsPanel = dynamic(
  () =>
    import("@/components/stage-graphs/stage-graphs-panel").then(
      (m) => m.StageGraphsPanel
    ),
  { ssr: false, loading: () => <LoadingOverlay /> }
);

export default function StageGraphsPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Stage graphs</h1>
      <StageGraphsPanel />
    </div>
  );
}
