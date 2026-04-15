"use client";

import dynamic from "next/dynamic";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

const LinesPanel = dynamic(
  () => import("@/components/lines/lines-panel").then((m) => m.LinesPanel),
  { ssr: false, loading: () => <LoadingOverlay /> }
);

export default function LinesPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Lines</h1>
      <LinesPanel />
    </div>
  );
}
