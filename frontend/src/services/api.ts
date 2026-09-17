import type { GradingJobCreated, GradingJobResult, GradingJobStatus } from "@/types/grading";

const API_BASE = "/api/v1";

/**
 * No barem is passed: every student in the file declares their own `ma_de`,
 * and the backend matches each one against the library.
 */
export async function createGradingJob(inputFile: File): Promise<GradingJobCreated> {
  const formData = new FormData();
  formData.append("input_file", inputFile);

  const res = await fetch(`${API_BASE}/grading/jobs`, {
    method: "POST",
    body: formData,
  });
  // Surface FastAPI's `detail`: the rejections here are all actionable —
  // which students are missing `ma_de`, which exam codes the library has no
  // rubric for — and a bare status code throws that away.
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body — keep the status code.
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getGradingJob(jobId: string): Promise<GradingJobStatus> {
  const res = await fetch(`${API_BASE}/grading/jobs/${jobId}`);
  if (!res.ok) throw new Error(`get job failed: ${res.status}`);
  return res.json();
}

export async function getGradingJobResult(jobId: string): Promise<GradingJobResult> {
  const res = await fetch(`${API_BASE}/grading/jobs/${jobId}/result`);
  if (!res.ok) throw new Error(`get job result failed: ${res.status}`);
  return res.json();
}

export async function listGradingJobs(): Promise<GradingJobStatus[]> {
  const res = await fetch(`${API_BASE}/grading/jobs`);
  if (!res.ok) throw new Error(`list jobs failed: ${res.status}`);
  return res.json();
}
