import type { CompareResponse, HealthStatus } from "../types";

export async function checkHealth(): Promise<HealthStatus> {
  const r = await fetch("/api/health");
  if (!r.ok) throw new Error("Health check failed");
  return r.json() as Promise<HealthStatus>;
}

export async function compareDocuments(
  fileV1: File,
  fileV2: File,
): Promise<CompareResponse> {
  const form = new FormData();
  form.append("file_v1", fileV1);
  form.append("file_v2", fileV2);

  const r = await fetch("/api/compare", { method: "POST", body: form });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error((err as { detail: string }).detail || "Comparison failed");
  }
  return r.json() as Promise<CompareResponse>;
}

export function pdfUrl(sessionId: string, version: "v1" | "v2"): string {
  return `/api/pdf/${sessionId}/${version}`;
}
