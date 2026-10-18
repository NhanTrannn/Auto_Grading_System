/**
 * Build real barem questions from the assistant's draft format.
 *
 * The assistant (backend/app/services/barem_assistant.py) never writes the
 * full schema — slot ids, criterion ids and part wiring are exactly what an
 * LLM gets subtly wrong — so it answers with numbers, parts, criteria, scores
 * and answers, and this module turns that into `RubricQuestion`s using the
 * same factory helpers the editor's own "add question" button uses.
 */
import type { Criterion, ExamRubric, PartialCreditRule, QuestionPart, RubricQuestion } from "@/types/barem";

import { collectCriterionIds } from "../criterionTree";
import { deepClone, makePart } from "../factory";
import { flattenCriteria, questionTotal } from "../flatten";

export type DraftType = "matching" | "logical" | "visual";

export interface DraftCriterion {
  part?: string;
  type: DraftType;
  score?: number;
  content?: string;
  grader_note?: string;
  answers?: string[];
  tokens?: string[];
  partial?: { min_correct?: number; score?: number; raw_rule?: PartialCreditRule }[];
  keywords?: string[];
  sample_solution?: string;
}

export interface DraftQuestion {
  number: number;
  text?: string;
  parts?: { label?: string; text?: string }[];
  criteria?: DraftCriterion[];
}

export interface AssistantReply {
  reply: string;
  meta: { ma_de?: string; subject?: string; total_score?: number } | null;
  questions: DraftQuestion[];
  remove_questions: number[];
  confidence_notes: string[];
}

function walk(criteria: Criterion[]): Criterion[] {
  return criteria.flatMap((c) => [c, ...walk(c.sub_criteria ?? [])]);
}

/**
 * Questions the assistant may not rewrite: printed tables and per-student
 * (`conditional_outputs`) answers have no place in the draft format, so a
 * rewrite would silently drop them. Mirrors `locked_questions()` server-side.
 */
export function isLocked(question: RubricQuestion | undefined): boolean {
  if (!question) return false;
  const hasTable = question.question.parts.some((part) => part.tables.length > 0);
  const hasConditional = walk(question.grading_rule).some((c) => c.conditional_outputs?.length);
  return hasTable || hasConditional;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v) => typeof v === "string" && v !== "").map(String) : [];
}

function partialRules(partial: DraftCriterion["partial"]): PartialCreditRule | PartialCreditRule[] | undefined {
  const rules: PartialCreditRule[] = [];
  for (const item of partial ?? []) {
    if (item.raw_rule) rules.push(item.raw_rule);
    else if (typeof item.min_correct === "number" && typeof item.score === "number") {
      // safe_eval_condition (pipeline.py) accepts comparisons on this variable.
      rules.push({
        type: "count_correct_tokens",
        partial_score: item.score,
        condition: `correct_token_count >= ${item.min_correct}`,
      });
    }
  }
  // One rule stays a bare object — the shape every hand-written barem uses.
  if (rules.length === 0) return undefined;
  return rules.length === 1 ? rules[0] : rules;
}

/** `T3`, `T3_1`, `T3_2`… never `uniqueCriterionId`'s `T3`→`T4`, which reads as question 4's. */
function freshId(base: string, taken: Set<string>): string {
  let id = base;
  for (let n = 2; taken.has(id); n += 1) id = `${base}_${n}`;
  taken.add(id);
  return id;
}

export function questionFromDraft(draft: DraftQuestion, taken: Set<string>): RubricQuestion {
  const number = draft.number;
  const sampleId = `cau_${number}_001`;

  const seen = new Set<string>();
  const parts: QuestionPart[] = [];
  for (const part of draft.parts?.length ? draft.parts : [{ label: "main" }]) {
    const label = (part.label ?? "").trim().toLowerCase() || "main";
    if (seen.has(label)) continue;
    seen.add(label);
    parts.push(makePart(sampleId, label, part.text ?? ""));
  }

  const criteriaDrafts = draft.criteria ?? [];
  const grading_rule: Criterion[] = criteriaDrafts.map((c, index) => {
    const label = (c.part ?? "").trim().toLowerCase();
    const part = parts.find((p) => p.part_label === label) ?? parts[0];
    const base = criteriaDrafts.length === 1 ? `T${number}` : `T${number}_${index + 1}`;
    const criterion: Criterion = {
      criterion_id: freshId(base, taken),
      question_type: c.type,
      part_label: part.part_label,
      slot_ids: part.answer_slots.map((slot) => slot.slot_id),
      content: c.content ?? "",
      score: typeof c.score === "number" ? c.score : 0,
    };
    if (c.grader_note) criterion.grader_note = c.grader_note;

    if (c.type === "matching") {
      criterion.expected_outputs = strings(c.answers);
      criterion.expected_output_tokens = strings(c.tokens);
      const rules = partialRules(c.partial);
      if (rules) criterion.partial_credit_rule = rules;
    } else if (c.type === "logical") {
      criterion.expected_value = {
        keywords: strings(c.keywords),
        sample_solution: c.sample_solution ?? "",
      };
    }
    return criterion;
  });

  return {
    sample_id: sampleId,
    question_number: number,
    question: { text: draft.text ?? "", parts },
    grading_rule,
  };
}

// ── proposal → changes ──────────────────────────────────────────────────────

export type ChangeKind = "add" | "replace" | "remove" | "locked" | "meta";

export interface ProposedChange {
  key: string;
  kind: ChangeKind;
  questionNumber?: number;
  label: string;
  detail: string;
}

function draftTotal(draft: DraftQuestion): number {
  return (draft.criteria ?? []).reduce((sum, c) => sum + (typeof c.score === "number" ? c.score : 0), 0);
}

export function describeProposal(exam: ExamRubric, reply: AssistantReply): ProposedChange[] {
  const byNumber = new Map(exam.teacher_barem.map((q) => [q.question_number, q]));
  const changes: ProposedChange[] = [];

  if (reply.meta && Object.values(reply.meta).some((v) => v !== undefined && v !== null && v !== "")) {
    const bits = [
      reply.meta.ma_de ? `mã đề ${reply.meta.ma_de}` : null,
      reply.meta.subject ? `môn "${reply.meta.subject}"` : null,
      typeof reply.meta.total_score === "number" ? `tổng ${reply.meta.total_score}đ` : null,
    ].filter(Boolean);
    if (bits.length) changes.push({ key: "meta", kind: "meta", label: "Thông tin đề", detail: bits.join(", ") });
  }

  for (const draft of reply.questions) {
    const existing = byNumber.get(draft.number);
    const count = draft.criteria?.length ?? 0;
    const total = draftTotal(draft).toFixed(2);
    if (isLocked(existing)) {
      changes.push({
        key: `q${draft.number}`,
        kind: "locked",
        questionNumber: draft.number,
        label: `Câu ${draft.number}`,
        detail: "có bảng / đáp án theo STT — trợ lý không được sửa, hãy soạn tay",
      });
    } else if (existing) {
      const before = questionTotal(flattenCriteria(existing)).toFixed(2);
      changes.push({
        key: `q${draft.number}`,
        kind: "replace",
        questionNumber: draft.number,
        label: `Sửa câu ${draft.number}`,
        detail: `${count} tiêu chí · ${before}đ → ${total}đ`,
      });
    } else {
      changes.push({
        key: `q${draft.number}`,
        kind: "add",
        questionNumber: draft.number,
        label: `Thêm câu ${draft.number}`,
        detail: `${count} tiêu chí · ${total}đ`,
      });
    }
  }

  for (const number of reply.remove_questions) {
    if (!byNumber.has(number)) continue;
    changes.push({
      key: `rm${number}`,
      kind: isLocked(byNumber.get(number)) ? "locked" : "remove",
      questionNumber: number,
      label: `Xoá câu ${number}`,
      detail: isLocked(byNumber.get(number)) ? "câu bị khoá — không xoá" : "",
    });
  }
  return changes;
}

/**
 * The exam after applying the selected changes. Pure — the caller hands the
 * result to `useBaremDraft.replaceExam`, so the whole proposal is one undo step.
 */
export function applyProposal(exam: ExamRubric, reply: AssistantReply, selected: Set<string>): ExamRubric {
  const next = deepClone(exam);
  const touched = new Set<number>(
    reply.questions.filter((q) => selected.has(`q${q.number}`)).map((q) => q.number),
  );
  const removing = new Set(reply.remove_questions.filter((n) => selected.has(`rm${n}`)));

  next.teacher_barem = next.teacher_barem.filter(
    (q) => isLocked(q) || (!touched.has(q.question_number) && !removing.has(q.question_number)),
  );
  // Ids of the questions being rewritten are free again; everyone else's aren't.
  const taken = collectCriterionIds(next.teacher_barem.flatMap((q) => q.grading_rule));

  for (const draft of reply.questions) {
    if (!selected.has(`q${draft.number}`)) continue;
    if (next.teacher_barem.some((q) => q.question_number === draft.number)) continue; // locked, kept
    next.teacher_barem.push(questionFromDraft(draft, taken));
  }
  next.teacher_barem.sort((a, b) => a.question_number - b.question_number);

  if (selected.has("meta") && reply.meta) {
    if (reply.meta.ma_de) next.ma_de = String(reply.meta.ma_de);
    if (reply.meta.subject) next.subject = reply.meta.subject;
    if (typeof reply.meta.total_score === "number") next.total_score = reply.meta.total_score;
  }
  return next;
}
