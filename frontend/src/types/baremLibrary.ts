import type { ExamRubric } from "./barem";

/** Listing row — the server omits `content` here, a rubric is tens of KB. */
export interface BaremSummary {
  barem_id: string;
  name: string;
  ma_de: string | null;
  subject: string | null;
  total_score: number | null;
  question_count: number;
  created_at: string;
  updated_at: string;
}

export interface BaremDetail extends BaremSummary {
  content: ExamRubric;
}
