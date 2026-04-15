export type RoiTool = "box" | "polygon";

export function closePolygon(points: number[][]): number[][] {
  if (!points || points.length === 0) return [];
  const first = points[0]!;
  const last = points[points.length - 1]!;
  if (first[0] === last[0] && first[1] === last[1]) return points;
  return [...points, [first[0]!, first[1]!]];
}

export function metricsFromPoints(
  points: number[][]
): { left: number; top: number; width: number; height: number } | null {
  if (!points || points.length < 2) return null;
  const xs = points.map((p) => p[0]).filter((x) => Number.isFinite(x));
  const ys = points.map((p) => p[1]).filter((y) => Number.isFinite(y));
  if (xs.length === 0 || ys.length === 0) return null;
  const left = Math.min(...xs);
  const right = Math.max(...xs);
  const top = Math.min(...ys);
  const bottom = Math.max(...ys);
  const width = right - left;
  const height = bottom - top;
  if (width < 2 || height < 2) return null;
  return { left, top, width, height };
}

export function newDraftRoiClientId(): string {
  if (typeof globalThis !== "undefined" && globalThis.crypto) {
    const c = globalThis.crypto;
    if (typeof c.randomUUID === "function") return c.randomUUID();
    if (typeof c.getRandomValues === "function") {
      const bytes = new Uint8Array(16);
      c.getRandomValues(bytes);
      bytes[6] = (bytes[6]! & 0x0f) | 0x40;
      bytes[8] = (bytes[8]! & 0x3f) | 0x80;
      const hex = [...bytes]
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
  }
  return `draft-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

