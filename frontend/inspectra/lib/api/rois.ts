/**
 * ROIs API (SUPER_ADMIN only).
 */

import type { Roi, RoiListResponse } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export async function listRois(params?: {
  line_id?: string;
  camera_id?: string;
  camera_position_id?: string;
  position?: number;
  stage_id?: string;
  model_deployment_id?: string;
  skip?: number;
  limit?: number;
}): Promise<RoiListResponse> {
  const search = new URLSearchParams();
  if (params?.line_id) search.set("line_id", params.line_id);
  if (params?.camera_id) search.set("camera_id", params.camera_id);
  if (params?.camera_position_id)
    search.set("camera_position_id", params.camera_position_id);
  if (params?.position !== undefined && params?.position !== null)
    search.set("position", String(params.position));
  if (params?.stage_id) search.set("stage_id", params.stage_id);
  if (params?.model_deployment_id)
    search.set("model_deployment_id", params.model_deployment_id);
  if (params?.skip != null) search.set("skip", String(params.skip));
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  const url = qs ? `${getApiBase()}/rois?${qs}` : `${getApiBase()}/rois`;
  const res = await fetchWithAuth(url, {});
  return handleResponse<RoiListResponse>(res);
}

export async function createRoi(payload: {
  camera_id: string;
  camera_position_id: string;
  stage_id: string;
  model_deployment_id: string;
  name?: string;
  type?: "box" | "polygon";
  points: number[][];
}): Promise<Roi> {
  const res = await fetchWithAuth(`${getApiBase()}/rois`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<Roi>(res);
}

export async function deleteRoi(id: string): Promise<void> {
  const res = await fetchWithAuth(`${getApiBase()}/rois/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  await handleResponse<void>(res);
}
