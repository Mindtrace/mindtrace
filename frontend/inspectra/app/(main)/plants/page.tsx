"use client";

import dynamic from "next/dynamic";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

const PlantsPanel = dynamic(
  () => import("@/components/plants/plants-panel").then((m) => m.PlantsPanel),
  { ssr: false, loading: () => <LoadingOverlay /> }
);

export default function PlantsPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Plants</h1>
      <PlantsPanel />
    </div>
  );
}
