"use client";

import { Spinner } from "@/components/ui/spinner";

/**
 * Full-screen overlay with a centered spinner. Use while a page or route is loading.
 * No text, spinner only (shadcn-style). Background is somewhat transparent.
 */
export function LoadingOverlay() {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/50 backdrop-blur-[2px]"
      aria-busy="true"
      aria-label="Loading"
    >
      <Spinner className="size-8 text-muted-foreground" />
    </div>
  );
}
