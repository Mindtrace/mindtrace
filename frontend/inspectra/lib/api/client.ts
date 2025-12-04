// API client for communicating with FastAPI backend
// This will use openapi-typescript generated types when backend is ready

import { z } from "zod";
import type { ApiResponse } from "./types";

// API base URL - should come from environment variables
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Zod schema for API response validation
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const apiResponseSchema = z.object({
  status: z.string(),
  message: z.string(),
  timestamp: z.string(),
});

// Mock data for development (backend not ready yet)
const mockApiResponse: ApiResponse = {
  status: "success",
  message: "Inspectra API is ready! This is mock data until backend is connected.",
  timestamp: new Date().toISOString(),
};

/**
 * Example API function - this demonstrates how backend calls will be structured
 * When backend is ready, uncomment the fetch call and remove the mock return
 */
export async function getHealthCheck(): Promise<ApiResponse> {
  // TODO: Uncomment when backend is ready
  // const response = await fetch(`${API_BASE_URL}/api/health`, {
  //   method: "GET",
  //   headers: {
  //     "Content-Type": "application/json",
  //   },
  // });
  //
  // if (!response.ok) {
  //   throw new Error(`API error: ${response.statusText}`);
  // }
  //
  // const data = await response.json();
  // return apiResponseSchema.parse(data);

  // Mock response for now
  return Promise.resolve(mockApiResponse);
}

