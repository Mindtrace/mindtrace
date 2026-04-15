"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  listCameraServices,
  updateCameraService,
  getSafeErrorMessage,
  isSessionOrAuthError,
} from "@/lib/api/client";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CameraService } from "@/lib/api/types";
import { LoadingOverlay } from "@/components/ui/loading-overlay";
import { CameraServicesTable } from "./camera-services-table";
import { CameraServicesPagination } from "./camera-services-pagination";
import {
  HealthStatusDropdown,
  type HealthStatusValue,
} from "@/components/health-status/health-status-dropdown";

const PAGE_SIZE = 10;
const HEALTH_STATUSES = [
  "unknown",
  "healthy",
  "unhealthy",
  "degraded",
] as const;

export function CameraServicesPanel() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<CameraService | null>(null);
  const [editHealthStatus, setEditHealthStatus] = useState<HealthStatusValue | "">(
    ""
  );
  const [editServiceUrl, setEditServiceUrl] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["camera-services", page],
    queryFn: () =>
      listCameraServices({ skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE }),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      health_status,
      cam_service_url,
    }: {
      id: string;
      health_status?: string;
      cam_service_url?: string;
    }) => updateCameraService(id, { health_status, cam_service_url }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["camera-services"] });
      toast.success("Camera service updated successfully.");
      setEditing(null);
    },
    onError: (err: Error) => {
      if (!isSessionOrAuthError(err))
        toast.error(
          getSafeErrorMessage(err, "Failed to update camera service.")
        );
    },
  });

  function startEdit(c: CameraService) {
    setEditing(c);
    setEditHealthStatus(c.health_status as HealthStatusValue);
    setEditServiceUrl(c.cam_service_url);
  }

  if (isLoading) return <LoadingOverlay />;
  if (error) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-destructive">
            {getSafeErrorMessage(error, "Something went wrong.")}
          </p>
        </CardContent>
      </Card>
    );
  }

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <Dialog
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit camera service</DialogTitle>
            <DialogDescription>
              Update health status or service URL.
            </DialogDescription>
          </DialogHeader>
          {editing && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                updateMutation.mutate({
                  id: editing.id,
                  health_status: editHealthStatus || undefined,
                  cam_service_url: editServiceUrl.trim() || undefined,
                });
              }}
              className="space-y-4"
            >
              {updateMutation.isError &&
                !isSessionOrAuthError(updateMutation.error) && (
                  <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {getSafeErrorMessage(
                      updateMutation.error,
                      "Failed to update."
                    )}
                  </p>
                )}
              <div className="space-y-2">
                <Label htmlFor="edit-health-status">Health status</Label>
                <HealthStatusDropdown
                  id="edit-health-status"
                  value={editHealthStatus}
                  onValueChange={setEditHealthStatus}
                  disabled={updateMutation.isPending}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-camera-service-url">
                  Camera service URL
                </Label>
                <Input
                  id="edit-camera-service-url"
                  value={editServiceUrl}
                  onChange={(e) => setEditServiceUrl(e.target.value)}
                  placeholder="http://..."
                  disabled={updateMutation.isPending}
                />
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditing(null)}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={updateMutation.isPending}>
                  {updateMutation.isPending ? "Saving…" : "Save"}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Card>
        <CardContent className="pt-6">
          {items.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">
              No camera services yet.
            </p>
          ) : (
            <>
              <CameraServicesTable items={items} onEdit={startEdit} />
              <CameraServicesPagination
                page={page}
                totalPages={totalPages}
                total={total}
                pageSize={PAGE_SIZE}
                onPageChange={setPage}
              />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
