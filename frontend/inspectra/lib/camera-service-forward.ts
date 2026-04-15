export function normalizeCameraServiceUrl(baseUrl: string): string {
  const base = new URL(baseUrl);
  if (base.protocol !== "http:" && base.protocol !== "https:") {
    throw new Error(`Unsupported camera service protocol: ${base.protocol}`);
  }
  let s = base.toString();
  if (!s.endsWith("/")) s += "/";
  return s;
}

export function cameraServiceUsesForwardProxy(): boolean {
  if (typeof window === "undefined") return false;
  if (process.env.NEXT_PUBLIC_CAMERA_SERVICE_PROXY === "1") return true;
  return process.env.NODE_ENV === "development";
}

export async function cameraServiceFetchResponse(
  serviceUrl: string,
  path: string,
  options: {
    method?: "GET" | "POST";
    query?: Record<string, string>;
    jsonBody?: Record<string, unknown>;
  } = {}
): Promise<Response> {
  const method = options.method ?? "POST";
  const base = normalizeCameraServiceUrl(serviceUrl);
  const rel = path.startsWith("/") ? path.slice(1) : path;
  const url = new URL(rel, base);
  if (options.query) {
    for (const [k, v] of Object.entries(options.query)) {
      url.searchParams.set(k, v);
    }
  }
  const pathForProxy = url.pathname + url.search;

  if (cameraServiceUsesForwardProxy()) {
    return fetch(`${window.location.origin}/camera-forward`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        baseUrl: base,
        path: pathForProxy,
        method,
        ...(method === "GET"
          ? {}
          : { body: options.jsonBody ?? {} }),
      }),
    });
  }

  if (method === "GET") {
    return fetch(url.toString(), {
      method: "GET",
      headers: { Accept: "application/json" },
    });
  }

  return fetch(url.toString(), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      accept: "application/json",
    },
    body: JSON.stringify(options.jsonBody ?? {}),
  });
}
