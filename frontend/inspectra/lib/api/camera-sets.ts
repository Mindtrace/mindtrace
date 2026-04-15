/**
 * Camera sets API (SUPER_ADMIN only).
 */

import type { CameraSet, CameraSetListResponse } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export async function listCameraSets(params?: {
  camera_service_id?: string;
  skip?: number;
  limit?: number;
}): Promise<CameraSetListResponse> {
  const search = new URLSearchParams();
  if (params?.camera_service_id != null)
    search.set("camera_service_id", params.camera_service_id);
  if (params?.skip != null) search.set("skip", String(params.skip));
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  const url = qs ? `${getApiBase()}/camera-sets?${qs}` : `${getApiBase()}/camera-sets`;
  const res = await fetchWithAuth(url, {});
  return handleResponse<CameraSetListResponse>(res);
}

export async function createCameraSet(payload: {
  camera_service_id: string;
  name: string;
  cameras: string[];
  batch_size?: number;
}): Promise<CameraSet> {
  const res = await fetchWithAuth(`${getApiBase()}/camera-sets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      camera_service_id: payload.camera_service_id,
      name: payload.name,
      cameras: payload.cameras,
      batch_size: payload.batch_size ?? 1,
    }),
  });
  return handleResponse<CameraSet>(res);
}

export async function updateCameraSet(
  id: string,
  payload: { name?: string; cameras?: string[]; batch_size?: number }
): Promise<CameraSet> {
  const res = await fetchWithAuth(`${getApiBase()}/camera-sets/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<CameraSet>(res);
}

export async function deleteCameraSet(id: string): Promise<{ success: boolean; message: string }> {
  const res = await fetchWithAuth(`${getApiBase()}/camera-sets/${id}`, {
    method: "DELETE",
  });
  return handleResponse<{ success: boolean; message: string }>(res);
}

