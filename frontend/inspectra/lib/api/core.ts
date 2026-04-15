/**
 * Shared API helpers: base URL, auth headers, response handling, session keys.
 * Used by auth, organizations, users (and future feature modules).
 */

const DEFAULT_API_PORT = "8080";

export function getApiBase(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl) return envUrl.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    if (process.env.NODE_ENV === "development") {
      return `${window.location.origin}/api`;
    }
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:${DEFAULT_API_PORT}`;
  }
  if (process.env.NODE_ENV === "development") {
    return "http://127.0.0.1:8080";
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

export function clearSessionAndRedirect(
  redirect?: (url: string) => void
): void {
  logout();
  if (typeof window !== "undefined") {
    const doRedirect =
      redirect ??
      ((url: string) => {
        window.location.href = url;
      });
    doRedirect("/login");
  }
}

type PydanticErrorItem = {
  loc?: unknown;
  msg?: unknown;
  type?: unknown;
  ctx?: unknown;
  input?: unknown;
};

function formatValidationErrors(detail: unknown): string | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;

  const items = detail as PydanticErrorItem[];

  for (const it of items) {
    const loc = Array.isArray(it.loc) ? it.loc : [];
    const msg = typeof it.msg === "string" ? it.msg : "";
    const type = typeof it.type === "string" ? it.type : "";
    const ctx = typeof it.ctx === "object" && it.ctx !== null ? it.ctx : null;

    if (
      loc.length >= 2 &&
      loc[0] === "body" &&
      loc[1] === "name" &&
      (type === "string_pattern_mismatch" ||
        msg.toLowerCase().includes("pattern"))
    ) {
      const pattern =
        ctx && "pattern" in ctx && typeof (ctx as any).pattern === "string"
          ? (ctx as any).pattern
          : "";
      if (pattern.includes("^\\S+$") || pattern.includes("^\\\\S+$")) {
        return "Name cannot contain spaces.";
      }
      return "Invalid name.";
    }

    if (type === "too_short" && msg.toLowerCase().includes("at least")) {
      return msg;
    }
  }

  const lines = items
    .map((it) => {
      const msg = typeof it.msg === "string" ? it.msg : null;
      const loc = Array.isArray(it.loc)
        ? it.loc.filter((x) => typeof x === "string")
        : [];
      const field =
        loc.length >= 2 && loc[0] === "body" ? String(loc[1]) : loc.at(-1);
      if (!msg) return null;
      return field ? `${field}: ${msg}` : msg;
    })
    .filter((x): x is string => x != null);

  if (lines.length === 0) return "Invalid request. Please check your input.";
  return lines.slice(0, 3).join("\n");
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
        else {
          const formatted = formatValidationErrors(raw);
          if (formatted) detail = formatted;
          else if (typeof raw === "object" && typeof raw.error === "string")
            detail = raw.error;
          else if (typeof raw === "object" && typeof raw.message === "string")
            detail = raw.message;
          else detail = JSON.stringify(raw);
        }
      }
    } catch {
      if (text) detail = text;
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
