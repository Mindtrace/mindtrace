/**
 * Line structure API (SUPER_ADMIN only).
 *
 * Part groups -> parts -> stage graphs.
 */

import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export type PartItem = {
  id?: string;
  part_number: string;
  stage_graph_id?: string | null;
  stage_graph_name?: string | null;
};
export type PartGroupItem = { id?: string; name: string; parts: PartItem[] };

export type LineStructureResponse = {
  line_id: string;
  part_groups: PartGroupItem[];
};

export async function getLineStructure(
  lineId: string
): Promise<LineStructureResponse> {
  const res = await fetchWithAuth(
    `${getApiBase()}/lines/${lineId}/structure`,
    {}
  );
  return handleResponse<LineStructureResponse>(res);
}

export async function updateLineStructure(
  lineId: string,
  payload: { part_groups: PartGroupItem[] }
): Promise<LineStructureResponse> {
  const res = await fetchWithAuth(`${getApiBase()}/lines/${lineId}/structure`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return handleResponse<LineStructureResponse>(res);
}
