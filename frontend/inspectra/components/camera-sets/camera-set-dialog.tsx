"use client";

import { ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CameraService, CameraSet } from "@/lib/api/types";

export function CameraSetDialog(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: CameraSet | null;
  services: CameraService[];
  serviceById: Map<string, CameraService>;

  draftServiceId: string;
  setDraftServiceId: (id: string) => void;
  draftName: string;
  setDraftName: (v: string) => void;
  draftBatchSize: string;
  setDraftBatchSize: (v: string) => void;
  draftSelected: Set<string>;
  toggleCamera: (name: string) => void;

  loadingCameras: boolean;
  cameraLoadError: string | null;
  availableCameras: string[];
  disabledCameraReason: Map<string, string>;

  onReloadCameras: () => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  const {
    open,
    onOpenChange,
    editing,
    services,
    serviceById,
    draftServiceId,
    setDraftServiceId,
    draftName,
    setDraftName,
    draftBatchSize,
    setDraftBatchSize,
    draftSelected,
    toggleCamera,
    loadingCameras,
    cameraLoadError,
    availableCameras,
    disabledCameraReason,
    onReloadCameras,
    onCancel,
    onSubmit,
  } = props;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] flex-col sm:max-w-md">
        <DialogHeader className="shrink-0">
          <DialogTitle>
            {editing ? "Edit camera set" : "Create camera set"}
          </DialogTitle>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
          <div className="space-y-2">
            <Label>Camera service</Label>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="w-full justify-between">
                  {serviceById.get(draftServiceId)?.line_name ??
                    serviceById.get(draftServiceId)?.line_id ??
                    "Select camera service"}
                  <ChevronDown className="h-4 w-4 opacity-50" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="start"
                className="w-[var(--radix-dropdown-menu-trigger-width)]"
              >
                {services.map((svc) => (
                  <DropdownMenuItem
                    key={svc.id}
                    onClick={() => {
                      setDraftServiceId(svc.id);
                    }}
                  >
                    {svc.line_name ?? svc.line_id}{" "}
                    <span className="ml-2 font-mono text-xs text-muted-foreground">
                      {svc.cam_service_url}
                    </span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <div className="space-y-2">
            <Label htmlFor="camera-set-name">Name</Label>
            <Input
              id="camera-set-name"
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="camera-set-batch-size">Batch size</Label>
            <Input
              id="camera-set-batch-size"
              type="number"
              min={1}
              step={1}
              value={draftBatchSize}
              onChange={(e) => setDraftBatchSize(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Number of items processed together for this set (saved with the
              camera set).
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-end justify-between gap-2">
              <div>
                <Label>Cameras</Label>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={onReloadCameras}
                disabled={loadingCameras || !draftServiceId}
              >
                {loadingCameras ? "Loading…" : "Reload"}
              </Button>
            </div>

            {cameraLoadError ? (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {cameraLoadError}
              </p>
            ) : null}

            <div className="max-h-[360px] overflow-y-auto rounded-md border p-3">
              {!draftServiceId ? (
                <p className="text-sm text-muted-foreground">
                  Select a camera service first.
                </p>
              ) : availableCameras.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {loadingCameras ? "Loading cameras…" : "No cameras found."}
                </p>
              ) : (
                <div className="space-y-2">
                  {availableCameras.map((cam) => {
                    const reason = disabledCameraReason.get(cam);
                    const disabled = reason != null && !draftSelected.has(cam);
                    return (
                      <label
                        key={cam}
                        className={`flex cursor-pointer items-start gap-3 rounded-md px-2 py-1.5 hover:bg-accent/40 ${
                          disabled ? "opacity-60" : ""
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="mt-0.5 h-4 w-4"
                          checked={draftSelected.has(cam)}
                          onChange={() => toggleCamera(cam)}
                          disabled={disabled}
                        />
                        <div className="min-w-0">
                          <div className="truncate font-mono text-xs">{cam}</div>
                          {reason ? (
                            <div className="text-xs text-muted-foreground">
                              {reason}
                            </div>
                          ) : null}
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="text-xs text-muted-foreground">
              Selected: {draftSelected.size}
            </div>
          </div>
        </div>

        <DialogFooter className="shrink-0">
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" onClick={onSubmit}>
            {editing ? "Save" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

