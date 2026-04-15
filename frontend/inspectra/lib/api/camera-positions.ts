/**
 * Camera positions API (SUPER_ADMIN only).
 */

import type { CameraPosition } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export async function upsertCameraPosition(payload: {
  camera_id: string;
  position: number;
}): Promise<CameraPosition> {
  const res = await fetchWithAuth(`${getApiBase()}/camera-positions:upsert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<CameraPosition>(res);
}

