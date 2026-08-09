export type JobStatus = "pending" | "running" | "done" | "failed";

export interface GradingJobCreated {
  job_id: string;
  status: JobStatus;
}

export interface GradingJobStatus {
  job_id: string;
  status: JobStatus;
  error: string | null;
  result_path: string | null;
}
