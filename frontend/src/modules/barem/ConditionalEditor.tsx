/**
 * Editor for per-student conditional answers: `conditional_outputs` plus the
 * `condition_source` that resolves the `value` their conditions branch on.
 *
 * The two halves are edited together on purpose. `condition_source` is
 * mandatory whenever conditional_outputs exists — pipeline.py has no implicit
 * default, and a criterion missing it doesn't error, it just quietly grades
 * everything wrong. And the two source types take *different keys* (`field` vs
 * `slot_ids`); mixing them up resolves to an empty slot list which then falls
 * back to reading the student's whole answer. Both traps are structural, so the
 * form models them as one exclusive choice rather than free-form JSON.
 *
 * Three more rules are invisible in the JSON and are surfaced here instead,
 * because each one silently costs students marks when an author gets it wrong:
 * branches are tried top to bottom and the **first** match wins; a value
 * matching **no** branch grades against an empty answer list, so it can only
 * ever be wrong; and with a `self_reported` source, a blank slot is scored
 * wrong outright without going to the LLM. The value tester at the bottom is
 * the only practical way to check the first two before a real run.
 */
import { useState } from "react";

import Button from "@/components/core/Button";
import type { AnswerSlot, ConditionalOutput, ConditionSource } from "@/types/barem";

import { evaluateCondition } from "./conditionEval";
import { EntryListInput, Field, Select, TextInput } from "./Field";
import styles from "./ConditionalEditor.module.css";

interface ConditionalEditorProps {
  conditionalOutputs: ConditionalOutput[];
  conditionSource?: ConditionSource;
  /** Every slot in the question — a self_reported source must point at one. */
  availableSlots: AnswerSlot[];
  onChangeOutputs: (outputs: ConditionalOutput[]) => void;
  onChangeSource: (source: ConditionSource | undefined) => void;
}

const SAMPLE_FIELDS = [
  { value: "student_index", label: "student_index — STT thật trong danh sách thi" },
  { value: "ma_de", label: "ma_de — mã đề" },
];

const DEFAULT_TEST_VALUES = "1, 2, 3, 4, 5, 6, 7, 8";

function parseTestValues(raw: string): string[] {
  return raw
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export default function ConditionalEditor({
  conditionalOutputs,
  conditionSource,
  availableSlots,
  onChangeOutputs,
  onChangeSource,
}: ConditionalEditorProps) {
  const [testValues, setTestValues] = useState(DEFAULT_TEST_VALUES);
  const sourceType = conditionSource?.type ?? "none";

  function setSourceType(type: "none" | "sample_field" | "self_reported") {
    if (type === "none") onChangeSource(undefined);
    else if (type === "sample_field") onChangeSource({ type: "sample_field", field: "student_index" });
    else onChangeSource({ type: "self_reported", slot_ids: [] });
  }

  function updateBranch(index: number, patch: Partial<ConditionalOutput>) {
    onChangeOutputs(conditionalOutputs.map((branch, i) => (i === index ? { ...branch, ...patch } : branch)));
  }

  function moveBranch(index: number, delta: number) {
    const target = index + delta;
    if (target < 0 || target >= conditionalOutputs.length) return;
    const next = [...conditionalOutputs];
    [next[index], next[target]] = [next[target], next[index]];
    onChangeOutputs(next);
  }

  function addBranch() {
    onChangeOutputs([
      ...conditionalOutputs,
      { condition: `value % 4 == ${conditionalOutputs.length}`, expected_outputs: [], expected_output_tokens: [] },
    ]);
  }

  function toggleSlot(slotId: string) {
    if (conditionSource?.type !== "self_reported") return;
    const current = conditionSource.slot_ids;
    onChangeSource({
      type: "self_reported",
      slot_ids: current.includes(slotId) ? current.filter((id) => id !== slotId) : [...current, slotId],
    });
  }

  const sourceLabel =
    conditionSource?.type === "sample_field"
      ? conditionSource.field
      : conditionSource?.type === "self_reported"
        ? conditionSource.slot_ids.join(" + ") || "(chưa chọn slot)"
        : "(chưa khai nguồn)";

  const values = parseTestValues(testValues);
  const rows = values.map((value) => {
    const evaluations = conditionalOutputs.map((branch) => evaluateCondition(branch.condition, value));
    const hit = evaluations.findIndex((result) => result.matched);
    const alsoMatched = evaluations.reduce<number[]>((acc, result, index) => {
      if (result.matched && index !== hit) acc.push(index + 1);
      return acc;
    }, []);
    const firstError = evaluations.find((result) => result.error)?.error;
    return { value, hit, alsoMatched, firstError };
  });
  const uncovered = rows.filter((row) => row.hit === -1);

  return (
    <div className={styles.wrapper}>
      <p className={styles.explainer}>
        Dùng khi <strong>mỗi học sinh có một đáp án đúng khác nhau</strong> (ví dụ kết quả phụ thuộc STT). Khi chấm, hệ
        thống lấy một con số gọi là <code>value</code> từ nguồn bên dưới, thử lần lượt từng nhánh từ trên xuống, và{" "}
        <strong>dừng ở nhánh đầu tiên đúng</strong> — đáp án của nhánh đó thay cho <code>expected_outputs</code> của
        tiêu chí.
      </p>

      <div className={styles.sourceBox}>
        <Field
          label="Bước 1 · Lấy 'value' từ đâu"
          required
          hint="Bắt buộc khi có conditional_outputs. Thiếu field này pipeline sẽ bỏ qua hoàn toàn việc chọn nhánh và chấm sai toàn bộ."
        >
          <Select
            value={sourceType}
            onChange={setSourceType}
            options={[
              { value: "none", label: "— chưa khai —" },
              { value: "sample_field", label: "sample_field — đọc từ dữ liệu gốc (STT thật)" },
              { value: "self_reported", label: "self_reported — đọc từ slot sinh viên tự ghi" },
            ]}
          />
        </Field>

        {conditionSource?.type === "sample_field" && (
          <Field
            label="field"
            hint="Chấm theo STT thật trong danh sách. Học sinh nhớ nhầm số của mình rồi tính nhất quán theo số nhầm đó vẫn bị tính sai."
          >
            <Select
              value={conditionSource.field}
              onChange={(field) => onChangeSource({ type: "sample_field", field })}
              options={SAMPLE_FIELDS}
            />
          </Field>
        )}

        {conditionSource?.type === "self_reported" && (
          <Field
            label="slot_ids"
            required
            hint="Chấm theo con số học sinh THỰC SỰ dùng để tính, nên không phạt oan khi họ nhớ nhầm STT nhưng làm nhất quán. Chọn nhiều slot thì nội dung các slot được nối lại. Học sinh bỏ trống slot ⇒ chấm sai luôn, không qua LLM."
          >
            <div className={styles.slotPicker}>
              {availableSlots.length === 0 && <span className={styles.slotEmpty}>Câu này chưa khai slot nào.</span>}
              {availableSlots.map((slot) => (
                <label key={slot.slot_id} className={styles.slotChip}>
                  <input
                    type="checkbox"
                    checked={conditionSource.slot_ids.includes(slot.slot_id)}
                    onChange={() => toggleSlot(slot.slot_id)}
                  />
                  <code>{slot.slot_id}</code>
                </label>
              ))}
            </div>
          </Field>
        )}
      </div>

      <div className={styles.branchesHead}>
        <span className={styles.stepLabel}>Bước 2 · Các nhánh, xét từ trên xuống</span>
        <span className={styles.sourceEcho}>
          value = <code>{sourceLabel}</code>
        </span>
      </div>

      <div className={styles.branches}>
        {conditionalOutputs.map((branch, index) => (
          <div key={index} className={styles.branch}>
            <div className={styles.branchHead}>
              <span className={styles.branchIndex}>Nhánh {index + 1}</span>
              <div className={styles.branchActions}>
                <button
                  type="button"
                  className={styles.iconButton}
                  onClick={() => moveBranch(index, -1)}
                  disabled={index === 0}
                  title="Lên trước"
                >
                  ↑
                </button>
                <button
                  type="button"
                  className={styles.iconButton}
                  onClick={() => moveBranch(index, 1)}
                  disabled={index === conditionalOutputs.length - 1}
                  title="Xuống sau"
                >
                  ↓
                </button>
                <button
                  type="button"
                  className={styles.removeBranch}
                  onClick={() => onChangeOutputs(conditionalOutputs.filter((_, i) => i !== index))}
                >
                  Xoá
                </button>
              </div>
            </div>

            <Field
              label="Nếu…"
              hint="Biến duy nhất dùng được là 'value'. Cho phép: + - * / %, so sánh, in [..], and/or/not, .isdigit()."
            >
              <TextInput
                value={branch.condition}
                onChange={(condition) => updateBranch(index, { condition })}
                placeholder="value % 4 == 0"
                mono
              />
            </Field>

            <Field
              label="…thì đáp án đúng là"
              hint="Thay cho expected_outputs của tiêu chí. Đáp án nhiều dòng gõ ngay trong một ô."
            >
              <EntryListInput
                multiline
                value={branch.expected_outputs}
                onChange={(expected_outputs) => updateBranch(index, { expected_outputs })}
                placeholder="24615"
                addLabel="Thêm đáp án"
                emptyLabel="Chưa có đáp án — học sinh rơi vào nhánh này chắc chắn bị sai."
              />
            </Field>

            <Field label="…và token cho điểm bán phần" hint="Mỗi ô một token, tìm theo đúng thứ tự này.">
              <EntryListInput
                ordered
                value={branch.expected_output_tokens ?? []}
                onChange={(expected_output_tokens) => updateBranch(index, { expected_output_tokens })}
                placeholder="2"
                addLabel="Thêm token"
                emptyLabel="Không có token — nhánh này không cho điểm bán phần."
              />
            </Field>
          </div>
        ))}
      </div>

      <Button size="sm" variant="secondary" onClick={addBranch}>
        Thêm nhánh điều kiện
      </Button>

      {conditionalOutputs.length > 0 && (
        <div className={styles.tester}>
          <span className={styles.stepLabel}>Bước 3 · Thử xem giá trị nào rơi vào nhánh nào</span>
          <Field label="Các giá trị muốn thử" hint="Ngăn cách bằng dấu phẩy. Nên thử đủ dải STT thật của lớp.">
            <TextInput value={testValues} onChange={setTestValues} mono placeholder={DEFAULT_TEST_VALUES} />
          </Field>

          <div className={styles.testGrid}>
            {rows.map((row) => (
              <div
                key={row.value}
                className={`${styles.testCell} ${row.hit === -1 ? styles.testMiss : styles.testHit}`}
                title={row.firstError ?? undefined}
              >
                <code>{row.value}</code>
                <span>
                  {row.hit === -1 ? "không nhánh nào" : `nhánh ${row.hit + 1}`}
                  {row.alsoMatched.length > 0 && (
                    <em className={styles.overlap}> (nhánh {row.alsoMatched.join(", ")} cũng đúng, bị bỏ qua)</em>
                  )}
                </span>
              </div>
            ))}
          </div>

          {uncovered.length > 0 && (
            <p className={styles.warn}>
              {uncovered.length} giá trị không khớp nhánh nào ({uncovered.map((row) => row.value).join(", ")}). Học
              sinh có <code>value</code> như vậy sẽ được chấm với danh sách đáp án rỗng — luôn sai, dù bài làm đúng. Bổ
              sung nhánh hoặc nới điều kiện.
            </p>
          )}
          {rows.some((row) => row.firstError) && (
            <p className={styles.warn}>
              Có điều kiện không đọc được: {rows.find((row) => row.firstError)?.firstError}. Khi chấm thật, lỗi này chỉ
              hiện ra dưới dạng cảnh báo trong log và nhánh đó luôn bị bỏ qua.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
