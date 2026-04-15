"use client";

import dynamic from "next/dynamic";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

const CameraSetsPanel = dynamic(
  () =>
    import("@/components/camera-sets/camera-sets-panel").then(
      (m) => m.CameraSetsPanel
    ),
  { ssr: false, loading: () => <LoadingOverlay /> }
);

export default function CameraSetsPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Camera sets</h1>
      <CameraSetsPanel />
    </div>
  );
}
