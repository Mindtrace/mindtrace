/**
 * Cameras API (SUPER_ADMIN only).
 */

import type { Camera, CameraListResponse } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export async function listCameras(params?: {
  camera_service_id?: string;
  camera_set_id?: string;
  skip?: number;
  limit?: number;
}): Promise<CameraListResponse> {
  const search = new URLSearchParams();
  if (params?.camera_service_id != null)
    search.set("camera_service_id", params.camera_service_id);
  if (params?.camera_set_id != null)
    search.set("camera_set_id", params.camera_set_id);
  if (params?.skip != null) search.set("skip", String(params.skip));
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  const url = qs ? `${getApiBase()}/cameras?${qs}` : `${getApiBase()}/cameras`;
  const res = await fetchWithAuth(url, {});
  return handleResponse<CameraListResponse>(res);
}

export async function getCamera(id: string): Promise<Camera> {
  const res = await fetchWithAuth(`${getApiBase()}/cameras/${id}`, {});
  return handleResponse<Camera>(res);
}

export type UpdateCameraConfigBody = {
  exposure_ms?: number;
  white_balance?: "off" | "once";
};

export async function updateCameraConfig(
  id: string,
  body: UpdateCameraConfigBody
): Promise<Camera> {
  const res = await fetchWithAuth(`${getApiBase()}/cameras/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse<Camera>(res);
}
