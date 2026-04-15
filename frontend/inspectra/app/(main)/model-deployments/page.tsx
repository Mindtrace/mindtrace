"use client";

import dynamic from "next/dynamic";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

const ModelDeploymentsPanel = dynamic(
  () =>
    import("@/components/model-deployments/model-deployments-panel").then(
      (m) => m.ModelDeploymentsPanel
    ),
  { ssr: false, loading: () => <LoadingOverlay /> }
);

export default function ModelDeploymentsPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Model deployments</h1>
      <ModelDeploymentsPanel />
    </div>
  );
}
