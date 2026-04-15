"use client";

import { useEffect, useRef, useState } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { closePolygon, metricsFromPoints, type RoiTool } from "./roi-drawing";
import type { Roi } from "@/lib/api/types";

export function CameraFeed(props: {
  feedUrl: string;
  feedCameraName: string;
  feedStreamLoaded: boolean;
  setFeedStreamLoaded: (v: boolean) => void;
  roiDrawingEnabled: boolean;

  roiTool: RoiTool;
  setPendingRoiType: (t: "box" | "polygon") => void;
  setPendingRoiPoints: (pts: number[][] | null) => void;
  openRoiNameDialog: () => void;

  activeDrag: { x1: number; y1: number; x2: number; y2: number } | null;
  setActiveDrag: (
    next:
      | { x1: number; y1: number; x2: number; y2: number }
      | null
      | ((prev: { x1: number; y1: number; x2: number; y2: number } | null) => any)
  ) => void;
  polygonDraftPoints: number[][];
  setPolygonDraftPoints: (updater: any) => void;
  polygonHover: { x: number; y: number } | null;
  setPolygonHover: (v: { x: number; y: number } | null) => void;

  persistedRois: Roi[];
  roiDrafts: Array<{ id: string; name: string; type: "box" | "polygon"; points: number[][] }>;

  stagePersistedRoiRemoval: (id: string) => void;

  removeDraftRoi: (id: string) => void;
}) {
  const {
    feedUrl,
    feedCameraName,
    feedStreamLoaded,
    setFeedStreamLoaded,
    roiDrawingEnabled,
    roiTool,
    setPendingRoiType,
    setPendingRoiPoints,
    openRoiNameDialog,
    activeDrag,
    setActiveDrag,
    polygonDraftPoints,
    setPolygonDraftPoints,
    polygonHover,
    setPolygonHover,
    persistedRois,
    roiDrafts,
    stagePersistedRoiRemoval,
    removeDraftRoi,
  } = props;

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [streamLayout, setStreamLayout] = useState({ w: 0, h: 0 });

  function syncCanvasToImage() {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas) return;
    const w = Math.max(1, Math.floor(img.clientWidth));
    const h = Math.max(1, Math.floor(img.clientHeight));
    if (canvas.width !== w) canvas.width = w;
    if (canvas.height !== h) canvas.height = h;
  }

  function bumpStreamLayout() {
    const img = imgRef.current;
    if (!img) return;
    const w = Math.max(0, Math.floor(img.clientWidth));
    const h = Math.max(0, Math.floor(img.clientHeight));
    setStreamLayout((prev) => (prev.w === w && prev.h === h ? prev : { w, h }));
  }

  function drawOverlay() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const drawBox = (points: number[][], color: string) => {
      if (!points || points.length < 4) return;
      const [p1, , p3] = points;
      const x1 = p1[0];
      const y1 = p1[1];
      const x2 = p3[0];
      const y2 = p3[1];
      const left = Math.min(x1, x2);
      const top = Math.min(y1, y2);
      const w = Math.abs(x2 - x1);
      const h = Math.abs(y2 - y1);
      if (w < 2 || h < 2) return;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.fillStyle = `${color}22`;
      ctx.fillRect(left, top, w, h);
      ctx.strokeRect(left, top, w, h);
    };

    const drawPolygon = (points: number[][], color: string) => {
      if (!points || points.length < 3) return;
      ctx.beginPath();
      ctx.moveTo(points[0]![0]!, points[0]![1]!);
      for (let i = 1; i < points.length; i++) ctx.lineTo(points[i]![0]!, points[i]![1]!);
      ctx.closePath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.fillStyle = `${color}22`;
      ctx.fill();
      ctx.stroke();
    };

    for (const r of persistedRois) {
      if (!r.points || r.points.length < 3) continue;
      if (r.type === "polygon") drawPolygon(r.points, "#3b82f6");
      else drawBox(r.points, "#3b82f6");
    }
    for (const r of roiDrafts) {
      if (!r.points || r.points.length < 3) continue;
      if (r.type === "polygon") drawPolygon(r.points, "#22c55e");
      else drawBox(r.points, "#22c55e");
    }
    if (activeDrag) {
      drawBox(
        [
          [activeDrag.x1, activeDrag.y1],
          [activeDrag.x2, activeDrag.y1],
          [activeDrag.x2, activeDrag.y2],
          [activeDrag.x1, activeDrag.y2],
        ],
        "#f59e0b"
      );
    }
    if (roiTool === "polygon" && polygonDraftPoints.length > 0) {
      const pts = polygonHover
        ? [...polygonDraftPoints, [polygonHover.x, polygonHover.y]]
        : polygonDraftPoints;
      ctx.beginPath();
      ctx.moveTo(pts[0]![0]!, pts[0]![1]!);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i]![0]!, pts[i]![1]!);
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth = 2;
      ctx.stroke();
      for (const p of polygonDraftPoints) {
        ctx.beginPath();
        ctx.arc(p[0]!, p[1]!, 4, 0, Math.PI * 2);
        ctx.fillStyle = "#f59e0b";
        ctx.fill();
        ctx.strokeStyle = "#11182755";
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }
  }

  useEffect(() => {
    if (!feedStreamLoaded) return;
    syncCanvasToImage();
    bumpStreamLayout();
    drawOverlay();
    const onResize = () => {
      syncCanvasToImage();
      bumpStreamLayout();
      drawOverlay();
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feedStreamLoaded]);

  useEffect(() => {
    if (!feedStreamLoaded) return;
    syncCanvasToImage();
    bumpStreamLayout();
    drawOverlay();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feedStreamLoaded, activeDrag, roiTool, polygonDraftPoints, polygonHover, persistedRois, roiDrafts]);

  return (
    <div className="space-y-2">
      {feedStreamLoaded && !roiDrawingEnabled ? (
        <p className="text-sm text-muted-foreground">
          Select camera position, stage, and model deployment before drawing ROIs on the feed.
        </p>
      ) : null}

      <div className="relative overflow-hidden rounded-md border bg-muted/20">
        {!feedStreamLoaded ? (
          <div className="flex aspect-video w-full items-center justify-center bg-muted/30">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground" />
              Loading stream…
            </div>
          </div>
        ) : null}

        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          key={feedUrl}
          src={feedUrl}
          alt={`Live feed: ${feedCameraName}`}
          className={feedStreamLoaded ? "h-auto w-full" : "h-0 w-0"}
          ref={imgRef}
          onLoad={() => {
            setFeedStreamLoaded(true);
            setTimeout(() => {
              syncCanvasToImage();
              bumpStreamLayout();
              drawOverlay();
            }, 0);
          }}
          onError={() => setFeedStreamLoaded(false)}
        />

        {feedStreamLoaded ? (
          <canvas
            ref={canvasRef}
            className={cn(
              "absolute inset-0 h-full w-full",
              roiDrawingEnabled ? "cursor-crosshair" : "pointer-events-none cursor-not-allowed"
            )}
            onMouseDown={(e) => {
              if (!roiDrawingEnabled) return;
              const canvas = canvasRef.current;
              if (!canvas) return;
              const rect = canvas.getBoundingClientRect();
              const x = Math.min(canvas.width, Math.max(0, e.clientX - rect.left));
              const y = Math.min(canvas.height, Math.max(0, e.clientY - rect.top));

              if (roiTool === "polygon") {
                setPolygonHover({ x, y });
                setPolygonDraftPoints((prev: number[][]) => {
                  if (prev.length >= 3) {
                    const first = prev[0]!;
                    const dx = first[0]! - x;
                    const dy = first[1]! - y;
                    if (Math.hypot(dx, dy) <= 10) {
                      setPendingRoiType("polygon");
                      setPendingRoiPoints(closePolygon(prev));
                      openRoiNameDialog();
                      setPolygonHover(null);
                      return [];
                    }
                  }
                  return [...prev, [x, y]];
                });
                return;
              }

              setActiveDrag({ x1: x, y1: y, x2: x, y2: y });
            }}
            onMouseMove={(e) => {
              if (!roiDrawingEnabled) return;
              const canvas = canvasRef.current;
              if (!canvas) return;
              const rect = canvas.getBoundingClientRect();
              const x = Math.min(canvas.width, Math.max(0, e.clientX - rect.left));
              const y = Math.min(canvas.height, Math.max(0, e.clientY - rect.top));

              if (roiTool === "polygon") {
                setPolygonHover({ x, y });
                return;
              }

              if (!activeDrag) return;
              setActiveDrag((prev: any) => (prev ? { ...prev, x2: x, y2: y } : prev));
            }}
            onMouseUp={() => {
              if (!roiDrawingEnabled) return;
              if (roiTool === "polygon") return;
              if (!activeDrag) return;
              const left = Math.min(activeDrag.x1, activeDrag.x2);
              const top = Math.min(activeDrag.y1, activeDrag.y2);
              const right = Math.max(activeDrag.x1, activeDrag.x2);
              const bottom = Math.max(activeDrag.y1, activeDrag.y2);
              setActiveDrag(null);
              if (right - left < 4 || bottom - top < 4) return;
              setPendingRoiType("box");
              setPendingRoiPoints([
                [left, top],
                [right, top],
                [right, bottom],
                [left, bottom],
              ]);
              openRoiNameDialog();
            }}
            onDoubleClick={() => {
              if (!roiDrawingEnabled) return;
              if (roiTool !== "polygon") return;
              if (polygonDraftPoints.length < 3) return;
              setPendingRoiType("polygon");
              setPendingRoiPoints(closePolygon(polygonDraftPoints));
              openRoiNameDialog();
              setPolygonDraftPoints([]);
              setPolygonHover(null);
            }}
            onMouseLeave={() => {
              if (activeDrag) setActiveDrag(null);
              setPolygonHover(null);
            }}
          />
        ) : null}

        {feedStreamLoaded ? (
          <div className="pointer-events-none absolute inset-0 z-20">
            {roiTool === "polygon" && polygonDraftPoints.length > 0 ? (
              <div className="pointer-events-auto absolute right-2 top-2">
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="h-7 w-7 border-amber-500/40 bg-background/80 p-0 text-amber-600 shadow-md hover:bg-amber-500/10"
                  aria-label="Clear polygon draft"
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    setPolygonDraftPoints([]);
                    setPolygonHover(null);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ) : null}

            {streamLayout.w > 0 && streamLayout.h > 0
              ? persistedRois.map((r) => {
              const m = metricsFromPoints(r.points);
              if (!m) return null;
              const btn = 28;
              const leftPct = ((m.left + m.width - btn) / streamLayout.w) * 100;
              const topPct = (m.top / streamLayout.h) * 100;
              return (
                <Button
                  key={r.id}
                  type="button"
                  variant="destructive"
                  size="icon"
                  className="pointer-events-auto absolute h-7 w-7 min-h-7 min-w-7 p-0 shadow-md"
                  style={{ left: `${Math.max(0, leftPct)}%`, top: `${Math.max(0, topPct)}%` }}
                  aria-label={`Remove saved ROI ${r.name} on save`}
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    stagePersistedRoiRemoval(r.id);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              );
            })
              : null}

            {streamLayout.w > 0 && streamLayout.h > 0
              ? roiDrafts.map((d) => {
              const m = metricsFromPoints(d.points);
              if (!m) return null;
              const btn = 28;
              const leftPct = ((m.left + m.width - btn) / streamLayout.w) * 100;
              const topPct = (m.top / streamLayout.h) * 100;
              return (
                <Button
                  key={d.id}
                  type="button"
                  variant="outline"
                  size="icon"
                  className="pointer-events-auto absolute h-7 w-7 min-h-7 min-w-7 border-destructive/50 p-0 text-destructive shadow-md hover:bg-destructive/10"
                  style={{ left: `${Math.max(0, leftPct)}%`, top: `${Math.max(0, topPct)}%` }}
                  aria-label={`Remove draft ROI ${d.name}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    removeDraftRoi(d.id);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              );
            })
              : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

