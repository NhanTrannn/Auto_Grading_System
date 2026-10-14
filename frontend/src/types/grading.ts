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
  created_at: string;
}

export interface StudentSummary {
  hs: string;
  score: number;
  max_score: number;
  wrong: string[];
}

/** A teacher's score change, applied by the backend on top of the AI verdict. */
export interface TeacherOverrideInfo {
  new_score: number;
  old_score: number | null;
  note: string | null;
  created_by: string | null;
  created_at: string | null;
}

export interface CriterionResult {
  criterion_id: string;
  score: number;
  max_score: number;
  status: string;
  llm_reasoning?: string;
  /** Present only when overridden: what the AI gave before the teacher changed it. */
  ai_score?: number;
  teacher_override?: TeacherOverrideInfo;
  [key: string]: unknown;
}

/**
 * A group of criteria whose combined score is decided as a unit rather than by
 * summing members — either `all_or_nothing` or, when
 * `group_decision_source === "llm"`, by the LLM reading the group's
 * `grader_note` (see `group_llm_decided` in pipeline.py).
 */
export interface GroupOverride {
  group_id: string;
  members: string[];
  group_score: number;
  group_max_score: number;
  group_decision_source?: string;
  group_score_reasoning?: string;
}

export interface GradingResultSample {
  sample_id: string;
  question_number: number;
  score: number;
  max_score: number;
  status: string;
  criterion_results?: CriterionResult[];
  group_overrides?: GroupOverride[];
  [key: string]: unknown;
}

export interface GradingJobResult {
  grading_results: GradingResultSample[];
  student_summary: StudentSummary[];
}
