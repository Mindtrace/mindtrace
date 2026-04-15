/**
 * Camera services API (SUPER_ADMIN only).
 */

import type { CameraService, CameraServiceListResponse } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export async function listCameraServices(params?: {
  line_id?: string;
  skip?: number;
  limit?: number;
}): Promise<CameraServiceListResponse> {
  const search = new URLSearchParams();
  if (params?.line_id != null) search.set("line_id", params.line_id);
  if (params?.skip != null) search.set("skip", String(params.skip));
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  const url = qs
    ? `${getApiBase()}/camera-services?${qs}`
    : `${getApiBase()}/camera-services`;
  const res = await fetchWithAuth(url, {});
  return handleResponse<CameraServiceListResponse>(res);
}

export async function getCameraService(id: string): Promise<CameraService> {
  const res = await fetchWithAuth(`${getApiBase()}/camera-services/${id}`, {});
  return handleResponse<CameraService>(res);
}

export async function updateCameraService(
  id: string,
  payload: {
    cam_service_status?: string;
    health_status?: string;
    cam_service_url?: string;
  }
): Promise<CameraService> {
  const body: Record<string, string> = {};
  if (payload.cam_service_status != null)
    body.cam_service_status = payload.cam_service_status;
  if (payload.health_status != null) body.health_status = payload.health_status;
  if (payload.cam_service_url != null)
    body.cam_service_url = payload.cam_service_url;
  const res = await fetchWithAuth(`${getApiBase()}/camera-services/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse<CameraService>(res);
}
