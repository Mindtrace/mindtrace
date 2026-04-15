/**
 * Auth API: login, refresh, getMe. Also provides fetchWithAuth for other modules.
 */

import type { TokenResponse, User } from "./types";
import {
  ACCESS_TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  SESSION_EXPIRED_MESSAGE,
  clearSessionAndRedirect,
  getApiBase,
  getAuthHeaders,
  handleResponse,
} from "./core";

export async function fetchWithAuth(
  url: string,
  init: RequestInit
): Promise<Response> {
  const withAuth = {
    ...init,
    headers: {
      ...getAuthHeaders(),
      ...(init.headers as Record<string, string>),
    },
  };
  let res = await fetch(url, withAuth);
  if (res.status === 401) {
    const newTokens = await refreshTokens();
    if (!newTokens) {
      clearSessionAndRedirect();
      throw new Error(SESSION_EXPIRED_MESSAGE);
    }
    res = await fetch(url, {
      ...init,
      headers: {
        ...getAuthHeaders(),
        ...(init.headers as Record<string, string>),
      },
    });
    if (res.status === 401) {
      clearSessionAndRedirect();
      throw new Error(SESSION_EXPIRED_MESSAGE);
    }
  }
  return res;
}

export async function login(
  email: string,
  password: string
): Promise<TokenResponse> {
  const res = await fetch(`${getApiBase()}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: email.trim().toLowerCase(),
      password: password.trim(),
    }),
  });
  const data = await handleResponse<TokenResponse>(res);
  if (typeof window !== "undefined" && data.access_token) {
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
    if (data.refresh_token)
      localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
  }
  return data;
}

export async function refreshTokens(): Promise<TokenResponse | null> {
  const r =
    typeof window !== "undefined"
      ? localStorage.getItem(REFRESH_TOKEN_KEY)
      : null;
  if (!r) return null;
  const res = await fetch(`${getApiBase()}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: r }),
  });
  if (!res.ok) return null;
  const data = await res.json();
  if (typeof window !== "undefined" && data.access_token) {
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
    if (data.refresh_token)
      localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
  }
  return data;
}

export async function getMe(): Promise<User> {
  const res = await fetchWithAuth(`${getApiBase()}/auth/me`, {});
  return handleResponse<User>(res);
}
