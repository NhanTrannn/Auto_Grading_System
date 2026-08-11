/**
 * Constructors for new barem nodes, pre-filled so a freshly added question is
 * already schema-valid rather than a shell the author has to repair.
 *
 * ID conventions follow structure_parem.txt §6:
 *   sample_id  = cau_{n}_001
 *   slot_id    = {sample_id}_{part_label}          (single-slot part)
 *              = {sample_id}_{part_label}_S{k}     (multi-slot part)
 *   criterion  = T{n} / T{n}{PART} / T{n}{PART}{k}
 *   cell_id    = {row_id}{col_id}, e.g. R2C1
 */
import type {
  Criterion,
  QuestionPart,
  QuestionPreset,
  QuestionTable,
  RubricQuestion,
  TableSlotCell,
} from "@/types/barem";

export const PRESET_INFO: Record<
  QuestionPreset,
  { label: string; hint: string; prompt: string; content: string }
> = {
  matching: {
    label: "Khớp đáp án",
    hint: "So khớp chính xác chuỗi/token",
    prompt: "Kết quả in ra màn hình là gì?",
    content: "Ghi đúng kết quả chương trình. Nêu rõ đáp án đúng và mức điểm bán phần nếu có.",
  },
  logical: {
    label: "Suy luận / code",
    hint: "Chấm theo logic, LLM quyết định",
    prompt: "Viết đoạn chương trình thực hiện yêu cầu sau.",
    content: "Viết đúng logic theo yêu cầu. Chấp nhận mọi cách làm tương đương về kết quả.",
  },
  table: {
    label: "Điền bảng",
    hint: "Mỗi ô là một tiêu chí",
    prompt: "Điền vào bảng dưới đây.",
    content: "Điền đúng các ô trong bảng.",
  },
  visual: {
    label: "Hình / lưu đồ",
    hint: "Vision LLM đọc ảnh trực tiếp",
    prompt: "Vẽ lưu đồ cho thuật toán sau.",
    content: "Vẽ đúng lưu đồ thể hiện thuật toán, đủ các khối và hướng rẽ nhánh.",
  },
};

export function slotId(sampleId: string, partLabel: string, index?: number): string {
  return index === undefined ? `${sampleId}_${partLabel}` : `${sampleId}_${partLabel}_S${index}`;
}

/**
 * Header row R1 is `printed`, every data cell is `student_text`. Both kinds are
 * listed: grade_table_group_with_llm() builds the table it shows the LLM from
 * table_slot, so omitting header cells would hand it an unlabelled grid.
 */
export function makeTableSlot(rows: number, cols: number, headers: string[] = []): TableSlotCell[] {
  const cells: TableSlotCell[] = [];
  for (let r = 1; r <= rows; r += 1) {
    for (let c = 1; c <= cols; c += 1) {
      const rowId = `R${r}`;
      const colId = `C${c}`;
      const isHeader = r === 1;
      cells.push({
        cell_id: `${rowId}${colId}`,
        source: isHeader ? "printed" : "student_text",
        row_id: rowId,
        col_id: colId,
        text: isHeader ? (headers[c - 1] ?? `Cột ${c}`) : "",
      });
    }
  }
  return cells;
}

export function makeTable(tableId = "TB1", rows = 4, cols = 2): QuestionTable {
  return { table_id: tableId, table_slot: makeTableSlot(rows, cols, ["Input", "Output"]) };
}

/** Answer slots for exactly the `student_text` cells — printed cells aren't graded. */
export function slotsForTable(sampleId: string, partLabel: string, table: QuestionTable) {
  return table.table_slot
    .filter((cell) => cell.source === "student_text")
    .map((cell, index) => ({
      slot_id: slotId(sampleId, partLabel, index + 1),
      cell_id: cell.cell_id,
      row_id: cell.row_id,
      col_id: cell.col_id,
    }));
}

export function makePart(sampleId: string, partLabel: string, text = ""): QuestionPart {
  return {
    part_label: partLabel,
    text,
    tables: [],
    answer_slots: [{ slot_id: slotId(sampleId, partLabel) }],
  };
}

/** Next free part label: main → a → b → c … */
export function nextPartLabel(existing: string[]): string {
  if (!existing.includes("main")) return "main";
  for (let i = 0; i < 26; i += 1) {
    const label = String.fromCharCode(97 + i);
    if (!existing.includes(label)) return label;
  }
  return `part_${existing.length + 1}`;
}

export function makeCriterion(
  criterionId: string,
  preset: QuestionPreset,
  part: QuestionPart,
  score: number,
): Criterion {
  const base: Criterion = {
    criterion_id: criterionId,
    question_type: preset,
    part_label: part.part_label,
    slot_ids: part.answer_slots.map((slot) => slot.slot_id),
    content: PRESET_INFO[preset].content,
    score,
  };

  switch (preset) {
    case "matching":
      return { ...base, expected_outputs: [], expected_output_tokens: [] };
    case "logical":
      return { ...base, expected_value: { keywords: [], sample_solution: "" } };
    case "table":
      return { ...base, row_id: "R2", col_id: "C1", expected_value: { sample_solution: "" } };
    case "visual":
      return base;
  }
}

export function makeQuestion(preset: QuestionPreset, questionNumber: number): RubricQuestion {
  const sampleId = `cau_${questionNumber}_001`;
  const info = PRESET_INFO[preset];
  const part = makePart(sampleId, "main", info.prompt);

  if (preset === "table") {
    const table = makeTable();
    part.tables = [table];
    part.answer_slots = slotsForTable(sampleId, "main", table);

    // One criterion per student cell, grouped under an all_or_nothing wrapper —
    // the T15B1..T15B5 shape. Cells of one table are graded together in a single
    // LLM call, so splitting them per cell is what lets the LLM see the grid.
    const wrapper: Criterion = {
      criterion_id: `T${questionNumber}`,
      question_type: "multi_type",
      part_label: "main",
      sub_label: "main",
      content: info.content,
      score: 0.5,
      all_or_nothing: true,
      grader_note: "Phải đúng toàn bộ các ô mới được điểm.",
      slot_ids: part.answer_slots.map((slot) => slot.slot_id),
      sub_criteria: part.answer_slots.map((slot, index) => ({
        criterion_id: `T${questionNumber}_${index + 1}`,
        question_type: "table" as const,
        row_id: slot.row_id,
        col_id: slot.col_id,
        content: `Ô ${slot.cell_id}.`,
        weight: 0.1,
        expected_value: { sample_solution: "" },
      })),
    };

    return {
      sample_id: sampleId,
      question_number: questionNumber,
      question: { text: `Câu ${questionNumber}: (0.5 điểm)`, parts: [part] },
      grading_rule: [wrapper],
    };
  }

  return {
    sample_id: sampleId,
    question_number: questionNumber,
    question: { text: `Câu ${questionNumber}: (0.5 điểm)`, parts: [part] },
    grading_rule: [makeCriterion(`T${questionNumber}`, preset, part, 0.5)],
  };
}

export function emptyExam(): RubricQuestion[] {
  return [];
}

export function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}
