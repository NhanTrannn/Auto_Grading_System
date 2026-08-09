import type { GradingJobCreated, GradingJobStatus } from "@/types/grading";

const API_BASE = "/api/v1";

export async function createGradingJob(
  inputFile: File,
  baremFile: File,
): Promise<GradingJobCreated> {
  const formData = new FormData();
  formData.append("input_file", inputFile);
  formData.append("barem_file", baremFile);

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
