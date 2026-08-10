import type {
  AlignResult,
  OcrHealth,
  OcrResult,
  OcrTaskType,
  RoiPageResult,
} from "@/types/ocr";

/** Proxied by vite.config.ts to the standalone OCR service on port 8081. */
const OCR_BASE = "/ocr";

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    return JSON.stringify(body);
  } catch {
    return `HTTP ${res.status}`;
  }
}

export async function getOcrHealth(): Promise<OcrHealth> {
  const res = await fetch(`${OCR_BASE}/health`);
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function detectRois(files: File[]): Promise<RoiPageResult[]> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));

  const res = await fetch(`${OCR_BASE}/module1/roi`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function alignImages(template: File, student: File): Promise<AlignResult> {
  const formData = new FormData();
  formData.append("template", template);
  formData.append("student", student);

  const res = await fetch(`${OCR_BASE}/module2/align`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function runOcr(
  image: File,
  taskType: OcrTaskType,
  nRows?: number,
  nCols?: number,
): Promise<OcrResult> {
  const formData = new FormData();
  formData.append("image", image);
  formData.append("task_type", taskType);
  if (taskType === "table") {
    formData.append("n_rows", String(nRows ?? 0));
    formData.append("n_cols", String(nCols ?? 0));
  }

  const res = await fetch(`${OCR_BASE}/module3/ocr`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}
