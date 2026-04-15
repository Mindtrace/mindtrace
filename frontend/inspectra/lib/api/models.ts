/**
 * Models API (SUPER_ADMIN only).
 */

import type { Model, ModelListResponse } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export async function listModels(params?: {
  skip?: number;
  limit?: number;
}): Promise<ModelListResponse> {
  const search = new URLSearchParams();
  if (params?.skip != null) search.set("skip", String(params.skip));
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  const url = qs ? `${getApiBase()}/models?${qs}` : `${getApiBase()}/models`;
  const res = await fetchWithAuth(url, {});
  return handleResponse<ModelListResponse>(res);
}

export async function createModel(payload: {
  name: string;
  version: string;
}): Promise<Model> {
  const res = await fetchWithAuth(`${getApiBase()}/models`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return handleResponse<Model>(res);
}

export async function getModel(id: string): Promise<Model> {
  const res = await fetchWithAuth(`${getApiBase()}/models/${id}`, {});
  return handleResponse<Model>(res);
}

export async function updateModel(
  id: string,
  payload: { name?: string; version?: string }
): Promise<Model> {
  const res = await fetchWithAuth(`${getApiBase()}/models/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return handleResponse<Model>(res);
}
