"use client";

import dynamic from "next/dynamic";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

const CamerasPanel = dynamic(
  () =>
    import("@/components/cameras/cameras-panel").then((m) => m.CamerasPanel),
  { ssr: false, loading: () => <LoadingOverlay /> }
);

export default function CamerasPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Cameras</h1>
      <CamerasPanel />
    </div>
  );
}
