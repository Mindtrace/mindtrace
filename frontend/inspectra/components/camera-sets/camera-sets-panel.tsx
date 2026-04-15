"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  createCameraSet,
  deleteCameraSet,
  getSafeErrorMessage,
  listCameraServices,
  listCameraSets,
  updateCameraSet,
} from "@/lib/api/client";
import type { CameraService, CameraSet } from "@/lib/api/types";
import { cameraServiceFetchResponse } from "@/lib/camera-service-forward";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ChevronDown } from "lucide-react";
import { LoadingOverlay } from "@/components/ui/loading-overlay";
import { useSearchParams } from "next/navigation";
import { CameraSetDialog } from "@/components/camera-sets/camera-set-dialog";

const PAGE_SIZE = 10;

type CamerasResponse = {
  success: boolean;
  message?: string;
  data?: string[];
};

export function CameraSetsPanel() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const initialServiceId = searchParams.get("camera_service_id") ?? "";

  const [selectedServiceId, setSelectedServiceId] = useState(initialServiceId);
  const [page, setPage] = useState(1);

  const [editing, setEditing] = useState<CameraSet | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const dialogOpen = showCreate || editing !== null;

  const [draftServiceId, setDraftServiceId] = useState("");
  const [draftName, setDraftName] = useState("");
  const [draftBatchSize, setDraftBatchSize] = useState("1");
  const [draftSelected, setDraftSelected] = useState<Set<string>>(new Set());
  const [availableCameras, setAvailableCameras] = useState<string[]>([]);
  const [loadingCameras, setLoadingCameras] = useState(false);
  const [cameraLoadError, setCameraLoadError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  const {
    data: servicesData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["camera-services", "all"],
    queryFn: () => listCameraServices({ limit: 500 }),
  });

  const services = useMemo(() => servicesData?.items ?? [], [servicesData]);
  const serviceById = useMemo(() => {
    return new Map(services.map((s) => [s.id, s] as const));
  }, [services]);

  const {
    data: setsData,
    isLoading: isLoadingSets,
    error: setsError,
  } = useQuery({
    queryKey: ["camera-sets", selectedServiceId, page],
    queryFn: () =>
      listCameraSets({
        camera_service_id: selectedServiceId || undefined,
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      }),
  });

  const pageItems = setsData?.items ?? [];
  const total = setsData?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const end = Math.min(page * PAGE_SIZE, total);

  useEffect(() => setPage(1), [selectedServiceId]);

  const { data: allSetsInService } = useQuery({
    queryKey: ["camera-sets-all", editing?.camera_service_id ?? draftServiceId],
    queryFn: () =>
      listCameraSets({
        camera_service_id:
          (editing?.camera_service_id ?? draftServiceId) || undefined,
        limit: 500,
      }),
    enabled:
      dialogOpen && (editing?.camera_service_id ?? draftServiceId) !== "",
  });

  const cameraToSetId = useMemo(() => {
    const used = new Map<string, string>();
    const svcId = editing?.camera_service_id ?? draftServiceId;
    for (const s of allSetsInService?.items ?? []) {
      if (svcId && s.camera_service_id !== svcId) continue;
      for (const cam of s.cameras) used.set(cam, s.id);
    }
    return used;
  }, [allSetsInService?.items, editing?.camera_service_id, draftServiceId]);

  const editingId = editing?.id ?? null;

  const disabledCameraReason = useMemo(() => {
    const m = new Map<string, string>();
    const activeServiceId = editing?.camera_service_id ?? draftServiceId;
    if (!activeServiceId) return m;
    for (const cam of availableCameras) {
      const usedBy = cameraToSetId.get(cam);
      if (usedBy && usedBy !== editingId) {
        const usedSet = (allSetsInService?.items ?? []).find(
          (s) => s.id === usedBy
        );
        if (usedSet?.camera_service_id === activeServiceId) {
          m.set(cam, usedSet ? `Assigned to "${usedSet.name}"` : "Assigned");
        }
      }
    }
    return m;
  }, [
    availableCameras,
    cameraToSetId,
    draftServiceId,
    editing?.camera_service_id,
    editingId,
    allSetsInService?.items,
  ]);

  function closeDialog() {
    setShowCreate(false);
    setEditing(null);
    setDraftServiceId("");
    setDraftName("");
    setDraftBatchSize("1");
    setDraftSelected(new Set());
    setAvailableCameras([]);
    setCameraLoadError(null);
    setReloadTick(0);
  }

  function startCreate() {
    setEditing(null);
    setShowCreate(true);
    setDraftServiceId(selectedServiceId || services[0]?.id || "");
    setDraftName("");
    setDraftBatchSize("1");
    setDraftSelected(new Set());
    setAvailableCameras([]);
    setCameraLoadError(null);
    setReloadTick((x) => x + 1);
  }

  function startEdit(set: CameraSet) {
    setShowCreate(false);
    setEditing(set);
    setDraftServiceId(set.camera_service_id);
    setDraftName(set.name);
    setDraftBatchSize(String(Math.max(1, set.batch_size ?? 1)));
    setDraftSelected(new Set(set.cameras));
    setAvailableCameras([]);
    setCameraLoadError(null);
    setReloadTick((x) => x + 1);
  }

  function deleteSet(id: string) {
    deleteMutation.mutate(id);
  }

  function toggleCamera(name: string) {
    setDraftSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  async function loadCamerasForService(service: CameraService) {
    setLoadingCameras(true);
    setCameraLoadError(null);
    try {
      const res = await cameraServiceFetchResponse(
        service.cam_service_url,
        "/get_cameras",
        { method: "GET" }
      );
      if (!res.ok)
        throw new Error(`Camera service returned HTTP ${res.status}`);
      const json = (await res.json()) as CamerasResponse;
      if (!json?.success)
        throw new Error(json?.message || "Failed to retrieve cameras.");
      const cams = Array.isArray(json?.data)
        ? json.data.filter((c) => typeof c === "string")
        : [];
      setAvailableCameras(cams);
    } catch (e) {
      setAvailableCameras([]);
      setCameraLoadError(
        getSafeErrorMessage(e, "Failed to load available cameras.")
      );
    } finally {
      setLoadingCameras(false);
    }
  }

  useEffect(() => {
    if (!dialogOpen) return;
    const svcId = editing?.camera_service_id ?? draftServiceId;
    if (!svcId) return;
    const svc = serviceById.get(svcId);
    if (!svc) return;
    loadCamerasForService(svc);
  }, [
    dialogOpen,
    editing?.camera_service_id,
    draftServiceId,
    reloadTick,
    serviceById,
  ]);

  function saveDraft() {
    const name = draftName.trim();
    const serviceId = draftServiceId;
    if (!serviceId) {
      toast.error("Select a camera service.");
      return;
    }
    if (!name) {
      toast.error("Camera set name is required.");
      return;
    }

    const batchSize = parseInt(draftBatchSize.trim(), 10);
    if (!Number.isFinite(batchSize) || batchSize < 1) {
      toast.error("Batch size must be a whole number ≥ 1.");
      return;
    }

    const selected = Array.from(draftSelected);
    const conflict = selected.find((cam) => {
      const usedBy = cameraToSetId.get(cam);
      return usedBy != null && usedBy !== (editing?.id ?? "");
    });
    if (conflict) {
      toast.error(`"${conflict}" is already assigned to another camera set.`);
      return;
    }

    if (editing) {
      updateMutation.mutate({
        id: editing.id,
        payload: { name, cameras: selected, batch_size: batchSize },
      });
    } else {
      createMutation.mutate({
        camera_service_id: serviceId,
        name,
        cameras: selected,
        batch_size: batchSize,
      });
    }
  }

  const createMutation = useMutation({
    mutationFn: (payload: {
      camera_service_id: string;
      name: string;
      cameras: string[];
      batch_size: number;
    }) => createCameraSet(payload),
    onSuccess: () => {
      toast.success("Camera set created.");
      queryClient.invalidateQueries({ queryKey: ["camera-sets"] });
      queryClient.invalidateQueries({ queryKey: ["camera-sets-all"] });
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      closeDialog();
    },
    onError: (err: Error) => {
      toast.error(getSafeErrorMessage(err, "Failed to create camera set."));
    },
  });

  const updateMutation = useMutation({
    mutationFn: (args: {
      id: string;
      payload: { name?: string; cameras?: string[]; batch_size?: number };
    }) => updateCameraSet(args.id, args.payload),
    onSuccess: () => {
      toast.success("Camera set updated.");
      queryClient.invalidateQueries({ queryKey: ["camera-sets"] });
      queryClient.invalidateQueries({ queryKey: ["camera-sets-all"] });
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      closeDialog();
    },
    onError: (err: Error) => {
      toast.error(getSafeErrorMessage(err, "Failed to update camera set."));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteCameraSet(id),
    onSuccess: () => {
      toast.success("Camera set deleted.");
      queryClient.invalidateQueries({ queryKey: ["camera-sets"] });
      queryClient.invalidateQueries({ queryKey: ["camera-sets-all"] });
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: (err: Error) => {
      toast.error(getSafeErrorMessage(err, "Failed to delete camera set."));
    },
  });

  if (isLoading || isLoadingSets) return <LoadingOverlay />;
  if (error || setsError) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-destructive">
            {getSafeErrorMessage(error ?? setsError, "Something went wrong.")}
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <CameraSetDialog
        open={dialogOpen}
        onOpenChange={(open) => !open && closeDialog()}
        editing={editing}
        services={services}
        serviceById={serviceById}
        draftServiceId={draftServiceId}
        setDraftServiceId={(id) => {
          setDraftServiceId(id);
          setDraftSelected(new Set());
          setReloadTick((x) => x + 1);
        }}
        draftName={draftName}
        setDraftName={setDraftName}
        draftBatchSize={draftBatchSize}
        setDraftBatchSize={setDraftBatchSize}
        draftSelected={draftSelected}
        toggleCamera={toggleCamera}
        loadingCameras={loadingCameras}
        cameraLoadError={cameraLoadError}
        availableCameras={availableCameras}
        disabledCameraReason={disabledCameraReason}
        onReloadCameras={() => setReloadTick((x) => x + 1)}
        onCancel={closeDialog}
        onSubmit={saveDraft}
      />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4 py-4">
          <div className="flex items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="justify-between">
                  {selectedServiceId
                    ? (serviceById.get(selectedServiceId)?.line_name ??
                      serviceById.get(selectedServiceId)?.line_id ??
                      "Camera service")
                    : "All camera services"}
                  <ChevronDown className="ml-2 h-4 w-4 opacity-50" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuItem onClick={() => setSelectedServiceId("")}>
                  All camera services
                </DropdownMenuItem>
                {services.map((svc) => (
                  <DropdownMenuItem
                    key={svc.id}
                    onClick={() => setSelectedServiceId(svc.id)}
                  >
                    {svc.line_name ?? svc.line_id}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <Button onClick={startCreate}>Create camera set</Button>
        </CardHeader>

        <CardContent>
          {pageItems.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">
              No camera sets yet.
            </p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="font-medium">Name</TableHead>
                    <TableHead>Camera service</TableHead>
                    <TableHead className="text-right tabular-nums">
                      Batch size
                    </TableHead>
                    <TableHead className="text-right tabular-nums">
                      Cameras
                    </TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pageItems.map((s) => {
                    const svc = serviceById.get(s.camera_service_id);
                    return (
                      <TableRow key={s.id}>
                        <TableCell className="font-medium">{s.name}</TableCell>
                        <TableCell>
                          {svc
                            ? (svc.line_name ?? svc.line_id)
                            : s.camera_service_id}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {s.batch_size ?? 1}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {s.cameras.length}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-2">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => startEdit(s)}
                            >
                              Edit
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => deleteSet(s.id)}
                            >
                              Delete
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}

          {total > 0 ? (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-4">
              <p className="text-sm text-muted-foreground">
                Showing {start}–{end} of {total}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(Math.max(1, page - 1))}
                  disabled={page <= 1}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(Math.min(totalPages, page + 1))}
                  disabled={page >= totalPages}
                >
                  Next
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
