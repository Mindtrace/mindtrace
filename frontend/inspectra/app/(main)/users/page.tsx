"use client";

import dynamic from "next/dynamic";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

const UsersPanel = dynamic(
  () => import("@/components/users/users-panel").then((m) => m.UsersPanel),
  { ssr: false, loading: () => <LoadingOverlay /> }
);

export default function UsersPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Users</h1>
      <UsersPanel />
    </div>
  );
}
