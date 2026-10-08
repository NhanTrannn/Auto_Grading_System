/**
 * Editor for one question: its prompt text, its parts (answer regions, tables,
 * answer slots) and its grading_rule tree.
 *
 * Parts and criteria are shown together rather than on separate screens because
 * they are cross-referential — a criterion picks a part_label and slot_ids that
 * must already exist, and a table criterion addresses a cell of that part's
 * table_slot. Splitting them would mean editing blind on both sides.
 */
import { useEffect, useState } from "react";

import Button from "@/components/core/Button";
import Card from "@/components/core/Card";
import type { Criterion, QuestionPart, QuestionTable, RubricQuestion } from "@/types/barem";

import { useAdvancedMode } from "./advancedMode";
import ConfirmDelete from "./ConfirmDelete";
import CriterionEditor from "./CriterionEditor";
import { collectCriterionIds, replaceCriterion, uniqueCriterionId } from "./criterionTree";
import { deepClone, makeTable, nextPartLabel, slotId, slotsForTable } from "./factory";
import { Field, NumberInput, Row, TextArea, TextInput } from "./Field";
import { flattenCriteria, questionTotal } from "./flatten";
import { renamePartLabel } from "./renamePart";
import { countScoreMentions, rescoreQuestion, rewriteScoreInText } from "./rescore";
import styles from "./QuestionEditor.module.css";
import TableSlotEditor from "./TableSlotEditor";

interface QuestionEditorProps {
  question: RubricQuestion;
  /** Numbers already used by other questions, so a renumber can't collide. */
  takenNumbers: number[];
  onChange: (question: RubricQuestion) => void;
  onRenumber: (nextNumber: number) => void;
  onRemove: () => void;
  onDuplicate: () => void;
}

/**
 * Question number, committed on blur/Enter instead of per keystroke.
 *
 * The number is the key the whole editor selects by, and every slot_id embeds
 * it, so applying "1" → "12" one character at a time would renumber twice and
 * pass through states like "" (= 0). Holding the text locally until the author
 * is done means only a finished, valid, unused number is ever applied.
 */
function QuestionNumberInput({
  value,
  takenNumbers,
  onCommit,
}: {
  value: number;
  takenNumbers: number[];
  onCommit: (next: number) => void;
}) {
  const [text, setText] = useState(String(value));
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    setText(String(value));
    setProblem(null);
  }, [value]);

  function commit() {
    const next = Number(text.trim());
    if (!/^\d+$/.test(text.trim()) || next < 1) {
      setProblem("Số câu phải là số nguyên dương.");
      setText(String(value));
      return;
    }
    if (next !== value && takenNumbers.includes(next)) {
      setProblem(`Đã có câu ${next} — chọn số khác.`);
      setText(String(value));
      return;
    }
    setProblem(null);
    if (next !== value) onCommit(next);
  }

  return (
    <>
      <input
        className={styles.numberInput}
        value={text}
        inputMode="numeric"
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") {
            setText(String(value));
            event.currentTarget.blur();
          }
        }}
      />
      {problem && <span className={styles.numberProblem}>{problem}</span>}
    </>
  );
}

export default function QuestionEditor({
  question,
  takenNumbers,
  onChange,
  onRenumber,
  onRemove,
  onDuplicate,
}: QuestionEditorProps) {
  const advanced = useAdvancedMode();
  const parts = question.question.parts;
  const allSlots = parts.flatMap((part) => part.answer_slots);
  const partLabels = parts.map((part) => part.part_label);
  const flat = flattenCriteria(question);
  const total = questionTotal(flat);
  const [rescoreBlocked, setRescoreBlocked] = useState<string | null>(null);
  const textScoreMentions = countScoreMentions(question.question.text);

  /**
   * A question has no score of its own, so this rescales its criteria and, when
   * the wording allows it, keeps the "(0.5 điểm)" in the question text in step.
   * That text is what the LLM reads, so leaving it stale would have it grading
   * against one number while the rubric totals another.
   */
  function applyTotal(next: number | null) {
    if (next === null) return;
    const result = rescoreQuestion(question, next);
    setRescoreBlocked(result.blocked ?? null);
    if (result.blocked) return;

    const rewritten = rewriteScoreInText(result.question.question.text, next);
    onChange(
      rewritten === null
        ? result.question
        : { ...result.question, question: { ...result.question.question, text: rewritten } },
    );
  }

  // Cells already addressed by a table criterion, so the grid can mark them.
  const gradedCellsByPart = new Map<string, Set<string>>();
  for (const criterion of flat) {
    if (criterion.question_type !== "table" || !criterion.row_id || !criterion.col_id) continue;
    const label = criterion.part_label ?? "";
    const set = gradedCellsByPart.get(label) ?? new Set<string>();
    set.add(`${criterion.row_id}${criterion.col_id}`);
    gradedCellsByPart.set(label, set);
  }

  function updatePart(index: number, updater: (part: QuestionPart) => QuestionPart) {
    onChange({
      ...question,
      question: {
        ...question.question,
        parts: parts.map((part, i) => (i === index ? updater(deepClone(part)) : part)),
      },
    });
  }

  function updateCriteria(updater: (criteria: Criterion[]) => Criterion[]) {
    onChange({ ...question, grading_rule: updater(deepClone(question.grading_rule)) });
  }

  function addSubCriterion(parentId: string) {
    updateCriteria((criteria) => {
      const walk = (items: Criterion[]): Criterion[] =>
        items.map((item) => {
          if (item.criterion_id === parentId) {
            const children = item.sub_criteria ?? [];
            return {
              ...item,
              // A parent that gains children stops being graded itself, so its
              // own type marker becomes informational only.
              question_type: item.question_type ?? "multi_type",
              sub_criteria: [
                ...children,
                {
                  criterion_id: uniqueCriterionId(
                    `${parentId}${children.length + 1}`,
                    collectCriterionIds(question.grading_rule),
                  ),
                  question_type: "matching",
                  content: "",
                  score: 0,
                },
              ],
            };
          }
          if (item.sub_criteria?.length) return { ...item, sub_criteria: walk(item.sub_criteria) };
          return item;
        });
      return walk(criteria);
    });
  }

  function renderCriterion(criterion: Criterion, depth: number, index: number, parent?: Criterion) {
    const partLabel = criterion.part_label ?? "";
    const part = parts.find((p) => p.part_label === partLabel);
    const cells = (part?.tables ?? []).flatMap((table) => table.table_slot.map((cell) => cell.cell_id));
    const inGroup = Boolean(parent?.all_or_nothing);

    // Outside an all_or_nothing group a child may still be scored by `weight`,
    // as a share of the parent's score (flattenCriteria derives it). Compute
    // the same number here so the editor can show what the child is worth
    // instead of an empty `score` box that looks unfilled.
    let derivedScore: number | undefined;
    if (parent && !parent.all_or_nothing && criterion.score == null && criterion.weight) {
      const totalWeight = (parent.sub_criteria ?? []).reduce((sum, sc) => sum + (sc.weight || 0), 0);
      if (totalWeight) derivedScore = (parent.score ?? 0) * (criterion.weight / totalWeight);
    }

    return (
      <CriterionEditor
        // Position, not id: while an author is mid-rename two criteria can
        // briefly share an id, and React would then treat them as one element
        // and carry the first one's local state onto the second.
        key={`${depth}:${index}`}
        criterion={criterion}
        availableSlots={allSlots}
        availablePartLabels={partLabels}
        availableCells={cells}
        inAllOrNothingGroup={inGroup}
        derivedScore={derivedScore}
        depth={depth}
        onChange={(next) => updateCriteria((criteria) => replaceCriterion(criteria, criterion.criterion_id, next))}
        onRemove={() => updateCriteria((criteria) => replaceCriterion(criteria, criterion.criterion_id, null))}
        onAddSubCriterion={() => addSubCriterion(criterion.criterion_id)}
      >
        {criterion.sub_criteria?.map((sub, i) => renderCriterion(sub, depth + 1, i, criterion))}
      </CriterionEditor>
    );
  }

  return (
    <div className={styles.wrapper}>
      <Card
        title={`Câu ${question.question_number}`}
        subtitle={`Tổng điểm tính từ tiêu chí: ${total.toFixed(2)}`}
        actions={
          <div className={styles.headActions}>
            <Button size="sm" variant="secondary" onClick={onDuplicate}>
              Nhân bản
            </Button>
            <ConfirmDelete label="Xoá câu" onConfirm={onRemove} />
          </div>
        }
      >
        <div className={styles.stack}>
          <Row>
            <Field
              label="Số thứ tự câu" name="question_number"
              hint="Phải khớp số câu trên tờ đề — dùng để ghép bài làm của học sinh với câu này."
            >
              <QuestionNumberInput
                value={question.question_number}
                takenNumbers={takenNumbers}
                onCommit={onRenumber}
              />
            </Field>
            <Field
              label="Mã định danh câu" name="sample_id" advanced
              hint="Chỉ để người đọc — pipeline không ghép dữ liệu theo trường này."
            >
              <TextInput value={question.sample_id} onChange={(sample_id) => onChange({ ...question, sample_id })} mono />
            </Field>
            <Field
              label="Điểm cả câu"
              hint={
                textScoreMentions === 1
                  ? "Chia lại theo tỉ lệ cho các tiêu chí bên dưới, và sửa luôn số điểm ghi trong đề bài."
                  : textScoreMentions === 0
                    ? "Chia lại theo tỉ lệ cho các tiêu chí bên dưới. Đề bài không ghi số điểm nào nên không có gì để sửa theo."
                    : `Chia lại theo tỉ lệ cho các tiêu chí bên dưới. Đề bài ghi ${textScoreMentions} số điểm nên không tự sửa — bạn tự sửa trong ô đề bài.`
              }
            >
              <NumberInput value={total} onChange={applyTotal} step={0.25} min={0} />
            </Field>
          </Row>

          {rescoreBlocked && <p className={styles.rescoreBlocked}>{rescoreBlocked}</p>}

          <Field
            label="Đề bài" name="question.text"
            required
            hint={
              <>
                Nguyên văn đề bài, kể cả chương trình C++. Nếu đề có phần IN SẴN (chữ ký hàm, biến
                khai sẵn) PHẢI ghi rõ ở đây — nếu không AI chấm sẽ tưởng sinh viên thiếu và trừ điểm
                oan. Tab để thụt lề, Shift+Tab lùi lại, Esc để rời ô.
                <br />
                Công thức toán: gõ LaTeX giữa <code>$…$</code> (giữa dòng) hoặc <code>$$…$$</code>{" "}
                (riêng một dòng) rồi xem bản dựng ngay bên dưới; hoặc chép ký hiệu:{" "}
                <code>∈ ∉ ⊂ ℝ ℕ × · ÷ ≤ ≥ ≠ ≈ Σ ∏ √ ∞ ∂ ∇ α β θ λ μ σ ⁰¹²³ⁿ ₀₁₂ₜ</code>
              </>
            }
          >
            <TextArea
              value={question.question.text}
              onChange={(text) => onChange({ ...question, question: { ...question.question, text } })}
              rows={6}
              mono
              code
              math
            />
          </Field>
        </div>
      </Card>

      <Card
        title="Các phần trả lời"
        subtitle={
          parts.length > 1
            ? "Mỗi phần (a, b, c…) là một vùng trả lời riêng trên tờ giấy thi"
            : "Câu có nhiều ý a, b, c… thì bấm “+ Phần” để tách vùng trả lời"
        }
        actions={
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              const label = nextPartLabel(partLabels);
              onChange({
                ...question,
                question: {
                  ...question.question,
                  parts: [
                    ...parts,
                    {
                      part_label: label,
                      text: "",
                      tables: [],
                      answer_slots: [{ slot_id: slotId(question.sample_id, label) }],
                    },
                  ],
                },
              });
            }}
          >
            + Phần
          </Button>
        }
      >
        <div className={styles.stack}>
          {parts.length === 0 && <p className={styles.empty}>Chưa có phần nào — câu này chưa có vùng trả lời để chấm.</p>}
          {parts.map((part, index) => (
            <div key={index} className={styles.part}>
              {(advanced || parts.length > 1) && (
                <Row>
                  <Field
                    label="Tên phần" name="part_label"
                    required
                    hint="VD: a, b, c. Đổi tên ở đây thì mã ô trả lời và mọi tiêu chí đang trỏ tới phần này cũng được đổi theo."
                  >
                    <TextInput
                      value={part.part_label}
                      onChange={(part_label) => onChange(renamePartLabel(question, index, part_label))}
                      mono
                    />
                  </Field>
                  <Field label="Ghi chú" name="note" advanced hint="Ghi chú cho người soạn, không ảnh hưởng chấm điểm.">
                    <TextInput
                      value={part.note ?? ""}
                      onChange={(note) => updatePart(index, (p) => ({ ...p, note: note || undefined }))}
                    />
                  </Field>
                </Row>
              )}

              <Field
                label={parts.length > 1 ? "Yêu cầu riêng của phần này" : "Yêu cầu riêng (nếu có)"}
                name="text"
                hint="Chỉ ghi yêu cầu chưa có trong đề bài, VD “Hãy tìm 3 ví dụ”. Không cần chép lại đề."
              >
                <TextArea
                  value={part.text}
                  onChange={(text) => updatePart(index, (p) => ({ ...p, text }))}
                  rows={2}
                  math
                />
              </Field>

              <Field
                label="Các ô trả lời" name="answer_slots" advanced
                hint="Mỗi dòng một slot_id — khoá nối với dữ liệu OCR của sinh viên. Thường đã được tạo tự động."
              >
                <div className={styles.slotList}>
                  {part.answer_slots.map((slot, slotIndex) => (
                    <div key={slotIndex} className={styles.slotRow}>
                      <TextInput
                        value={slot.slot_id}
                        mono
                        onChange={(value) =>
                          updatePart(index, (p) => ({
                            ...p,
                            answer_slots: p.answer_slots.map((s, i) =>
                              i === slotIndex ? { ...s, slot_id: value } : s,
                            ),
                          }))
                        }
                      />
                      {slot.cell_id && <span className={styles.cellTag}>{slot.cell_id}</span>}
                      <button
                        type="button"
                        className={styles.slotRemove}
                        onClick={() =>
                          updatePart(index, (p) => ({
                            ...p,
                            answer_slots: p.answer_slots.filter((_, i) => i !== slotIndex),
                          }))
                        }
                      >
                        ×
                      </button>
                    </div>
                  ))}
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      updatePart(index, (p) => ({
                        ...p,
                        answer_slots: [
                          ...p.answer_slots,
                          { slot_id: slotId(question.sample_id, p.part_label, p.answer_slots.length + 1) },
                        ],
                      }))
                    }
                  >
                    + Slot
                  </Button>
                </div>
              </Field>

              <div className={styles.tables}>
                {part.tables.map((table, tableIndex) => (
                  <TableSlotEditor
                    key={tableIndex}
                    table={table}
                    answerSlots={part.answer_slots}
                    gradedCells={gradedCellsByPart.get(part.part_label) ?? new Set()}
                    onChange={(next) =>
                      updatePart(index, (p) => ({
                        ...p,
                        tables: p.tables.map((t, i) => (i === tableIndex ? next : t)),
                      }))
                    }
                    onRemove={() =>
                      updatePart(index, (p) => ({ ...p, tables: p.tables.filter((_, i) => i !== tableIndex) }))
                    }
                    onSyncSlots={(next: QuestionTable) =>
                      updatePart(index, (p) => {
                        // Keep slots that already point at a cell; add one per
                        // student cell that has none yet.
                        const existing = new Map(
                          p.answer_slots.filter((s) => s.cell_id).map((s) => [s.cell_id!, s]),
                        );
                        const generated = slotsForTable(question.sample_id, p.part_label, next);
                        return {
                          ...p,
                          answer_slots: generated.map((slot) => existing.get(slot.cell_id!) ?? slot),
                        };
                      })
                    }
                  />
                ))}
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    updatePart(index, (p) => ({
                      ...p,
                      tables: [...p.tables, makeTable(`TB${p.tables.length + 1}`)],
                    }))
                  }
                >
                  + Bảng
                </Button>
              </div>

              <div className={styles.partFooter}>
                <ConfirmDelete
                  compact
                  label={parts.length > 1 ? `Xoá phần '${part.part_label}'` : "Xoá phần trả lời"}
                  onConfirm={() =>
                    onChange({
                      ...question,
                      question: { ...question.question, parts: parts.filter((_, i) => i !== index) },
                    })
                  }
                />
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card
        title="Tiêu chí chấm"
        subtitle="Tiêu chí có tiêu chí con là một nhóm — điểm được tính ở các tiêu chí con"
        actions={
          <Button
            size="sm"
            variant="secondary"
            onClick={() =>
              updateCriteria((criteria) => [
                ...criteria,
                {
                  criterion_id: uniqueCriterionId(
                    `T${question.question_number}_${criteria.length + 1}`,
                    collectCriterionIds(criteria),
                  ),
                  question_type: "matching",
                  part_label: partLabels[0] ?? "main",
                  slot_ids: parts[0]?.answer_slots.map((s) => s.slot_id) ?? [],
                  content: "",
                  score: 0,
                  expected_outputs: [],
                },
              ])
            }
          >
            + Tiêu chí
          </Button>
        }
      >
        <div className={styles.stack}>
          {question.grading_rule.length === 0 && (
            <p className={styles.empty}>Chưa có tiêu chí nào — câu này sẽ không được chấm điểm.</p>
          )}
          {question.grading_rule.map((criterion, i) => renderCriterion(criterion, 0, i))}
        </div>
      </Card>
    </div>
  );
}
