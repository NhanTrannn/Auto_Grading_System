/**
 * Barem validation, in two layers.
 *
 * Layer 1 — a faithful port of pipeline.py's `validate_barem()`, run on the
 * FLATTENED criterion list. These are the checks that actually block or warn at
 * load time on the backend, so the builder must reproduce them exactly: an
 * author who sees a clean report here should never hit a load_barem() error.
 *
 * Layer 2 — structural checks the backend does NOT perform, catching the traps
 * documented in structure_parem.txt §11. validate_barem() only inspects the
 * scoring shape; it never looks inside `condition_source`, `table_slot` or
 * `expected_value`, so a malformed one loads silently and only surfaces later
 * as a wrong grade (e.g. `condition_source: {type: "self_reported", field: …}`
 * resolves to an empty slot list, then falls back to reading the student's
 * entire raw answer — a real bug that shipped in T8_main_s2). Catching those
 * here is the whole point of authoring in a builder rather than by hand.
 */
import type {
  Criterion,
  ExamRubric,
  FlatCriterion,
  RubricQuestion,
  ValidationIssue,
  ValidationReport,
} from "@/types/barem";
import { QUESTION_TYPES } from "@/types/barem";

import { conditionSyntaxError } from "./conditionEval";
import { flattenCriteria, questionTotal } from "./flatten";

const KNOWN_TYPES = new Set<string>(QUESTION_TYPES);
const LOGICAL_EXPECTED_VALUE_KEYS = new Set(["keywords", "sample_solution"]);

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Flag accepted-answer strings that can never be matched, or match by accident.
 *
 * `_check_exact_output_match` compares byte-for-byte with no normalisation of
 * any kind, so an entry that is empty, or that carries whitespace the author
 * cannot see, behaves nothing like it reads on screen. These stay warnings, not
 * errors: a trailing space is occasionally the real expected answer.
 */
function checkAnswerText(
  cid: string,
  field: string,
  answers: string[],
  at: { questionNumber: number; criterionId: string },
  issues: ValidationIssue[],
): void {
  const seen = new Set<string>();
  answers.forEach((answer, index) => {
    if (answer === "") {
      issues.push({
        level: "warning",
        ...at,
        message: `${cid}: ${field}[${index}] là chuỗi rỗng — chỉ khớp khi học sinh không viết gì cả.`,
      });
    } else if (answer !== answer.trim()) {
      issues.push({
        level: "warning",
        ...at,
        message: `${cid}: ${field}[${index}] = ${JSON.stringify(answer)} có khoảng trắng ở đầu/cuối. So khớp là byte-exact nên học sinh phải viết đúng cả khoảng trắng đó.`,
      });
    }
    if (seen.has(answer)) {
      issues.push({
        level: "warning",
        ...at,
        message: `${cid}: ${field}[${index}] trùng với một đáp án phía trên.`,
      });
    }
    seen.add(answer);
  });
}

// ── Layer 1: port of validate_barem() ────────────────────────────────────

function validateScoring(questions: RubricQuestion[], declaredTotal: number, issues: ValidationIssue[]): number {
  const seenCriterionIds = new Map<string, number>();
  const groups = new Map<string, FlatCriterion[]>();
  let computedTotal = 0;

  for (const question of questions) {
    const qNum = question.question_number;
    const flat = flattenCriteria(question);
    const groupsSeenInQuestion = new Set<string>();
    let qTotal = 0;

    for (const criterion of flat) {
      const cid = criterion.criterion_id;
      if (!cid) {
        issues.push({
          level: "error",
          questionNumber: qNum,
          message: `Câu ${qNum}: có tiêu chí thiếu criterion_id (content='${(criterion.content ?? "").slice(0, 50)}')`,
        });
        continue;
      }

      seenCriterionIds.set(cid, (seenCriterionIds.get(cid) ?? 0) + 1);

      const qtype = criterion.question_type;
      if (!qtype) {
        issues.push({
          level: "warning",
          questionNumber: qNum,
          criterionId: cid,
          message: `${cid}: thiếu question_type — tiêu chí sẽ không có heuristic grader nào chạy.`,
        });
      } else if (!KNOWN_TYPES.has(qtype)) {
        issues.push({
          level: "warning",
          questionNumber: qNum,
          criterionId: cid,
          message: `${cid}: question_type lạ '${qtype}' (chỉ chấp nhận ${QUESTION_TYPES.join(", ")}) — sẽ rơi vào nhánh teacher review.`,
        });
      }

      if (criterion.group_all_or_nothing) {
        const gid = criterion.group_id;
        if (!gid) {
          issues.push({
            level: "error",
            questionNumber: qNum,
            criterionId: cid,
            message: `${cid}: thuộc nhóm all_or_nothing nhưng tiêu chí cha thiếu criterion_id.`,
          });
          continue;
        }
        const members = groups.get(gid) ?? [];
        members.push(criterion);
        groups.set(gid, members);
        if (!groupsSeenInQuestion.has(gid)) {
          groupsSeenInQuestion.add(gid);
          qTotal += criterion.group_max_score || 0;
        }
      } else {
        const score = criterion.score;
        if (score === null || score === undefined) {
          issues.push({
            level: "error",
            questionNumber: qNum,
            criterionId: cid,
            message: `${cid}: score để trống nhưng KHÔNG thuộc nhóm all_or_nothing — không nơi nào bù điểm cho tiêu chí này. Ba cách sửa: nhập 'score' riêng cho nó; hoặc khai 'weight' để chia theo tỷ trọng từ điểm của tiêu chí cha; hoặc bật lại all_or_nothing ở tiêu chí cha.`,
          });
        } else if (score < 0) {
          issues.push({
            level: "error",
            questionNumber: qNum,
            criterionId: cid,
            message: `${cid}: score âm (${score}).`,
          });
        } else {
          qTotal += score;
        }
      }
    }

    computedTotal += qTotal;
  }

  for (const [cid, count] of seenCriterionIds) {
    if (count > 1) {
      issues.push({
        level: "error",
        criterionId: cid,
        message: `criterion_id trùng lặp: '${cid}' xuất hiện ${count} lần.`,
      });
    }
  }

  for (const [gid, members] of groups) {
    const maxScores = new Set(members.map((m) => m.group_max_score));
    if (maxScores.size > 1) {
      issues.push({
        level: "error",
        message: `Nhóm '${gid}': group_max_score không nhất quán giữa các thành viên (${[...maxScores].join(", ")}).`,
      });
    }
    if (members.length < 2) {
      issues.push({
        level: "warning",
        message: `Nhóm '${gid}': chỉ có 1 thành viên — all_or_nothing không có ý nghĩa.`,
      });
    }
  }

  const rounded = Math.round(computedTotal * 10000) / 10000;
  if (Math.abs(rounded - declaredTotal) > 0.01) {
    issues.push({
      level: "error",
      message: `Tổng điểm tính từ barem (${rounded}) khác total_score khai báo (${declaredTotal}).`,
    });
  }

  return rounded;
}

// ── Layer 2: structural checks the backend does not run ──────────────────

function validateCriterionShape(
  criterion: FlatCriterion,
  question: RubricQuestion,
  slotIds: Set<string>,
  partLabels: Set<string>,
  partTableCells: Map<string, Set<string>>,
  issues: ValidationIssue[],
): void {
  const qNum = question.question_number;
  const cid = criterion.criterion_id;
  const at = { questionNumber: qNum, criterionId: cid };

  if (criterion.part_label && !partLabels.has(criterion.part_label)) {
    issues.push({
      level: "error",
      ...at,
      message: `${cid}: part_label '${criterion.part_label}' không tồn tại trong question.parts.`,
    });
  }

  for (const slotId of criterion.slot_ids ?? []) {
    if (!slotIds.has(slotId)) {
      issues.push({
        level: "error",
        ...at,
        message: `${cid}: slot_ids tham chiếu slot không tồn tại '${slotId}'.`,
      });
    }
  }
  if (!criterion.slot_ids?.length) {
    issues.push({
      level: "warning",
      ...at,
      message: `${cid}: chưa khai slot_ids — pipeline phải lùi về lọc theo part_label, kém chính xác nếu part có nhiều slot.`,
    });
  }

  if (!criterion.content?.trim()) {
    issues.push({
      level: "warning",
      ...at,
      message: `${cid}: content để trống — đây là nguồn chính LLM dùng để hiểu tiêu chí.`,
    });
  }

  // conditional_outputs ⇒ condition_source is mandatory (no implicit fallback).
  if (criterion.conditional_outputs?.length) {
    const source = criterion.condition_source;
    if (!source) {
      issues.push({
        level: "error",
        ...at,
        message: `${cid}: có conditional_outputs nhưng thiếu condition_source — pipeline sẽ bỏ qua hoàn toàn việc chọn nhánh và chấm sai (matched=false).`,
      });
    } else if (source.type === "sample_field") {
      if (!("field" in source) || !source.field) {
        issues.push({
          level: "error",
          ...at,
          message: `${cid}: condition_source type='sample_field' phải khai key 'field'.`,
        });
      }
    } else if (source.type === "self_reported") {
      if (!("slot_ids" in source) || !source.slot_ids?.length) {
        issues.push({
          level: "error",
          ...at,
          message: `${cid}: condition_source type='self_reported' phải khai key 'slot_ids' (LIST) — dùng nhầm 'field' sẽ âm thầm đọc TOÀN BỘ bài làm thay vì đúng 1 slot.`,
        });
      } else {
        for (const slotId of source.slot_ids) {
          if (!slotIds.has(slotId)) {
            issues.push({
              level: "error",
              ...at,
              message: `${cid}: condition_source.slot_ids tham chiếu slot không tồn tại '${slotId}'.`,
            });
          }
        }
      }
    }

    criterion.conditional_outputs.forEach((branch, index) => {
      if (!branch.condition?.trim()) {
        issues.push({
          level: "error",
          ...at,
          message: `${cid}: conditional_outputs[${index}] thiếu 'condition'.`,
        });
      } else {
        if (!/\bvalue\b/.test(branch.condition)) {
          issues.push({
            level: "warning",
            ...at,
            message: `${cid}: conditional_outputs[${index}].condition không dùng biến 'value' — đây là biến DUY NHẤT safe_eval_condition() cung cấp (kể cả khi nguồn là student_index).`,
          });
        }
        const syntax = conditionSyntaxError(branch.condition);
        if (syntax) {
          issues.push({
            level: "error",
            ...at,
            message: `${cid}: conditional_outputs[${index}].condition không phân tích được (${syntax}) — khi chấm, safe_eval_condition() sẽ ném lỗi và nhánh này bị bỏ qua với MỌI học sinh, chỉ để lại một dòng cảnh báo trong log.`,
          });
        }
      }
      if (!branch.expected_outputs?.length) {
        issues.push({
          level: "error",
          ...at,
          message: `${cid}: conditional_outputs[${index}] thiếu 'expected_outputs' (list, không phải chuỗi đơn).`,
        });
      } else {
        checkAnswerText(cid, `conditional_outputs[${index}].expected_outputs`, branch.expected_outputs, at, issues);
      }
    });
  } else if (criterion.condition_source) {
    issues.push({
      level: "warning",
      ...at,
      message: `${cid}: khai condition_source nhưng không có conditional_outputs — field này sẽ không được dùng.`,
    });
  }

  switch (criterion.question_type) {
    case "matching": {
      const hasOutputs = Boolean(criterion.expected_outputs?.length);
      const hasConditional = Boolean(criterion.conditional_outputs?.length);
      if (!hasOutputs && !hasConditional) {
        issues.push({
          level: "error",
          ...at,
          message: `${cid}: question_type='matching' cần expected_outputs hoặc conditional_outputs.`,
        });
      }
      checkAnswerText(cid, "expected_outputs", criterion.expected_outputs ?? [], at, issues);

      // A token is a literal substring searched inside the student's answer, so
      // a token that appears in none of the accepted answers can never be
      // earned. In practice this catches one specific misreading: authoring the
      // whole list as a single "3, 5, 2, 9" entry, as if the field were a
      // comma-separated string rather than an array of separate tokens.
      const tokens = criterion.expected_output_tokens ?? [];
      const answers = criterion.expected_outputs ?? [];
      if (tokens.length && answers.length) {
        tokens.forEach((token, index) => {
          if (token && !answers.some((answer) => answer.includes(token))) {
            issues.push({
              level: "warning",
              ...at,
              message: `${cid}: expected_output_tokens[${index}] = ${JSON.stringify(token)} không xuất hiện trong bất kỳ expected_outputs nào — token được tìm nguyên văn như một đoạn con, nên token này không bao giờ khớp. Nếu bạn đang gõ nhiều token vào cùng một ô và ngăn bằng dấu phẩy/khoảng trắng thì hãy tách thành nhiều ô.`,
            });
          }
        });
      }

      const rules = criterion.partial_credit_rule
        ? Array.isArray(criterion.partial_credit_rule)
          ? criterion.partial_credit_rule
          : [criterion.partial_credit_rule]
        : [];
      if (rules.length && !criterion.expected_output_tokens?.length && !hasConditional) {
        issues.push({
          level: "warning",
          ...at,
          message: `${cid}: có partial_credit_rule nhưng expected_output_tokens rỗng — chấm bán phần theo token sẽ không có gì để so.`,
        });
      }
      rules.forEach((rule, index) => {
        if (!rule.condition?.trim()) {
          issues.push({
            level: "error",
            ...at,
            message: `${cid}: partial_credit_rule[${index}] thiếu 'condition'.`,
          });
        }
        const max = criterion.score ?? criterion.group_max_score ?? 0;
        if (max && rule.partial_score > max) {
          issues.push({
            level: "warning",
            ...at,
            message: `${cid}: partial_score (${rule.partial_score}) lớn hơn điểm tối đa của tiêu chí (${max}).`,
          });
        }
      });
      break;
    }

    case "logical": {
      const ev = criterion.expected_value;
      if (!isPlainObject(ev)) {
        issues.push({
          level: "error",
          ...at,
          message: `${cid}: question_type='logical' cần expected_value dạng object {keywords, sample_solution}.`,
        });
        break;
      }
      const extraKeys = Object.keys(ev).filter((key) => !LOGICAL_EXPECTED_VALUE_KEYS.has(key));
      if (extraKeys.length) {
        issues.push({
          level: "error",
          ...at,
          message: `${cid}: expected_value chỉ chấp nhận đúng 2 key 'keywords' và 'sample_solution'. Key thừa bị bỏ qua hoàn toàn khi chấm: ${extraKeys.join(", ")}.`,
        });
      }
      if (ev.keywords !== undefined && !Array.isArray(ev.keywords)) {
        issues.push({
          level: "error",
          ...at,
          message: `${cid}: expected_value.keywords phải là list phẳng các chuỗi.`,
        });
      }
      if (!Array.isArray(ev.keywords) || ev.keywords.length === 0) {
        issues.push({
          level: "warning",
          ...at,
          message: `${cid}: chưa có keywords nào — heuristic sẽ không đưa được gợi ý matched/missing cho LLM.`,
        });
      }
      break;
    }

    case "table": {
      if (!criterion.row_id || !criterion.col_id) {
        issues.push({
          level: "error",
          ...at,
          message: `${cid}: question_type='table' phải khai cả row_id và col_id — mỗi tiêu chí chấm đúng 1 ô.`,
        });
        break;
      }
      const cells = criterion.part_label ? partTableCells.get(criterion.part_label) : undefined;
      const cellId = `${criterion.row_id}${criterion.col_id}`;
      if (!cells || cells.size === 0) {
        issues.push({
          level: "error",
          ...at,
          message: `${cid}: chấm ô ${cellId} nhưng part '${criterion.part_label}' chưa khai bảng nào (tables[].table_slot).`,
        });
      } else if (!cells.has(cellId)) {
        issues.push({
          level: "error",
          ...at,
          message: `${cid}: ô ${cellId} không tồn tại trong table_slot của part '${criterion.part_label}'.`,
        });
      }
      if (criterion.expected_value === undefined || criterion.expected_value === null) {
        issues.push({
          level: "warning",
          ...at,
          message: `${cid}: expected_value trống — LLM sẽ không có ví dụ gợi ý nào cho ô này (đây chỉ là gợi ý, không phải đáp án so khớp cứng).`,
        });
      }
      break;
    }

    case "visual":
      // Vision LLM grades straight from the image using content + grader_note;
      // there are no expected_* fields to check.
      break;

    default:
      break;
  }
}

function validateTables(question: RubricQuestion, issues: ValidationIssue[]): Map<string, Set<string>> {
  const qNum = question.question_number;
  const partTableCells = new Map<string, Set<string>>();

  for (const part of question.question.parts) {
    const cells = new Set<string>();
    for (const table of part.tables ?? []) {
      const seen = new Set<string>();
      for (const cell of table.table_slot ?? []) {
        const expectedId = `${cell.row_id}${cell.col_id}`;
        if (cell.cell_id !== expectedId) {
          issues.push({
            level: "error",
            questionNumber: qNum,
            message: `Câu ${qNum} / bảng ${table.table_id}: cell_id '${cell.cell_id}' không khớp row_id+col_id ('${expectedId}').`,
          });
        }
        if (seen.has(cell.cell_id)) {
          issues.push({
            level: "error",
            questionNumber: qNum,
            message: `Câu ${qNum} / bảng ${table.table_id}: ô '${cell.cell_id}' bị khai trùng.`,
          });
        }
        seen.add(cell.cell_id);
        cells.add(cell.cell_id);

        if (cell.source === "printed" && !cell.text.trim()) {
          issues.push({
            level: "warning",
            questionNumber: qNum,
            message: `Câu ${qNum} / bảng ${table.table_id}: ô '${cell.cell_id}' là 'printed' nhưng text rỗng — LLM sẽ thấy một ô in sẵn trống rỗng.`,
          });
        }
        if (cell.source === "student_text" && cell.text.trim()) {
          issues.push({
            level: "warning",
            questionNumber: qNum,
            message: `Câu ${qNum} / bảng ${table.table_id}: ô '${cell.cell_id}' là 'student_text' nhưng có sẵn text — nội dung thật lấy từ bài làm, text ở đây bị bỏ qua.`,
          });
        }
      }
    }
    partTableCells.set(part.part_label, cells);
  }

  return partTableCells;
}

function validateStructure(questions: RubricQuestion[], issues: ValidationIssue[]): void {
  const seenQuestionNumbers = new Map<number, number>();
  const seenSampleIds = new Map<string, number>();
  const seenSlotIds = new Map<string, number>();

  for (const question of questions) {
    const qNum = question.question_number;
    seenQuestionNumbers.set(qNum, (seenQuestionNumbers.get(qNum) ?? 0) + 1);
    seenSampleIds.set(question.sample_id, (seenSampleIds.get(question.sample_id) ?? 0) + 1);

    if (!question.question.parts.length) {
      issues.push({
        level: "error",
        questionNumber: qNum,
        message: `Câu ${qNum}: chưa có part nào — không có vùng trả lời để chấm.`,
      });
    }
    if (!question.grading_rule.length) {
      issues.push({
        level: "error",
        questionNumber: qNum,
        message: `Câu ${qNum}: grading_rule rỗng — câu này sẽ không được chấm điểm.`,
      });
    }

    const partLabels = new Set<string>();
    const slotIds = new Set<string>();

    for (const part of question.question.parts) {
      if (!part.part_label.trim()) {
        issues.push({
          level: "error",
          questionNumber: qNum,
          message: `Câu ${qNum}: có part thiếu part_label.`,
        });
      }
      if (partLabels.has(part.part_label)) {
        issues.push({
          level: "error",
          questionNumber: qNum,
          message: `Câu ${qNum}: part_label '${part.part_label}' bị trùng.`,
        });
      }
      partLabels.add(part.part_label);

      if (!part.answer_slots.length) {
        issues.push({
          level: "warning",
          questionNumber: qNum,
          message: `Câu ${qNum} / part '${part.part_label}': chưa có answer_slot nào.`,
        });
      }
      for (const slot of part.answer_slots) {
        slotIds.add(slot.slot_id);
        seenSlotIds.set(slot.slot_id, (seenSlotIds.get(slot.slot_id) ?? 0) + 1);
      }
    }

    const partTableCells = validateTables(question, issues);

    for (const criterion of flattenCriteria(question)) {
      validateCriterionShape(criterion, question, slotIds, partLabels, partTableCells, issues);
    }

    // A part nobody grades is almost always an authoring slip.
    const gradedParts = new Set(flattenCriteria(question).map((c) => c.part_label));
    for (const label of partLabels) {
      if (!gradedParts.has(label)) {
        issues.push({
          level: "warning",
          questionNumber: qNum,
          message: `Câu ${qNum}: part '${label}' không có tiêu chí nào chấm.`,
        });
      }
    }
  }

  for (const [qNum, count] of seenQuestionNumbers) {
    if (count > 1) {
      issues.push({
        level: "error",
        message: `question_number trùng lặp: ${qNum} xuất hiện ${count} lần — load_barem() chỉ giữ lại entry cuối cùng.`,
      });
    }
  }
  for (const [sampleId, count] of seenSampleIds) {
    if (count > 1) {
      issues.push({ level: "warning", message: `sample_id trùng lặp: '${sampleId}' (${count} lần).` });
    }
  }
  for (const [slotId, count] of seenSlotIds) {
    if (count > 1) {
      issues.push({ level: "error", message: `slot_id trùng lặp: '${slotId}' xuất hiện ${count} lần.` });
    }
  }
}

// ── Entry point ──────────────────────────────────────────────────────────

export function validateExam(exam: ExamRubric): ValidationReport {
  const issues: ValidationIssue[] = [];

  if (!exam.subject?.trim()) {
    issues.push({
      level: "warning",
      message: "subject để trống — LLM sẽ không biết đang chấm môn gì (đưa vào prompt qua _grader_intro).",
    });
  }
  if (!exam.ma_de?.trim()) {
    issues.push({ level: "warning", message: "ma_de để trống — barem và file input phải cùng mã đề." });
  }

  validateStructure(exam.teacher_barem, issues);
  const computedTotal = validateScoring(exam.teacher_barem, exam.total_score, issues);

  const errors = issues.filter((issue) => issue.level === "error");
  const warnings = issues.filter((issue) => issue.level === "warning");

  return { valid: errors.length === 0, issues, errors, warnings, computedTotal };
}

/** Effective leaf criteria of one question — used by the editor to preview scores. */
export function previewFlat(question: RubricQuestion): FlatCriterion[] {
  return flattenCriteria(question);
}

export { questionTotal };

/** True when this criterion is a wrapper (never graded directly). */
export function isWrapper(criterion: Criterion): boolean {
  return Boolean(criterion.sub_criteria?.length);
}
