"use client";

import dynamic from "next/dynamic";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

const OrganizationsPanel = dynamic(
  () =>
    import("@/components/organizations/organizations-panel").then(
      (m) => m.OrganizationsPanel
    ),
  { ssr: false, loading: () => <LoadingOverlay /> }
);

export default function OrganizationsPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Organizations</h1>
      <OrganizationsPanel />
    </div>
  );
}
