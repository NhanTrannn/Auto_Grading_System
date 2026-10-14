import type { GradingJobResult } from "@/types/grading";
import type {
  JobEdits,
  JobLog,
  OcrResultsFile,
  StorageCleanup,
  StorageSummary,
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

/**
 * Step 1: unpack the archive(s) and report what's inside them.
 *
 * The blank-exam archive is optional now. ROIs are detected on each student's
 * own paper instead of being measured once on a clean template and warped, so
 * the template no longer takes part in cropping at all — it only serves as a
 * tidier backdrop while mapping regions.
 */
export async function createUpload(
  studentsZip: File,
  templateZip?: File | null,
): Promise<UploadInventory> {
  const formData = new FormData();
  formData.append("students_zip", studentsZip);
  if (templateZip) formData.append("template_zip", templateZip);

  const res = await fetch(`${API_BASE}/uploads`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

/**
 * URL of the page the ROI editor draws its boxes over.
 *
 * Falls back to the first student's paper when no blank exam was uploaded —
 * the layout is the same on every copy, and boxes are stored as page-relative
 * fractions, so which copy it is does not matter.
 */
export function referencePageUrl(uploadId: string, page: number, maDe?: string): string {
  const query = maDe ? `?ma_de=${encodeURIComponent(maDe)}` : "";
  return `${API_BASE}/uploads/${uploadId}/reference/${page}${query}`;
}

/**
 * Step 2: run one or more exam codes from a previous upload.
 *
 * By default no barem is passed — the server looks one up per code in the
 * library by `ma_de`. A group can instead set `baremId` to pick a specific
 * library barem directly, skipping that ma_de lookup entirely (the barem
 * doesn't need to declare a matching, or any, `ma_de` of its own — the server
 * re-tags it under the hood). Each code carries its own regions, because two
 * codes rarely put their answers in the same place on the page.
 */
export async function createPipelineJob(input: {
  uploadId: string;
  groups: { maDe: string; rois: RoiConfigEntry[]; baremId?: string }[];
}): Promise<PipelineJobCreated> {
  const res = await fetch(`${API_BASE}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      upload_id: input.uploadId,
      groups: input.groups.map((g) => ({
        ma_de: g.maDe,
        roi_config: { rois: g.rois },
        ...(g.baremId ? { barem_id: g.baremId } : {}),
      })),
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

// ── managing runs ───────────────────────────────────────────────────────────

/** Delete a run: its results in the DB and its directory on disk. */
export async function deletePipelineJob(jobId: string): Promise<{ freed_bytes: number }> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function getStorage(): Promise<StorageSummary> {
  const res = await fetch(`${API_BASE}/storage`);
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

/** Remove uploads no run uses (older than a day) and already-unpacked ZIPs. */
export async function cleanupStorage(): Promise<StorageCleanup> {
  const res = await fetch(`${API_BASE}/storage/cleanup`, { method: "POST" });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

/** Teacher fixes to OCR readings, `{hs_key: {cau_key: correction}}`. */
export async function getJobEdits(jobId: string): Promise<JobEdits> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/edits`);
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

/** Save what the student really wrote; an empty `text` clears the correction. */
export async function saveOcrCorrection(
  jobId: string,
  hsKey: string,
  cauKey: string,
  text: string,
  correctedBy?: string,
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/jobs/${jobId}/students/${encodeURIComponent(hsKey)}/regions/${encodeURIComponent(cauKey)}/ocr`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, corrected_by: correctedBy || null }),
    },
  );
  if (!res.ok) throw new Error(await readError(res));
}

/** Set one criterion's score by hand (posting the AI score back undoes it). */
export async function overrideCriterionScore(
  jobId: string,
  hsKey: string,
  criterionId: string,
  newScore: number,
  note?: string,
  createdBy?: string,
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/jobs/${jobId}/students/${encodeURIComponent(hsKey)}/criteria/${encodeURIComponent(criterionId)}/override`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_score: newScore, note: note || null, created_by: createdBy || null }),
    },
  );
  if (!res.ok) throw new Error(await readError(res));
}

/** URL of one student's cropped answer region, for the review screen. */
export function cropUrl(jobId: string, hsKey: string, cauKey: string): string {
  return `${API_BASE}/jobs/${jobId}/crops/${encodeURIComponent(hsKey)}/${encodeURIComponent(cauKey)}`;
}
