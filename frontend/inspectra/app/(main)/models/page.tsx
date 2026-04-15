"use client";

import dynamic from "next/dynamic";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

const ModelsPanel = dynamic(
  () => import("@/components/models/models-panel").then((m) => m.ModelsPanel),
  { ssr: false, loading: () => <LoadingOverlay /> }
);

export default function ModelsPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Models</h1>
      <ModelsPanel />
    </div>
  );
}
