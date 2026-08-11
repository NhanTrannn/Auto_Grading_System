import type { GradingJobResult } from "@/types/grading";
import type {
  JobLog,
  OcrResultsFile,
  PipelineJobCreated,
  PipelineJobStatus,
  RoiConfigEntry,
  UploadInventory,
} from "@/types/pipeline";

const API_BASE = "/api/v1/pipeline";

/** FastAPI puts validation/business errors in `detail`; surface them verbatim. */
async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    return JSON.stringify(body);
  } catch {
    return `HTTP ${res.status}`;
  }
}

/** Step 1: unpack both archives and report what's inside them. */
export async function createUpload(
  templateZip: File,
  studentsZip: File,
): Promise<UploadInventory> {
  const formData = new FormData();
  formData.append("template_zip", templateZip);
  formData.append("students_zip", studentsZip);

  const res = await fetch(`${API_BASE}/uploads`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

/** URL of one blank exam page — the ROI editor draws its boxes over this. */
export function templatePageUrl(uploadId: string, page: number): string {
  return `${API_BASE}/uploads/${uploadId}/template/${page}`;
}

/** Step 2: run exactly one exam code from a previous upload. */
export async function createPipelineJob(input: {
  uploadId: string;
  maDe: string;
  baremId: string;
  rois: RoiConfigEntry[];
}): Promise<PipelineJobCreated> {
  const res = await fetch(`${API_BASE}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      upload_id: input.uploadId,
      ma_de: input.maDe,
      barem_id: input.baremId,
      roi_config: { rois: input.rois },
      save_crops: true,
    }),
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function getPipelineJob(jobId: string): Promise<PipelineJobStatus> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`);
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function listPipelineJobs(): Promise<PipelineJobStatus[]> {
  const res = await fetch(`${API_BASE}/jobs`);
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function getPipelineJobResult(jobId: string): Promise<GradingJobResult> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/result`);
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

/** Intermediate Results-format JSON, readable as soon as OCR finishes. */
export async function getPipelineOcrResult(jobId: string): Promise<OcrResultsFile> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/ocr-result`);
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

/** Incremental log tail — feed `next_offset` back in as `offset`. */
export async function getPipelineJobLog(jobId: string, offset: number): Promise<JobLog> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/log?offset=${offset}`);
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

/** URL of one student's cropped answer region, for the review screen. */
export function cropUrl(jobId: string, hsKey: string, cauKey: string): string {
  return `${API_BASE}/jobs/${jobId}/crops/${encodeURIComponent(hsKey)}/${encodeURIComponent(cauKey)}`;
}
