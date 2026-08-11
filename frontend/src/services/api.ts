import type { GradingJobCreated, GradingJobResult, GradingJobStatus } from "@/types/grading";

const API_BASE = "/api/v1";

/** The barem comes from the library by id; the backend writes its stored content out for the worker. */
export async function createGradingJob(
  inputFile: File,
  baremId: string,
): Promise<GradingJobCreated> {
  const formData = new FormData();
  formData.append("input_file", inputFile);
  formData.append("barem_id", baremId);

  const res = await fetch(`${API_BASE}/grading/jobs`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`create job failed: ${res.status}`);
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
