/**
 * Load a barem JSON from disk and normalise it onto the schema pipeline.py
 * actually reads.
 *
 * Two kinds of input arrive here:
 *   1. A real `sample_parem.json` already in the current schema — passes
 *      through essentially untouched.
 *   2. A file produced by the upstream rubric-builder, whose schema drifted
 *      from the backend in ways that silently produce ungradeable barems:
 *      `question_type` values outside the four pipeline.py knows, a singular
 *      `expected_output` string where the grader reads a plural
 *      `expected_outputs` list, nested `columns[]`/`rows[].cells[]` tables
 *      where `_attach_table_slots()` only understands a flat `table_slot`, and
 *      criterion fields no grading code ever reads.
 *
 * Every conversion is reported back so the author can see what changed rather
 * than discovering it later in a grading run.
 */
import type {
  Criterion,
  ExamRubric,
  QuestionPart,
  QuestionTable,
  RubricQuestion,
  TableSlotCell,
} from "@/types/barem";

export interface MigrationNote {
  /** Where the change happened, e.g. "Câu 3 / T3_main_s2". */
  where: string;
  message: string;
}

export interface MigrationResult {
  exam: ExamRubric;
  notes: MigrationNote[];
}

/**
 * Upstream question_type values → the four pipeline.py dispatches on.
 * `fill_in_the_blank` graded a fixed string, which is exactly `matching`.
 * `text` and `code` were both "let a human/LLM judge the reasoning", which is
 * `logical` — the mode whose heuristic only gathers keyword hints and leaves
 * the verdict to the LLM.
 */
const TYPE_MIGRATION: Record<string, string> = {
  fill_in_the_blank: "matching",
  fill_in_blank: "matching",
  text: "logical",
  code: "logical",
  short_text: "matching",
  long_text: "logical",
};

/** Fields the upstream schema carried that no grading code in pipeline.py reads. */
const DEAD_CRITERION_FIELDS = [
  "gradable",
  "accepted_special_answers",
  "combined_allowed",
  "scoring_note",
] as const;

const DEAD_EXAM_FIELDS = ["mc_total", "essay_total", "student_index_note"] as const;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asStringArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string");
  if (typeof value === "string" && value.length > 0) return [value];
  return [];
}

/**
 * Nested `columns[]` + `rows[].cells[]` → the flat `table_slot` list.
 *
 * Column headers were implicit in the old shape (a `header` string on the
 * column, outside the row grid); pipeline.py needs them as real cells, so they
 * become a `printed` row R1 and every authored row shifts down by one. That
 * shift is why an old barem's table criteria addressed R1/R2/R3 while the
 * current one addresses R2/R3/R4.
 */
function migrateTable(raw: unknown, where: string, notes: MigrationNote[]): QuestionTable | null {
  if (!isPlainObject(raw)) return null;
  const tableId = typeof raw.table_id === "string" ? raw.table_id : "TB1";

  if (Array.isArray(raw.table_slot)) {
    const cells = raw.table_slot
      .filter(isPlainObject)
      .map((cell): TableSlotCell => {
        const rowId = String(cell.row_id ?? "");
        const colId = String(cell.col_id ?? "");
        return {
          cell_id: typeof cell.cell_id === "string" ? cell.cell_id : `${rowId}${colId}`,
          source: cell.source === "printed" ? "printed" : "student_text",
          row_id: rowId,
          col_id: colId,
          text: typeof cell.text === "string" ? cell.text : "",
        };
      });
    return { table_id: tableId, table_slot: cells };
  }

  const columns = Array.isArray(raw.columns) ? raw.columns.filter(isPlainObject) : [];
  const rows = Array.isArray(raw.rows) ? raw.rows.filter(isPlainObject) : [];
  if (!columns.length && !rows.length) return { table_id: tableId, table_slot: [] };

  const tableSlot: TableSlotCell[] = [];

  if (columns.length) {
    for (const column of columns) {
      const colId = String(column.col_id ?? "");
      tableSlot.push({
        cell_id: `R1${colId}`,
        source: "printed",
        row_id: "R1",
        col_id: colId,
        text: typeof column.header === "string" ? column.header : "",
      });
    }
  }

  rows.forEach((row, rowIndex) => {
    // +2: R1 is now the header row synthesised above, so authored row 0 → R2.
    const newRowId = columns.length ? `R${rowIndex + 2}` : String(row.row_id ?? `R${rowIndex + 1}`);
    const cells = Array.isArray(row.cells) ? row.cells.filter(isPlainObject) : [];
    for (const cell of cells) {
      const colId = String(cell.col_id ?? "");
      const text = typeof cell.text === "string" ? cell.text : "";
      tableSlot.push({
        cell_id: `${newRowId}${colId}`,
        source: text ? "printed" : "student_text",
        row_id: newRowId,
        col_id: colId,
        text,
      });
    }
  });

  notes.push({
    where,
    message: columns.length
      ? `Bảng '${tableId}': chuyển columns/rows lồng nhau sang table_slot phẳng. Header thành hàng R1 (source='printed'), các hàng dữ liệu dời xuống R2, R3… — nhớ kiểm lại row_id trong tiêu chí table.`
      : `Bảng '${tableId}': chuyển columns/rows lồng nhau sang table_slot phẳng.`,
  });

  return { table_id: tableId, table_slot: tableSlot };
}

function migrateCriterion(raw: unknown, where: string, notes: MigrationNote[]): Criterion | null {
  if (!isPlainObject(raw)) return null;
  const criterion = { ...raw } as Record<string, unknown>;
  const cid = typeof criterion.criterion_id === "string" ? criterion.criterion_id : "(không có id)";
  const at = `${where} / ${cid}`;

  const rawType = criterion.question_type;
  if (typeof rawType === "string" && TYPE_MIGRATION[rawType]) {
    const mapped = TYPE_MIGRATION[rawType];
    criterion.question_type = mapped;
    notes.push({
      where: at,
      message: `question_type '${rawType}' không nằm trong 4 loại pipeline.py chấp nhận — đổi thành '${mapped}'. Kiểm lại xem có đúng ý không.`,
    });
  }

  // expected_output (chuỗi đơn) + accepted_outputs → expected_outputs (list)
  const singular = criterion.expected_output;
  const accepted = criterion.accepted_outputs;
  if (singular !== undefined || accepted !== undefined) {
    const merged = [...asStringArray(singular), ...asStringArray(accepted)];
    const existing = asStringArray(criterion.expected_outputs);
    const combined = [...new Set([...existing, ...merged])];
    if (combined.length) criterion.expected_outputs = combined;
    delete criterion.expected_output;
    delete criterion.accepted_outputs;
    notes.push({
      where: at,
      message: `Gộp expected_output/accepted_outputs thành expected_outputs (list) — pipeline.py chỉ đọc dạng số nhiều.`,
    });
  }

  if (Array.isArray(criterion.conditional_outputs)) {
    let changed = false;
    criterion.conditional_outputs = criterion.conditional_outputs.filter(isPlainObject).map((branch) => {
      const next = { ...branch };
      if (next.expected_output !== undefined) {
        const existing = asStringArray(next.expected_outputs);
        next.expected_outputs = [...new Set([...existing, ...asStringArray(next.expected_output)])];
        delete next.expected_output;
        changed = true;
      }
      return next;
    });
    if (changed) {
      notes.push({
        where: at,
        message: `conditional_outputs[].expected_output → expected_outputs (list).`,
      });
    }
    if (!criterion.condition_source) {
      notes.push({
        where: at,
        message: `Có conditional_outputs nhưng thiếu condition_source — BẮT BUỘC phải khai, nếu không pipeline bỏ qua hoàn toàn việc chọn nhánh. Cần điền tay.`,
      });
    }
  }

  // expected_value: an empty {} placeholder carries no information for a
  // logical criterion, and dropping it lets validation flag one that genuinely
  // has no keywords.
  //
  // Only for logical, though. On a table criterion the key's mere PRESENCE is
  // load-bearing: grade_table_criterion gates on `expected_value is not None`,
  // so `{}` grades the cell (the value itself is only a hint the LLM sees)
  // while a missing key takes the "thiếu row_id/col_id/expected_value" branch —
  // which drops `row_id`, leaves `student_cell_text` null and never extracts
  // what the student wrote. Importing a barem would have silently disarmed
  // every table criterion whose hint was empty.
  if (
    criterion.question_type === "logical" &&
    isPlainObject(criterion.expected_value) &&
    Object.keys(criterion.expected_value).length === 0
  ) {
    delete criterion.expected_value;
  }
  if (criterion.question_type === "logical" && isPlainObject(criterion.expected_value)) {
    const extras = Object.keys(criterion.expected_value).filter(
      (key) => key !== "keywords" && key !== "sample_solution",
    );
    if (extras.length) {
      notes.push({
        where: at,
        message: `expected_value có key ngoài {keywords, sample_solution}: ${extras.join(", ")} — grade_expected_value_criterion() bỏ qua hoàn toàn các key này. Chuyển nội dung sang 'keywords' nếu cần chấm.`,
      });
    }
  }

  const dropped = DEAD_CRITERION_FIELDS.filter((field) => field in criterion);
  for (const field of dropped) delete criterion[field];
  if (dropped.length) {
    notes.push({
      where: at,
      message: `Bỏ field không được pipeline.py đọc: ${dropped.join(", ")}.`,
    });
  }

  if (Array.isArray(criterion.sub_criteria)) {
    criterion.sub_criteria = criterion.sub_criteria
      .map((sub) => migrateCriterion(sub, where, notes))
      .filter((sub): sub is Criterion => sub !== null);
  }

  return criterion as unknown as Criterion;
}

function migratePart(raw: unknown, where: string, notes: MigrationNote[]): QuestionPart | null {
  if (!isPlainObject(raw)) return null;
  const tables = Array.isArray(raw.tables)
    ? raw.tables.map((table) => migrateTable(table, where, notes)).filter((t): t is QuestionTable => t !== null)
    : [];

  const answerSlots = Array.isArray(raw.answer_slots)
    ? raw.answer_slots.filter(isPlainObject).map((slot) => ({
        slot_id: String(slot.slot_id ?? ""),
        ...(slot.cell_id ? { cell_id: String(slot.cell_id) } : {}),
        ...(slot.row_id ? { row_id: String(slot.row_id) } : {}),
        ...(slot.col_id ? { col_id: String(slot.col_id) } : {}),
      }))
    : [];

  return {
    part_label: String(raw.part_label ?? "main"),
    text: typeof raw.text === "string" ? raw.text : "",
    tables,
    answer_slots: answerSlots,
    ...(typeof raw.note === "string" && raw.note ? { note: raw.note } : {}),
  };
}

function migrateQuestion(raw: unknown, notes: MigrationNote[]): RubricQuestion | null {
  if (!isPlainObject(raw)) return null;
  const questionNumber = Number(raw.question_number);
  const where = `Câu ${Number.isFinite(questionNumber) ? questionNumber : "?"}`;
  const questionBody = isPlainObject(raw.question) ? raw.question : {};

  const parts = Array.isArray(questionBody.parts)
    ? questionBody.parts.map((part) => migratePart(part, where, notes)).filter((p): p is QuestionPart => p !== null)
    : [];

  const gradingRuleRaw = Array.isArray(raw.grading_rule)
    ? raw.grading_rule
    : Array.isArray(raw.sub_questions)
      ? raw.sub_questions
      : [];

  const gradingRule = gradingRuleRaw
    .map((item) => migrateCriterion(item, where, notes))
    .filter((c): c is Criterion => c !== null);

  // A question-level question_type was only ever a fallback and no longer
  // routes anything — every leaf criterion declares its own.
  if (raw.question_type !== undefined) {
    notes.push({
      where,
      message: `Bỏ question_type ở cấp câu — routing giờ đọc question_type của TỪNG criterion lá, không có fallback lên cấp câu.`,
    });
  }

  return {
    sample_id: String(raw.sample_id ?? `cau_${questionNumber}_001`),
    question_number: Number.isFinite(questionNumber) ? questionNumber : 0,
    question: {
      text: typeof questionBody.text === "string" ? questionBody.text : "",
      parts,
    },
    ...(typeof raw.score === "number" ? { score: raw.score } : {}),
    grading_rule: gradingRule,
  };
}

export function migrateExam(raw: unknown): MigrationResult {
  const notes: MigrationNote[] = [];
  if (!isPlainObject(raw)) {
    throw new Error("File không phải là một object JSON hợp lệ.");
  }
  if (!Array.isArray(raw.teacher_barem)) {
    throw new Error("Thiếu mảng 'teacher_barem' — đây có phải file barem không?");
  }

  const teacherBarem = raw.teacher_barem
    .map((question) => migrateQuestion(question, notes))
    .filter((q): q is RubricQuestion => q !== null);

  const droppedExamFields = DEAD_EXAM_FIELDS.filter((field) => field in raw);
  if (droppedExamFields.length) {
    notes.push({
      where: "Thông tin đề",
      message: `Bỏ field không được pipeline.py đọc: ${droppedExamFields.join(", ")}.`,
    });
  }

  return {
    exam: {
      ma_de: String(raw.ma_de ?? "1"),
      subject: String(raw.subject ?? ""),
      total_score: Number(raw.total_score) || 0,
      teacher_barem: teacherBarem,
    },
    notes,
  };
}

/** Serialise exactly the fields pipeline.py reads, in a stable key order. */
export function serialiseExam(exam: ExamRubric): string {
  return JSON.stringify(
    {
      ma_de: exam.ma_de,
      subject: exam.subject,
      total_score: exam.total_score,
      teacher_barem: exam.teacher_barem,
    },
    null,
    2,
  );
}

export function downloadExam(exam: ExamRubric, filename = "sample_parem.json"): void {
  const blob = new Blob([serialiseExam(exam)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
