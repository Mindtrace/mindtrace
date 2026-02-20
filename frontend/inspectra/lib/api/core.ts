/**
 * Shared API helpers: base URL, auth headers, response handling, session keys.
 * Used by auth, organizations, users (and future feature modules).
 */

const DEFAULT_API_PORT = "8080";

export function getApiBase(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl) return envUrl.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:${DEFAULT_API_PORT}`;
  }
  return "http://localhost:8080";
}

export const ACCESS_TOKEN_KEY = "inspectra_token";
export const REFRESH_TOKEN_KEY = "inspectra_refresh_token";

export const SESSION_EXPIRED_MESSAGE =
  "Your session has expired. Please sign in again.";

export function isSessionOrAuthError(error: unknown): boolean {
  if (error instanceof Error) {
    const m = error.message.toLowerCase();
    return (
      m.includes("session has expired") ||
      m.includes("token") ||
      m.includes("unauthorized") ||
      m.includes("not authenticated") ||
      m.includes("invalid token")
    );
  }
  return false;
}

/** User-facing message for auth/session errors (no technical details). */
export function getSafeErrorMessage(error: unknown, fallback: string): string {
  if (isSessionOrAuthError(error)) return SESSION_EXPIRED_MESSAGE;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function getAuthHeaders(): HeadersInit {
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem(ACCESS_TOKEN_KEY)
      : null;
  const headers: HeadersInit = { "Content-Type": "application/json" };
  if (token)
    (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  return headers;
}

export function logout(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }
}

export function clearSessionAndRedirect(): void {
  logout();
  if (typeof window !== "undefined") {
    window.location.href = "/login";
  }
}

export async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    let detail: string = res.statusText;
    try {
      const j = JSON.parse(text);
      const raw = j.detail;
      if (raw != null) {
        if (typeof raw === "string") detail = raw;
        else if (typeof raw === "object" && typeof raw.error === "string")
          detail = raw.error;
        else if (typeof raw === "object" && typeof raw.message === "string")
          detail = raw.message;
        else detail = JSON.stringify(raw);
      }
    } catch {
      if (text) detail = text;
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
