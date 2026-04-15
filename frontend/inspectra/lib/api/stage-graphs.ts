/**
 * Stage graphs API (SUPER_ADMIN only).
 */

import type { StageGraph, StageGraphListResponse } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export async function listStageGraphs(params?: {
  skip?: number;
  limit?: number;
}): Promise<StageGraphListResponse> {
  const search = new URLSearchParams();
  if (params?.skip != null) search.set("skip", String(params.skip));
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  const url = qs
    ? `${getApiBase()}/stage-graphs?${qs}`
    : `${getApiBase()}/stage-graphs`;
  const res = await fetchWithAuth(url, {});
  return handleResponse<StageGraphListResponse>(res);
}

export async function createStageGraph(payload: {
  name: string;
}): Promise<StageGraph> {
  const res = await fetchWithAuth(`${getApiBase()}/stage-graphs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<StageGraph>(res);
}

export type StageGraphStageItem = {
  stage_id: string;
  order: number;
  label?: string;
};

export type StageGraphStageResponse = StageGraphStageItem & {
  stage_name?: string;
};

export type StageGraphDetail = StageGraph & {
  stages?: StageGraphStageResponse[];
};

export async function getStageGraph(id: string): Promise<StageGraphDetail> {
  const res = await fetchWithAuth(`${getApiBase()}/stage-graphs/${id}`, {});
  return handleResponse<StageGraphDetail>(res);
}

export async function updateStageGraphStages(
  id: string,
  payload: { stages: StageGraphStageItem[] }
): Promise<StageGraphDetail> {
  const res = await fetchWithAuth(`${getApiBase()}/stage-graphs/${id}/stages`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<StageGraphDetail>(res);
}
