import type { ExamRubric } from "@/types/barem";
import type { BaremDetail, BaremSummary } from "@/types/baremLibrary";

const API_BASE = "/api/v1/barems";

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    return JSON.stringify(body);
  } catch {
    return `HTTP ${res.status}`;
  }
}

export async function listBarems(): Promise<BaremSummary[]> {
  const res = await fetch(API_BASE);
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function getBarem(baremId: string): Promise<BaremDetail> {
  const res = await fetch(`${API_BASE}/${baremId}`);
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

/** Push the in-browser builder's current rubric into the library. */
export async function createBarem(name: string, content: ExamRubric): Promise<BaremDetail> {
  const res = await fetch(API_BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, content }),
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function uploadBarem(file: File): Promise<BaremDetail> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function updateBarem(
  baremId: string,
  patch: { name?: string; content?: ExamRubric },
): Promise<BaremDetail> {
  const res = await fetch(`${API_BASE}/${baremId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function deleteBarem(baremId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/${baremId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await readError(res));
}
