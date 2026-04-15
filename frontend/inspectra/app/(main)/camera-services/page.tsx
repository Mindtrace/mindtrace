"use client";

import dynamic from "next/dynamic";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

const CameraServicesPanel = dynamic(
  () =>
    import("@/components/camera-services/camera-services-panel").then(
      (m) => m.CameraServicesPanel
    ),
  { ssr: false, loading: () => <LoadingOverlay /> }
);

export default function CameraServicesPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Camera services</h1>
      <CameraServicesPanel />
    </div>
  );
}
