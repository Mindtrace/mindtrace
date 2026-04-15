/**
 * Model deployments API (SUPER_ADMIN only).
 */

import type { ModelDeployment, ModelDeploymentListResponse } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export async function listModelDeployments(params?: {
  organization_id?: string;
  plant_id?: string;
  line_id?: string;
  skip?: number;
  limit?: number;
}): Promise<ModelDeploymentListResponse> {
  const search = new URLSearchParams();
  if (params?.organization_id != null)
    search.set("organization_id", params.organization_id);
  if (params?.plant_id != null) search.set("plant_id", params.plant_id);
  if (params?.line_id != null) search.set("line_id", params.line_id);
  if (params?.skip != null) search.set("skip", String(params.skip));
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  const url = qs
    ? `${getApiBase()}/model-deployments?${qs}`
    : `${getApiBase()}/model-deployments`;
  const res = await fetchWithAuth(url, {});
  return handleResponse<ModelDeploymentListResponse>(res);
}

export async function getModelDeployment(id: string): Promise<ModelDeployment> {
  const res = await fetchWithAuth(`${getApiBase()}/model-deployments/${id}`, {});
  return handleResponse<ModelDeployment>(res);
}

export async function updateModelDeployment(
  id: string,
  payload: {
    deployment_status?: string;
    health_status?: string;
    model_server_url?: string;
  }
): Promise<ModelDeployment> {
  const body: Record<string, string> = {};
  if (payload.deployment_status != null)
    body.deployment_status = payload.deployment_status;
  if (payload.health_status != null) body.health_status = payload.health_status;
  if (payload.model_server_url != null)
    body.model_server_url = payload.model_server_url;
  const res = await fetchWithAuth(`${getApiBase()}/model-deployments/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse<ModelDeployment>(res);
}
