// Auth API functions

import { api, setToken, clearToken } from "./client";
import type {
  LoginPayload,
  RegisterPayload,
  TokenResponse,
  User,
  ChangeOwnPasswordRequest,
} from "./types";

// Login user
export async function login(payload: LoginPayload): Promise<TokenResponse> {
  const response = await api.post<TokenResponse>("/auth/login", payload, {
    auth: false,
  });
  setToken(response.access_token);
  return response;
}

// Register new user
export async function register(
  payload: RegisterPayload
): Promise<TokenResponse> {
  const response = await api.post<TokenResponse>("/auth/register", payload, {
    auth: false,
  });
  setToken(response.access_token);
  return response;
}

// Logout (client-side only - clears token)
export function logout(): void {
  clearToken();
}

// Get current user profile
export async function getMe(): Promise<User> {
  return api.get<User>("/me");
}

// Change own password
export async function changePassword(
  payload: ChangeOwnPasswordRequest
): Promise<void> {
  await api.put<void>("/me/password", payload);
}
