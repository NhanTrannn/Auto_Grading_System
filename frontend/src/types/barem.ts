/**
 * Barem (rubric) schema — mirrors EXACTLY what backend/pipeline.py reads.
 *
 * Source of truth: backend/structure/structure_parem.txt, kept in sync with
 * pipeline.py's load_barem() / flatten_criteria() / validate_barem().
 * When a barem-facing field changes in pipeline.py, update this file and
 * structure_parem.txt in the same change.
 *
 * Deliberately NOT modelled here (fields pipeline.py never reads): the
 * `mc_total` / `essay_total` / `student_index_note` exam fields, and the
 * `gradable` / `accepted_outputs` / `accepted_special_answers` /
 * `combined_allowed` / `scoring_note` criterion fields. They existed in the
 * upstream rubric-builder's schema but no grading code ever looks at them, so
 * carrying them would let an author think they affect grading when they don't.
 */

/**
 * KNOWN_QUESTION_TYPES in pipeline.py — exactly these four, nothing else.
 * infer_criterion_grading_mode() dispatches on this string directly; any other
 * value (including "" or a missing field) falls through to a teacher-review
 * branch where NO heuristic grader runs at all.
 */
export const QUESTION_TYPES = ["matching", "logical", "table", "visual"] as const;

export type QuestionType = (typeof QUESTION_TYPES)[number];

/**
 * A wrapper criterion (one that has sub_criteria) is never graded directly, so
 * it may carry a non-gradable marker like "multi_type" purely for readers —
 * see T15B in the real sample_parem.json. Leaf criteria must use QuestionType.
 */
export type WrapperQuestionType = QuestionType | "multi_type" | string;

export interface AnswerSlot {
  slot_id: string;
  /** Table slots only — ties the answer slot to one cell of a table_slot grid. */
  cell_id?: string;
  row_id?: string;
  col_id?: string;
}

/** One cell of the flat `table_slot` list — every cell, header cells included. */
export interface TableSlotCell {
  /** "{row_id}{col_id}" concatenated, no separator. E.g. "R2C1". */
  cell_id: string;
  /**
   * "printed"      — text is pre-printed on the exam paper (column headers,
   *                  teacher-fixed values); `text` below IS the content.
   * "student_text" — the student fills this in; `text` stays "" and the real
   *                  content is looked up by cell_id from the OCR'd answer.
   */
  source: "printed" | "student_text";
  row_id: string;
  col_id: string;
  /** Only meaningful when source === "printed". */
  text: string;
}

/**
 * Flat table format — the ONLY shape `_attach_table_slots()` understands.
 * (The upstream builder emitted nested `columns[]` + `rows[].cells[]`, which
 * pipeline.py silently ignores; see migrate.ts for the conversion.)
 */
export interface QuestionTable {
  table_id: string;
  table_slot: TableSlotCell[];
}

export interface QuestionPart {
  /** "main" | "main_S1" | "a" | "b" | "c" … — must match a criterion's part_label. */
  part_label: string;
  text: string;
  tables: QuestionTable[];
  answer_slots: AnswerSlot[];
  /** Free-form note for humans; does not affect grading. */
  note?: string;
}

export interface ConditionalOutput {
  /** Evaluated by safe_eval_condition() with a single variable named `value`. */
  condition: string;
  expected_outputs: string[];
  expected_output_tokens?: string[];
}

/**
 * MANDATORY whenever a criterion has `conditional_outputs` — pipeline.py has no
 * implicit fallback. Without it grade_expected_output_criterion() short-circuits
 * to `matched: false` without ever resolving a branch.
 */
export type ConditionSource =
  | {
      /** Read straight off the sample (ground-truth index from the exam roster). */
      type: "sample_field";
      /** Uses key "field" — NOT "slot_ids". */
      field: string;
    }
  | {
      /** Read what the student actually wrote in another slot. */
      type: "self_reported";
      /**
       * Uses key "slot_ids" (a list) — NOT "field". Writing "field" here
       * silently resolves to an empty slot list and falls back to reading the
       * student's entire raw answer; this exact bug shipped once in T8_main_s2.
       */
      slot_ids: string[];
    };

export interface PartialCreditRule {
  /** "count_correct_tokens" | "count_wrong_tokens" | "date_partial_match" | "position_tolerance" */
  type: string;
  partial_score: number;
  /** Python-ish expression run through safe_eval_condition(). */
  condition: string;
}

/** `expected_value` for question_type "logical" — exactly these two keys. */
export interface LogicalExpectedValue {
  /**
   * Flat list of strings, each scanned independently against the student's
   * answer. Only list what the student must actually type — a function
   * signature the exam pre-printed will always report as "missing".
   */
  keywords?: string[];
  /** Reference solution shown to the LLM as-is; never scanned for matched/missing. */
  sample_solution?: string;
}

export interface Criterion {
  criterion_id: string;
  /** Required on every LEAF criterion (own or inherited from the parent item). */
  question_type?: WrapperQuestionType;
  part_label?: string;
  /** Wrapper-level label for a question's sub-part (a/b/c); mirrors part_label. */
  sub_label?: string;
  content?: string;
  /**
   * Max points. `null` is only valid inside an all_or_nothing group (the group's
   * own `score` covers it) — validate_barem() errors otherwise.
   */
  score?: number | null;
  /**
   * Proportional share used instead of `score` inside a group. For a
   * non-all_or_nothing parent, flatten_criteria() derives
   * score = parent.score * (weight / sum_of_sibling_weights).
   */
  weight?: number;
  slot_ids?: string[];
  grader_note?: string;
  /** Group scores once, only when every member is correct. */
  all_or_nothing?: boolean;
  sub_criteria?: Criterion[];

  // ── question_type: "matching" ──────────────────────────────────────────
  /**
   * Accepted answers, compared byte-exactly. A literal that names a key of the
   * sample (e.g. "student_index") resolves to that field's real value.
   */
  expected_outputs?: string[];
  /** Positional tokens for partial credit; never yields status "correct" alone. */
  expected_output_tokens?: string[];
  /** A single rule, or tiered rules where the highest matching tier wins. */
  partial_credit_rule?: PartialCreditRule | PartialCreditRule[];
  conditional_outputs?: ConditionalOutput[];
  condition_source?: ConditionSource;

  // ── question_type: "logical" (and "table", where it is a free-form hint) ──
  expected_value?: LogicalExpectedValue | Record<string, unknown> | string | number | null;

  // ── question_type: "table" ────────────────────────────────────────────
  /** One criterion grades exactly ONE cell. */
  row_id?: string;
  col_id?: string;
}

export interface RubricQuestion {
  /** Human-readable only — pipeline.py never joins on this. */
  sample_id: string;
  /** The REAL join key: load_barem() builds barem_dict[question_number]. */
  question_number: number;
  question: {
    text: string;
    parts: QuestionPart[];
  };
  /** Optional, for readers only — validate_barem() ignores it. */
  score?: number;
  grading_rule: Criterion[];
}

export interface ExamRubric {
  ma_de: string;
  /** Injected into every criterion and shown to the LLM via _grader_intro(). */
  subject: string;
  total_score: number;
  teacher_barem: RubricQuestion[];
}

// ── Validation ──────────────────────────────────────────────────────────

export type IssueLevel = "error" | "warning";

export interface ValidationIssue {
  level: IssueLevel;
  message: string;
  /** question_number of the offending question, when the issue is scoped to one. */
  questionNumber?: number;
  criterionId?: string;
}

export interface ValidationReport {
  valid: boolean;
  issues: ValidationIssue[];
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  computedTotal: number;
}

/**
 * A criterion after flatten_criteria() — the shape graders actually see, with
 * inherited fields resolved and group markers attached.
 */
export interface FlatCriterion extends Criterion {
  group_id?: string;
  group_all_or_nothing?: boolean;
  group_llm_decided?: boolean;
  group_max_score?: number;
}

/** Presets offered when adding a question — each maps to a real QuestionType. */
export type QuestionPreset = "matching" | "logical" | "table" | "visual";
