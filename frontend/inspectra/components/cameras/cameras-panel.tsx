"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  createRoi,
  deleteRoi,
  getCamera,
  listCameras,
  listCameraSets,
  listCameraServices,
  listModelDeployments,
  listRois,
  listStages,
  getSafeErrorMessage,
  upsertCameraPosition,
  updateCameraConfig,
} from "@/lib/api/client";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { OutlineDropdownSelect } from "@/components/cameras/outline-dropdown-select";
import { RoiNameDialog } from "@/components/cameras/roi-name-dialog";
import { CameraFeed } from "@/components/cameras/camera-feed";
import { LoadingOverlay } from "@/components/ui/loading-overlay";
import { Label } from "@/components/ui/label";
import type {
  Camera,
  CameraService,
  CameraSet,
  ModelDeployment,
  Roi,
  Stage,
} from "@/lib/api/types";
import {
  cameraServiceFetchResponse,
  normalizeCameraServiceUrl,
} from "@/lib/camera-service-forward";
import { closePolygon, metricsFromPoints, newDraftRoiClientId, type RoiTool } from "@/components/cameras/roi-drawing";

const PAGE_SIZE = 10;

// ROI drawing helpers live in `components/cameras/roi-drawing.ts`

/** White balance modes accepted by the camera service `set_wb_once` API. */
export const WB_VALS = ["off", "once"] as const;
type WbVal = (typeof WB_VALS)[number];

type CamerasInitResponse = {
  success: boolean;
  message?: string;
  data?: string[];
};
type CamerasDeinitResponse = { success: boolean; message?: string };

type CameraServiceJsonResponse<T = unknown> = {
  success: boolean;
  message?: string;
  data?: T;
};

function parseWbFromDevice(raw: string): WbVal {
  const v = raw.trim().toLowerCase();
  return v === "once" ? "once" : "off";
}

function parseExposureRangeStrings(data: unknown): {
  min: number;
  max: number;
} {
  if (!Array.isArray(data) || data.length === 0)
    return { min: 0, max: 100_000 };
  const nums = data
    .map((x) => Number(String(x)))
    .filter((n) => !Number.isNaN(n));
  if (nums.length === 0) return { min: 0, max: 100_000 };
  return { min: Math.min(...nums), max: Math.max(...nums) };
}

async function cameraServicePost<T = unknown>(
  serviceUrl: string,
  path: string,
  body: Record<string, unknown>,
  query?: Record<string, string>
): Promise<CameraServiceJsonResponse<T>> {
  const res = await cameraServiceFetchResponse(serviceUrl, path, {
    query,
    jsonBody: body,
  });
  if (!res.ok)
    throw new Error(`Camera service request failed (HTTP ${res.status})`);
  return (await res.json()) as CameraServiceJsonResponse<T>;
}

async function deinitCameras(serviceUrl: string, cameras: string[]) {
  const res = await cameraServiceFetchResponse(serviceUrl, "/de_init_cameras", {
    jsonBody: { cameras },
  });
  if (!res.ok) throw new Error(`De-init failed (HTTP ${res.status})`);
  const json = (await res.json()) as CamerasDeinitResponse;
  if (!json?.success) throw new Error(json?.message || "De-init failed.");
  return json;
}

async function initCameras(serviceUrl: string, cameras: string[]) {
  const res = await cameraServiceFetchResponse(
    serviceUrl,
    "/initialize_cameras",
    {
      jsonBody: {
        cameras,
        camera_configs: [],
        triggermode: "trigger",
        max_retries: 1,
        stage_set_configs: {},
      },
    }
  );
  if (!res.ok) throw new Error(`Init failed (HTTP ${res.status})`);
  const json = (await res.json()) as CamerasInitResponse;
  if (!json?.success) throw new Error(json?.message || "Init failed.");
  return json;
}

export function CamerasPanel() {
  const queryClient = useQueryClient();

  const [selectedServiceId, setSelectedServiceId] = useState("");
  const [selectedCameraSetId, setSelectedCameraSetId] = useState("");
  const [page, setPage] = useState(1);
  const [feedCamera, setFeedCamera] = useState<Camera | null>(null);
  const [feedInitError, setFeedInitError] = useState<string | null>(null);
  const [hardwareLoadError, setHardwareLoadError] = useState<string | null>(
    null
  );
  const [feedStreamLoaded, setFeedStreamLoaded] = useState(false);
  const [hardwareReady, setHardwareReady] = useState(false);
  const [feedExposure, setFeedExposure] = useState(0);
  const [feedWb, setFeedWb] = useState<WbVal>("off");
  const [feedExpMin, setFeedExpMin] = useState(0);
  const [feedExpMax, setFeedExpMax] = useState(100_000);
  const [persistBusy, setPersistBusy] = useState(false);
  const [cameraPosition, setCameraPosition] = useState(0);
  const [roiStageId, setRoiStageId] = useState("");
  const [roiModelDeploymentId, setRoiModelDeploymentId] = useState("");
  const [roiTool, setRoiTool] = useState<RoiTool>("box");
  const [roiDrafts, setRoiDrafts] = useState<
    Array<{ id: string; name: string; type: "box" | "polygon"; points: number[][] }>
  >([]);
  const [streamLayout, setStreamLayout] = useState({ w: 0, h: 0 });
  /** Saved ROI ids to delete on next Save (not removed from DB until then). */
  const [persistedRoiIdsPendingDelete, setPersistedRoiIdsPendingDelete] =
    useState<string[]>([]);
  const [roiNameDialogOpen, setRoiNameDialogOpen] = useState(false);
  const [pendingRoiPoints, setPendingRoiPoints] = useState<number[][] | null>(
    null
  );
  const [pendingRoiType, setPendingRoiType] = useState<"box" | "polygon">("box");
  const [pendingRoiName, setPendingRoiName] = useState("");
  const [polygonDraftPoints, setPolygonDraftPoints] = useState<number[][]>([]);
  const [polygonHover, setPolygonHover] = useState<{ x: number; y: number } | null>(
    null
  );
  const [activeDrag, setActiveDrag] = useState<{
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  } | null>(null);
  const persistedRoisRef = useRef<Roi[]>([]);
  const exposureDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(
    null
  );

  const { data: servicesData } = useQuery({
    queryKey: ["camera-services", "all"],
    queryFn: () => listCameraServices({ limit: 500 }),
  });
  const services = useMemo(() => servicesData?.items ?? [], [servicesData]);
  const serviceById = useMemo(() => {
    return new Map(services.map((s) => [s.id, s] as const));
  }, [services]);

  const { data: cameraSetsData } = useQuery({
    queryKey: ["camera-sets", "all"],
    queryFn: () => listCameraSets({ limit: 500 }),
  });
  const cameraSets = useMemo(
    () => cameraSetsData?.items ?? [],
    [cameraSetsData]
  );
  const cameraSetById = useMemo(() => {
    return new Map(cameraSets.map((s) => [s.id, s] as const));
  }, [cameraSets]);
  const cameraSetsForSelectedService = useMemo(() => {
    if (!selectedServiceId) return cameraSets;
    return cameraSets.filter((s) => s.camera_service_id === selectedServiceId);
  }, [cameraSets, selectedServiceId]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["cameras", selectedServiceId, selectedCameraSetId, page],
    queryFn: () =>
      listCameras({
        camera_service_id: selectedServiceId || undefined,
        camera_set_id: selectedCameraSetId || undefined,
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      }),
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const end = Math.min(page * PAGE_SIZE, total);

  const reinitMutation = useMutation({
    mutationFn: async (camera: Camera) => {
      const serviceUrl = camera.camera_service_url;
      if (!serviceUrl) throw new Error("Camera service URL is missing.");
      await deinitCameras(serviceUrl, [camera.name]);
      return await initCameras(serviceUrl, [camera.name]);
    },
    onSuccess: () => {
      toast.success("Camera re-initialized successfully.");
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: (err: Error) => {
      toast.error(getSafeErrorMessage(err, "Failed to re-initialize camera."));
    },
  });

  const feedInitMutation = useMutation({
    mutationFn: async (camera: Camera) => {
      const serviceUrl = camera.camera_service_url;
      if (!serviceUrl) throw new Error("Camera service URL is missing.");
      await initCameras(serviceUrl, [camera.name]);
      return true;
    },
    onError: (err: Error) => {
      setFeedInitError(
        getSafeErrorMessage(err, "Failed to initialize camera.")
      );
    },
  });

  async function loadHardwareFromService(cam: Camera) {
    const serviceUrl = cam.camera_service_url;
    if (!serviceUrl) throw new Error("Camera service URL is missing.");
    const name = cam.name;

    const exp = await cameraServicePost<number>(serviceUrl, "/get_exposure", {
      camera: name,
    });
    if (!exp.success || typeof exp.data !== "number") {
      throw new Error(exp.message || "Could not read exposure from camera.");
    }

    const wb = await cameraServicePost<string>(serviceUrl, "/get_wb", {
      camera: name,
    });
    if (!wb.success || wb.data === undefined) {
      throw new Error(
        wb.message || "Could not read white balance from camera."
      );
    }

    let min = 0;
    let max = 100_000;
    try {
      const range = await cameraServicePost<string[]>(
        serviceUrl,
        "/get_exposure_range",
        {},
        { camera: name }
      );
      if (range.success && range.data?.length) {
        const r = parseExposureRangeStrings(range.data);
        min = r.min;
        max = r.max;
      }
    } catch {
      /* fall back to defaults */
    }
    if (max <= min) max = min + 1;
    const clamped = Math.min(max, Math.max(min, exp.data));
    // DB + PATCH schema expect integer ms; camera service may return floats.
    setFeedExposure(Math.round(clamped));
    setFeedWb(parseWbFromDevice(String(wb.data)));
    setFeedExpMin(min);
    setFeedExpMax(max);
    setHardwareReady(true);
  }

  function scheduleSetExposure(cam: Camera, value: number) {
    if (exposureDebounceRef.current) {
      clearTimeout(exposureDebounceRef.current);
      exposureDebounceRef.current = null;
    }
    exposureDebounceRef.current = setTimeout(async () => {
      exposureDebounceRef.current = null;
      try {
        const serviceUrl = cam.camera_service_url;
        if (!serviceUrl) return;
        const res = await cameraServicePost(serviceUrl, "/set_exposure", {
          camera: cam.name,
          exposure: Math.round(value),
        });
        if (!res.success) {
          toast.error(res.message || "Failed to set exposure.");
        }
      } catch (e) {
        toast.error(
          getSafeErrorMessage(e as Error, "Failed to set exposure on camera.")
        );
      }
    }, 280);
  }

  async function applyWbOnService(cam: Camera, mode: WbVal) {
    const serviceUrl = cam.camera_service_url;
    if (!serviceUrl) throw new Error("Camera service URL is missing.");
    const res = await cameraServicePost(serviceUrl, "/set_wb_once", {
      camera: cam.name,
      mode,
    });
    if (!res.success) {
      throw new Error(res.message || "set_wb_once failed.");
    }
  }

  function resetFeedDialogState() {
    setFeedCamera(null);
    setFeedInitError(null);
    setHardwareLoadError(null);
    setHardwareReady(false);
    setFeedStreamLoaded(false);
    setStreamLayout({ w: 0, h: 0 });
    setPersistedRoiIdsPendingDelete([]);
    setCameraPosition(0);
    setRoiStageId("");
    setRoiModelDeploymentId("");
    setRoiTool("box");
    setRoiDrafts([]);
    setRoiNameDialogOpen(false);
    setPendingRoiPoints(null);
    setPendingRoiType("box");
    setPendingRoiName("");
    setPolygonDraftPoints([]);
    setPolygonHover(null);
    setActiveDrag(null);
    if (exposureDebounceRef.current) {
      clearTimeout(exposureDebounceRef.current);
      exposureDebounceRef.current = null;
    }
  }

  const feedUrl = useMemo(() => {
    if (!feedCamera?.camera_service_url || !feedCamera?.name) return null;
    try {
      const base = normalizeCameraServiceUrl(feedCamera.camera_service_url);
      const path = `/video_stream/${encodeURIComponent(feedCamera.name)}`;
      return new URL(path, base).toString();
    } catch {
      return null;
    }
  }, [feedCamera]);

  function stagePersistedRoiRemoval(roiId: string) {
    setPersistedRoiIdsPendingDelete((prev) =>
      prev.includes(roiId) ? prev : [...prev, roiId]
    );
  }

  const configRoisQueryEnabled =
    feedCamera !== null &&
    feedStreamLoaded &&
    !!roiStageId &&
    !!roiModelDeploymentId;

  const { data: configExistingRoisData } = useQuery({
    queryKey: [
      "rois",
      "camera-config-overlay",
      feedCamera?.id ?? "",
      cameraPosition,
      roiStageId,
      roiModelDeploymentId,
    ],
    queryFn: async () => {
      if (!feedCamera || !roiStageId || !roiModelDeploymentId) {
        return { items: [] as Roi[], total: 0 };
      }
      return listRois({
        camera_id: feedCamera.id,
        position: cameraPosition,
        stage_id: roiStageId,
        model_deployment_id: roiModelDeploymentId,
        limit: 500,
      });
    },
    enabled: configRoisQueryEnabled,
  });

  const existingRoisForOverlay = useMemo(
    () => configExistingRoisData?.items ?? [],
    [configExistingRoisData]
  );
  const pendingDeleteSet = useMemo(
    () => new Set(persistedRoiIdsPendingDelete),
    [persistedRoiIdsPendingDelete]
  );
  const visiblePersistedRoisForOverlay = useMemo(
    () => existingRoisForOverlay.filter((r) => !pendingDeleteSet.has(r.id)),
    [existingRoisForOverlay, pendingDeleteSet]
  );
  persistedRoisRef.current = visiblePersistedRoisForOverlay;

  // Canvas drawing now handled by `CameraFeed`.

  const { data: stagesData } = useQuery({
    queryKey: ["stages", "all"],
    queryFn: () => listStages({ limit: 500 }),
    enabled: feedCamera !== null,
  });
  const stages = useMemo<Stage[]>(() => stagesData?.items ?? [], [stagesData]);

  const { data: modelDeploymentsData } = useQuery({
    queryKey: ["model-deployments", feedCamera?.line_id ?? ""],
    queryFn: () =>
      feedCamera?.line_id
        ? listModelDeployments({ line_id: feedCamera.line_id, limit: 500 })
        : Promise.resolve({ items: [], total: 0 }),
    enabled: !!feedCamera?.line_id,
  });
  const modelDeployments = useMemo<ModelDeployment[]>(
    () => modelDeploymentsData?.items ?? [],
    [modelDeploymentsData]
  );

  useEffect(() => {
    if (!feedCamera) return;
    if (roiModelDeploymentId) return;
    if (modelDeployments.length === 1) {
      setRoiModelDeploymentId(modelDeployments[0].id);
    }
  }, [feedCamera, modelDeployments, roiModelDeploymentId]);

  const roiDrawingEnabled =
    Number.isFinite(cameraPosition) &&
    cameraPosition >= 0 &&
    roiStageId.trim().length > 0 &&
    roiModelDeploymentId.trim().length > 0;

  useEffect(() => {
    if (!roiDrawingEnabled) {
      setActiveDrag(null);
      setPolygonDraftPoints([]);
      setPolygonHover(null);
    }
  }, [roiDrawingEnabled]);

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

  return (
    <div className="space-y-6">
      <Dialog
        open={feedCamera !== null}
        onOpenChange={(open) => {
          if (!open) resetFeedDialogState();
        }}
      >
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Camera feed</DialogTitle>
            <DialogDescription>
              {feedCamera ? (
                <span className="font-mono text-xs">{feedCamera.name}</span>
              ) : null}
            </DialogDescription>
          </DialogHeader>

          {feedInitMutation.isPending ? (
            <p className="text-sm text-muted-foreground">Initializing…</p>
          ) : feedInitError ? (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {feedInitError}
            </p>
          ) : feedUrl ? (
            <div className="space-y-4">
              {hardwareLoadError ? (
                <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {hardwareLoadError}
                </p>
              ) : null}

              <div className="grid gap-4 rounded-md border bg-card p-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="feed-exposure">Exposure</Label>
                  <div className="flex items-end gap-2">
                    <span
                      className="w-14 shrink-0 pb-1.5 text-right text-xs tabular-nums text-muted-foreground"
                      aria-hidden
                    >
                      {feedExpMin}
                    </span>
                    <div className="min-w-0 flex-1 space-y-0.5">
                      <input
                        id="feed-exposure"
                        type="range"
                        className="w-full accent-primary disabled:opacity-50"
                        min={feedExpMin}
                        max={feedExpMax}
                        step={1}
                        value={feedExposure}
                        disabled={!hardwareReady || !feedCamera}
                        aria-valuemin={feedExpMin}
                        aria-valuemax={feedExpMax}
                        aria-valuenow={feedExposure}
                        aria-valuetext={`${feedExposure} (range ${feedExpMin}–${feedExpMax})`}
                        onChange={(e) => {
                          if (!feedCamera) return;
                          const v = Math.round(Number(e.target.value));
                          setFeedExposure(v);
                          scheduleSetExposure(feedCamera, v);
                        }}
                      />
                      <input
                        type="number"
                        aria-label="Exposure in milliseconds"
                        className="mx-auto block h-8 w-full max-w-[7.5rem] rounded-md border border-input bg-background px-2 text-center font-mono text-xs tabular-nums shadow-sm disabled:cursor-not-allowed disabled:opacity-50 sm:text-sm"
                        min={feedExpMin}
                        max={feedExpMax}
                        step={1}
                        disabled={!hardwareReady || !feedCamera}
                        value={feedExposure}
                        onChange={(e) => {
                          if (!feedCamera) return;
                          const raw = e.target.value;
                          if (raw === "") return;
                          const n = Number(raw);
                          if (!Number.isFinite(n)) return;
                          const v = Math.min(
                            feedExpMax,
                            Math.max(feedExpMin, Math.round(n))
                          );
                          setFeedExposure(v);
                          scheduleSetExposure(feedCamera, v);
                        }}
                        onBlur={() => {
                          if (!feedCamera) return;
                          const v = Math.min(
                            feedExpMax,
                            Math.max(
                              feedExpMin,
                              Math.round(Number(feedExposure))
                            )
                          );
                          if (v !== feedExposure) {
                            setFeedExposure(v);
                            scheduleSetExposure(feedCamera, v);
                          }
                        }}
                      />
                    </div>
                    <span
                      className="w-14 shrink-0 pb-1.5 text-left text-xs tabular-nums text-muted-foreground"
                      aria-hidden
                    >
                      {feedExpMax}
                    </span>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="feed-wb">White balance</Label>
                  <select
                    id="feed-wb"
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
                    value={feedWb}
                    disabled={!hardwareReady || !feedCamera}
                    onChange={async (e) => {
                      if (!feedCamera) return;
                      const mode = e.target.value as WbVal;
                      setFeedWb(mode);
                      try {
                        await applyWbOnService(feedCamera, mode);
                      } catch (err) {
                        toast.error(
                          getSafeErrorMessage(
                            err as Error,
                            "Failed to set white balance."
                          )
                        );
                      }
                    }}
                  >
                    {WB_VALS.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="space-y-3 rounded-md border bg-card p-4">
                <div className="flex flex-wrap items-end gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="camera-position">Camera position</Label>
                    <input
                      id="camera-position"
                      type="number"
                      className="flex h-9 w-28 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                      value={cameraPosition}
                      min={0}
                      step={1}
                      onChange={(e) => setCameraPosition(Math.max(0, Number(e.target.value)))}
                    />
                  </div>

                  <OutlineDropdownSelect
                    id="roi-stage"
                    label="Stage"
                    value={roiStageId}
                    onValueChange={setRoiStageId}
                    placeholder="Select stage…"
                    items={stages.map((s) => ({ id: s.id, label: s.name }))}
                    className="min-w-[220px] flex-1"
                  />

                  <OutlineDropdownSelect
                    id="roi-model-deployment"
                    label="Model deployment"
                    value={roiModelDeploymentId}
                    onValueChange={setRoiModelDeploymentId}
                    placeholder="Select model deployment…"
                    items={modelDeployments.map((md) => ({
                      id: md.id,
                      label: `${md.model_name ?? md.model_id} (${md.deployment_status})`,
                    }))}
                    className="min-w-[280px] flex-1"
                  />
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <div className="text-sm text-muted-foreground">ROI tool</div>
                  <Button
                    type="button"
                    size="sm"
                    variant={roiTool === "box" ? "secondary" : "outline"}
                    onClick={() => {
                      setRoiTool("box");
                      setPolygonDraftPoints([]);
                      setPolygonHover(null);
                    }}
                    disabled={!roiDrawingEnabled}
                  >
                    Box
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant={roiTool === "polygon" ? "secondary" : "outline"}
                    onClick={() => {
                      setRoiTool("polygon");
                      setActiveDrag(null);
                    }}
                    disabled={!roiDrawingEnabled}
                  >
                    Polygon
                  </Button>
                  {roiTool === "polygon" && polygonDraftPoints.length > 0 ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setPolygonDraftPoints([]);
                        setPolygonHover(null);
                      }}
                    >
                      Clear polygon
                    </Button>
                  ) : null}
                </div>

                {persistedRoiIdsPendingDelete.length > 0 ? (
                  <p className="text-sm text-amber-700 dark:text-amber-500">
                    {persistedRoiIdsPendingDelete.length} saved ROI
                    {persistedRoiIdsPendingDelete.length === 1 ? "" : "s"}{" "}
                    marked for removal — save to delete from the server (or close
                    the dialog to discard).
                  </p>
                ) : null}
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={
                    !feedCamera ||
                    !hardwareReady ||
                    persistBusy ||
                    !!feedInitError ||
                    (roiDrafts.length > 0 &&
                      (!roiStageId || !roiModelDeploymentId))
                  }
                  onClick={async () => {
                    if (!feedCamera) return;
                    if (
                      roiDrafts.length > 0 &&
                      (!roiStageId || !roiModelDeploymentId)
                    ) {
                      toast.error(
                        "Select stage and model deployment before saving new ROIs."
                      );
                      return;
                    }
                    setPersistBusy(true);
                    const roiIdsToDelete = [...persistedRoiIdsPendingDelete];
                    try {
                      await updateCameraConfig(feedCamera.id, {
                        exposure_ms: Math.round(feedExposure),
                        white_balance: feedWb,
                      });

                      let deletedRoiCount = 0;
                      if (roiIdsToDelete.length > 0) {
                        for (const id of roiIdsToDelete) {
                          await deleteRoi(id);
                          deletedRoiCount += 1;
                        }
                        setPersistedRoiIdsPendingDelete([]);
                      }

                      let savedRoiCount = 0;
                      if (roiDrafts.length > 0 && roiStageId && roiModelDeploymentId) {
                        const cp = await upsertCameraPosition({
                          camera_id: feedCamera.id,
                          position: cameraPosition,
                        });
                        for (const roi of roiDrafts) {
                          await createRoi({
                            camera_id: feedCamera.id,
                            camera_position_id: cp.id,
                            stage_id: roiStageId,
                            model_deployment_id: roiModelDeploymentId,
                            type: roi.type,
                            name: roi.name,
                            points: roi.points,
                          });
                          savedRoiCount += 1;
                        }
                        setRoiDrafts([]);
                      }

                      if (deletedRoiCount > 0 || savedRoiCount > 0) {
                        await queryClient.invalidateQueries({
                          queryKey: ["rois", "camera-config-overlay"],
                        });
                      }

                      if (deletedRoiCount > 0 && savedRoiCount > 0) {
                        toast.success(
                          `Saved camera configuration, removed ${deletedRoiCount} ROI(s), added ${savedRoiCount}.`
                        );
                      } else if (deletedRoiCount > 0) {
                        toast.success(
                          `Saved camera configuration and removed ${deletedRoiCount} ROI(s).`
                        );
                      } else if (savedRoiCount > 0) {
                        toast.success(
                          `Saved camera configuration and ${savedRoiCount} ROI(s).`
                        );
                      } else {
                        toast.success("Camera configuration saved.");
                      }
                      await queryClient.invalidateQueries({
                        queryKey: ["cameras"],
                      });
                    } catch (e) {
                      toast.error(
                        getSafeErrorMessage(
                          e as Error,
                          "Failed to save configuration."
                        )
                      );
                    } finally {
                      setPersistBusy(false);
                    }
                  }}
                >
                  {persistBusy ? "Saving…" : "Save"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={
                    !feedCamera ||
                    !hardwareReady ||
                    persistBusy ||
                    !!feedInitError
                  }
                  onClick={async () => {
                    if (!feedCamera) return;
                    setPersistBusy(true);
                    try {
                      const doc = await getCamera(feedCamera.id);
                      const cfg = doc.config ?? {};
                      if (typeof cfg.exposure_ms === "number") {
                        const r = await cameraServicePost(
                          feedCamera.camera_service_url,
                          "/set_exposure",
                          {
                            camera: feedCamera.name,
                            exposure: Math.round(cfg.exposure_ms),
                          }
                        );
                        if (!r.success)
                          throw new Error(r.message || "set_exposure failed.");
                      }
                      if (
                        cfg.white_balance === "off" ||
                        cfg.white_balance === "once"
                      ) {
                        await applyWbOnService(feedCamera, cfg.white_balance);
                      }
                      await loadHardwareFromService(feedCamera);
                      setPersistedRoiIdsPendingDelete([]);
                      toast.success(
                        "Loaded configuration from the database and applied to the camera."
                      );
                    } catch (e) {
                      toast.error(
                        getSafeErrorMessage(
                          e as Error,
                          "Failed to load configuration from the database."
                        )
                      );
                    } finally {
                      setPersistBusy(false);
                    }
                  }}
                >
                  Load
                </Button>
              </div>

              <CameraFeed
                feedUrl={feedUrl}
                feedCameraName={feedCamera?.name ?? ""}
                feedStreamLoaded={feedStreamLoaded}
                setFeedStreamLoaded={setFeedStreamLoaded}
                roiDrawingEnabled={roiDrawingEnabled}
                roiTool={roiTool}
                setPendingRoiType={setPendingRoiType}
                setPendingRoiPoints={setPendingRoiPoints}
                openRoiNameDialog={() => {
                  setPendingRoiName("");
                  setRoiNameDialogOpen(true);
                }}
                activeDrag={activeDrag}
                setActiveDrag={setActiveDrag as any}
                polygonDraftPoints={polygonDraftPoints}
                setPolygonDraftPoints={setPolygonDraftPoints as any}
                polygonHover={polygonHover}
                setPolygonHover={setPolygonHover}
                persistedRois={visiblePersistedRoisForOverlay}
                roiDrafts={roiDrafts}
                stagePersistedRoiRemoval={stagePersistedRoiRemoval}
                removeDraftRoi={(id) =>
                  setRoiDrafts((prev) => prev.filter((x) => x.id !== id))
                }
              />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Feed URL unavailable.
            </p>
          )}
        </DialogContent>
      </Dialog>

      <RoiNameDialog
        open={roiNameDialogOpen}
        roiName={pendingRoiName}
        onRoiNameChange={setPendingRoiName}
        canSubmit={!!pendingRoiPoints && !!pendingRoiName.trim()}
        onCancel={() => {
          setRoiNameDialogOpen(false);
          setPendingRoiPoints(null);
          setPendingRoiName("");
        }}
        onSubmit={() => {
          const nm = pendingRoiName.trim();
          if (!nm || !pendingRoiPoints) return;
          setRoiDrafts((prev) => [
            ...prev,
            {
              id: newDraftRoiClientId(),
              name: nm,
              type: pendingRoiType,
              points: pendingRoiPoints,
            },
          ]);
          setPendingRoiPoints(null);
          setPendingRoiType("box");
          setPendingRoiName("");
          setRoiNameDialogOpen(false);
        }}
      />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4 py-4">
          <div className="flex flex-wrap items-center gap-2">
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
                <DropdownMenuItem
                  onClick={() => {
                    setSelectedServiceId("");
                    setSelectedCameraSetId("");
                    setPage(1);
                  }}
                >
                  All camera services
                </DropdownMenuItem>
                {services.map((svc: CameraService) => (
                  <DropdownMenuItem
                    key={svc.id}
                    onClick={() => {
                      setSelectedServiceId(svc.id);
                      if (
                        selectedCameraSetId &&
                        cameraSetById.get(selectedCameraSetId)
                          ?.camera_service_id !== svc.id
                      ) {
                        setSelectedCameraSetId("");
                      }
                      setPage(1);
                    }}
                  >
                    {svc.line_name ?? svc.line_id}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="justify-between">
                  {selectedCameraSetId
                    ? (cameraSetById.get(selectedCameraSetId)?.name ??
                      "Camera set")
                    : "All camera sets"}
                  <ChevronDown className="ml-2 h-4 w-4 opacity-50" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuItem
                  onClick={() => {
                    setSelectedCameraSetId("");
                    setPage(1);
                  }}
                >
                  All camera sets
                </DropdownMenuItem>
                {cameraSetsForSelectedService.map((cs: CameraSet) => (
                  <DropdownMenuItem
                    key={cs.id}
                    onClick={() => {
                      setSelectedCameraSetId(cs.id);
                      setPage(1);
                    }}
                  >
                    {cs.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </CardHeader>

        <CardContent>
          {items.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">
              No cameras yet.
            </p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="font-medium">Name</TableHead>
                    <TableHead>Line</TableHead>
                    <TableHead className="text-muted-foreground">
                      Service URL
                    </TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((cam) => (
                    <TableRow key={cam.id}>
                      <TableCell className="font-medium">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-medium">{cam.name}</span>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={async () => {
                              setFeedCamera(cam);
                              setFeedInitError(null);
                              setHardwareLoadError(null);
                              setHardwareReady(false);
                              setFeedStreamLoaded(false);
                              try {
                                await feedInitMutation.mutateAsync(cam);
                              } catch {
                                return;
                              }
                              try {
                                await loadHardwareFromService(cam);
                              } catch (e) {
                                setHardwareLoadError(
                                  getSafeErrorMessage(
                                    e as Error,
                                    "Failed to read camera hardware settings."
                                  )
                                );
                              }
                            }}
                          >
                            Configure
                          </Button>
                        </div>
                      </TableCell>
                      <TableCell>{cam.line_name ?? cam.line_id}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {cam.camera_service_url}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => reinitMutation.mutate(cam)}
                          disabled={reinitMutation.isPending}
                        >
                          {reinitMutation.isPending
                            ? "Re-initializing…"
                            : "Re-initialize"}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
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
