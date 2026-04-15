import { NextRequest, NextResponse } from "next/server";

/**
 * Forwards requests to the on-prem camera service from the Next.js server so the
 * browser only talks same-origin.
 *
 * Enabled when NODE_ENV is development, or when CAMERA_SERVICE_PROXY=1 (server)
 * together with NEXT_PUBLIC_CAMERA_SERVICE_PROXY=1 (client uses this route).
 */

function isProxyEnabled(): boolean {
  return (
    process.env.NODE_ENV === "development" ||
    process.env.CAMERA_SERVICE_PROXY === "1"
  );
}

function isAllowedTargetHost(hostname: string): boolean {
  if (hostname === "localhost" || hostname === "127.0.0.1") return true;
  if (/^10\./.test(hostname)) return true;
  if (/^192\.168\./.test(hostname)) return true;
  if (/^172\.(1[6-9]|2\d|3[0-1])\./.test(hostname)) return true;
  if (hostname === "host.docker.internal") return true;
  return false;
}

type ForwardBody = {
  baseUrl: string;
  path: string;
  method?: string;
  body?: Record<string, unknown>;
};

export async function POST(req: NextRequest) {
  if (!isProxyEnabled()) {
    return NextResponse.json(
      { error: "Camera forward proxy is disabled." },
      { status: 403 }
    );
  }

  let payload: ForwardBody;
  try {
    payload = (await req.json()) as ForwardBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const { baseUrl, path, method = "POST", body = {} } = payload;
  if (typeof baseUrl !== "string" || typeof path !== "string") {
    return NextResponse.json(
      { error: "baseUrl and path are required." },
      { status: 400 }
    );
  }

  let target: URL;
  try {
    const normalizedBase = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
    const rel = path.startsWith("/") ? path.slice(1) : path;
    target = new URL(rel, normalizedBase);
  } catch {
    return NextResponse.json({ error: "Invalid baseUrl or path." }, { status: 400 });
  }

  if (target.protocol !== "http:" && target.protocol !== "https:") {
    return NextResponse.json({ error: "Invalid target protocol." }, { status: 400 });
  }

  if (!isAllowedTargetHost(target.hostname)) {
    return NextResponse.json(
      { error: "Target host is not allowed for forwarding." },
      { status: 403 }
    );
  }

  const m = method.toUpperCase();
  const sendJsonBody = m === "POST" || m === "PUT" || m === "PATCH";

  const upstream = await fetch(target.toString(), {
    method: m,
    headers: {
      Accept: "application/json",
      ...(sendJsonBody ? { "Content-Type": "application/json" } : {}),
    },
    body: sendJsonBody ? JSON.stringify(body ?? {}) : undefined,
  });

  const text = await upstream.text();
  const ct = upstream.headers.get("content-type") || "application/json";
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "Content-Type": ct },
  });
}
