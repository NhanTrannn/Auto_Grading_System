/**
 * Editor for one criterion, showing only the fields its `question_type`
 * actually uses.
 *
 * Type-specific fields are gated rather than all shown at once because the four
 * modes read disjoint field sets: `expected_outputs` means nothing to a
 * `logical` criterion, `keywords` mean nothing to `matching`, and a `visual`
 * criterion reads neither (the Vision LLM works from `content` + `grader_note`
 * alone). Showing an inert field invites authoring into it.
 *
 * Wrapper criteria (those with sub_criteria) are rendered as a group header:
 * flatten_criteria() never emits them as gradable, so their expected_* fields
 * would be dead weight — only their score, grader_note and grouping mode matter.
 */
import type { ReactNode } from "react";

import Badge from "@/components/core/Badge";
import Button from "@/components/core/Button";
import type { AnswerSlot, Criterion, LogicalExpectedValue, PartialCreditRule, QuestionType } from "@/types/barem";
import { QUESTION_TYPES } from "@/types/barem";

import ConditionalEditor from "./ConditionalEditor";
import MatchingPreview from "./MatchingPreview";
import { Checkbox, EntryListInput, Field, ListInput, NumberInput, Row, Select, TextArea, TextInput } from "./Field";
import styles from "./CriterionEditor.module.css";

const TYPE_LABELS: Record<QuestionType, string> = {
  matching: "matching — so khớp chính xác chuỗi/token",
  logical: "logical — chấm theo logic, LLM quyết định",
  table: "table — chấm đúng 1 ô của bảng",
  visual: "visual — Vision LLM đọc ảnh trực tiếp",
};

interface CriterionEditorProps {
  criterion: Criterion;
  /** All slots of the owning question, for slot_ids and condition_source pickers. */
  availableSlots: AnswerSlot[];
  availablePartLabels: string[];
  /** Cell ids of the criterion's part, for the table row/col pickers. */
  availableCells: string[];
  /** True when the parent group is all_or_nothing — children use weight, not score. */
  inAllOrNothingGroup: boolean;
  /** Set when this child is scored by `weight` as a share of its parent's score. */
  derivedScore?: number;
  depth: number;
  onChange: (criterion: Criterion) => void;
  onRemove: () => void;
  onAddSubCriterion: () => void;
  children?: ReactNode;
}

/**
 * Flip a group between all_or_nothing and independently-scored children.
 *
 * Turning it OFF is the case that needs help: inside an all_or_nothing group a
 * child legitimately carries no `score` (the parent's covers the whole group),
 * so clearing the flag alone leaves every child with nothing to be worth, and
 * `validate_barem()` rejects each one with "score để trống nhưng KHÔNG thuộc
 * nhóm all_or_nothing". Children that already have a score or a weight are left
 * exactly as they are; the rest get `weight: 1`, which makes flatten_criteria
 * split the parent's score evenly between them — the least surprising reading
 * of "these now score on their own", and adjustable afterwards.
 */
function toggleAllOrNothing(criterion: Criterion, enabled: boolean): Partial<Criterion> {
  if (enabled) return { all_or_nothing: true };

  const subCriteria = (criterion.sub_criteria ?? []).map((child) =>
    child.score == null && !child.weight ? { ...child, weight: 1 } : child,
  );
  return { all_or_nothing: undefined, sub_criteria: subCriteria };
}

function asLogicalValue(value: Criterion["expected_value"]): LogicalExpectedValue {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as LogicalExpectedValue;
  return {};
}

function firstRule(rule: Criterion["partial_credit_rule"]): PartialCreditRule | null {
  if (!rule) return null;
  return Array.isArray(rule) ? (rule[0] ?? null) : rule;
}

export default function CriterionEditor({
  criterion,
  availableSlots,
  availablePartLabels,
  availableCells,
  inAllOrNothingGroup,
  derivedScore,
  depth,
  onChange,
  onRemove,
  onAddSubCriterion,
  children,
}: CriterionEditorProps) {
  const isWrapper = Boolean(criterion.sub_criteria?.length);
  const type = criterion.question_type as QuestionType | undefined;
  const patch = (updates: Partial<Criterion>) => onChange({ ...criterion, ...updates });

  const rows = [...new Set(availableCells.map((cell) => cell.split("C")[0]))].sort();
  const cols = [...new Set(availableCells.map((cell) => `C${cell.split("C")[1]}`))].sort();

  return (
    <div className={styles.criterion} data-depth={depth}>
      <header className={styles.head}>
        <div className={styles.headMain}>
          <input
            className={styles.idInput}
            value={criterion.criterion_id}
            onChange={(event) => patch({ criterion_id: event.target.value })}
            placeholder="T1"
          />
          {isWrapper ? (
            <Badge tone="neutral" dot={false}>
              nhóm · {criterion.sub_criteria!.length} tiêu chí con
            </Badge>
          ) : (
            <Badge tone={type ? "accent" : "warning"} dot={false}>
              {type ?? "chưa chọn loại"}
            </Badge>
          )}
        </div>
        <button type="button" className={styles.remove} onClick={onRemove}>
          Xoá
        </button>
      </header>

      <div className={styles.body}>
        <Row>
          {!isWrapper && (
            <Field label="question_type" required hint="Quyết định trực tiếp hàm chấm nào chạy.">
              <Select
                value={(criterion.question_type as string) ?? ""}
                onChange={(value) => patch({ question_type: value })}
                options={[
                  { value: "", label: "— chọn loại —" },
                  ...QUESTION_TYPES.map((item) => ({ value: item, label: TYPE_LABELS[item] })),
                ]}
              />
            </Field>
          )}
          <Field label="part_label" hint="Phần của câu mà tiêu chí này chấm.">
            <Select
              value={criterion.part_label ?? ""}
              onChange={(value) => patch({ part_label: value })}
              options={[
                { value: "", label: "— kế thừa từ cha —" },
                ...availablePartLabels.map((label) => ({ value: label, label })),
              ]}
            />
          </Field>
          {inAllOrNothingGroup ? (
            <Field
              label="weight"
              hint="Nhóm all_or_nothing: điểm thật nằm ở tiêu chí cha, weight chỉ là tỷ trọng nội bộ."
            >
              <NumberInput value={criterion.weight ?? null} step={0.05} onChange={(weight) => patch({ weight: weight ?? undefined })} />
            </Field>
          ) : derivedScore !== undefined ? (
            <Field
              label="weight"
              hint={`Tiêu chí này chia theo tỷ trọng từ điểm của tiêu chí cha ⇒ đang là ${derivedScore.toFixed(2)} điểm. Muốn ghi điểm tuyệt đối thì xoá weight rồi nhập score.`}
            >
              <NumberInput
                value={criterion.weight ?? null}
                step={0.05}
                onChange={(weight) => patch({ weight: weight ?? undefined })}
              />
            </Field>
          ) : (
            <Field label="score" required hint="Điểm tối đa của tiêu chí này.">
              <NumberInput value={criterion.score ?? null} onChange={(score) => patch({ score })} nullable />
            </Field>
          )}
        </Row>

        <Field
          label="content"
          required
          hint="Nguồn chính LLM dùng để hiểu tiêu chí. Viết càng cụ thể càng tốt — nêu rõ cả ví dụ SAI nếu muốn chấm chặt, vì mặc định LLM được dặn 'chấp nhận cách làm tương đương'."
        >
          <TextArea value={criterion.content ?? ""} onChange={(content) => patch({ content })} rows={3} />
        </Field>

        <Field
          label="grader_note"
          hint="Ngoại lệ / cách xử lý case đặc biệt. Ghi ở tiêu chí cha sẽ được GỘP (không ghi đè) vào mọi tiêu chí con."
        >
          <TextArea
            value={criterion.grader_note ?? ""}
            onChange={(grader_note) => patch({ grader_note: grader_note || undefined })}
            rows={2}
          />
        </Field>

        {!isWrapper && (
          <Field label="slot_ids" hint="Chọn đúng slot giúp lấy bài làm chính xác hơn là lọc theo part_label.">
            <div className={styles.slotPicker}>
              {availableSlots.length === 0 && <span className={styles.emptyHint}>Câu này chưa có answer_slot nào.</span>}
              {availableSlots.map((slot) => {
                const checked = criterion.slot_ids?.includes(slot.slot_id) ?? false;
                return (
                  <label key={slot.slot_id} className={`${styles.slotChip} ${checked ? styles.slotChipOn : ""}`}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        const current = criterion.slot_ids ?? [];
                        patch({
                          slot_ids: event.target.checked
                            ? [...current, slot.slot_id]
                            : current.filter((id) => id !== slot.slot_id),
                        });
                      }}
                    />
                    {slot.slot_id}
                  </label>
                );
              })}
            </div>
          </Field>
        )}

        {isWrapper && (
          <>
            <Checkbox
              checked={Boolean(criterion.all_or_nothing)}
              onChange={(all_or_nothing) => patch(toggleAllOrNothing(criterion, all_or_nothing))}
              label="all_or_nothing"
              hint="Chỉ cho điểm khi TẤT CẢ tiêu chí con đúng; điểm cộng 1 lần cho cả nhóm bằng 'score' của tiêu chí cha. Tắt đi thì mỗi tiêu chí con phải tự có điểm — chỗ nào chưa có sẽ được gán weight để chia đều từ điểm của tiêu chí cha."
            />
            {!criterion.all_or_nothing && criterion.grader_note && (
              <div className={styles.notice}>
                Nhóm này có <code>grader_note</code> và tiêu chí con loại <code>table</code> ⇒ pipeline sẽ bật{" "}
                <code>group_llm_decided</code>: chính LLM đọc ghi chú rồi tự quyết điểm cả nhóm, thay vì cộng dồn
                điểm từng ô. Điểm hiển thị của từng ô vẫn đúng nhưng không còn quyết định điểm thật của nhóm.
              </div>
            )}
          </>
        )}

        {!isWrapper && type === "matching" && (
          <>
            <Field
              label="expected_outputs — các cách viết được chấp nhận"
              required
              hint={
                <>
                  Mỗi ô là <strong>một đáp án trọn vẹn</strong>, được so khớp nguyên văn từng ký tự: đúng một ô bất kỳ
                  là <code>correct</code> và ăn trọn điểm. Đáp án nhiều dòng thì gõ xuống dòng ngay trong ô — đừng tách
                  thành hai ô, vì như thế thành hai đáp án riêng và bài của học sinh sẽ không khớp ô nào. Khoảng trắng,
                  dấu câu và chữ hoa/thường đều tính. Ghi đúng <code>student_index</code> để hệ thống tự thay bằng STT
                  thật của từng học sinh.
                </>
              }
            >
              <EntryListInput
                multiline
                value={criterion.expected_outputs ?? []}
                onChange={(expected_outputs) => patch({ expected_outputs })}
                placeholder={"3529"}
                addLabel="Thêm đáp án"
                emptyLabel="Chưa có đáp án nào — tiêu chí này sẽ không bao giờ đạt 'correct'."
              />
            </Field>

            <Field
              label="expected_output_tokens — mảnh nhỏ để chấm điểm bán phần"
              hint={
                <>
                  Dùng khi bài không khớp tuyệt đối nhưng vẫn đáng được một phần điểm.{" "}
                  <strong>Không có dấu phân cách nào cả</strong> — mỗi ô là một token riêng, không phải một chuỗi bị
                  tách bằng dấu phẩy hay khoảng trắng. Muốn 4 token thì tạo 4 ô. Khoảng trắng gõ bên trong một ô là một
                  phần của chính token đó (ô <code>3 5</code> đi tìm nguyên cụm "3 5", khác hẳn hai ô <code>3</code> và{" "}
                  <code>5</code>). Hệ thống tìm lần lượt từ trên xuống, mỗi token tìm tiếp <em>sau</em> chỗ token trước
                  dừng lại — nên <strong>thứ tự quan trọng</strong>, còn vị trí chính xác thì không. Khớp đủ 100% token
                  vẫn chỉ là <code>partially_correct</code>.
                </>
              }
            >
              <EntryListInput
                ordered
                value={criterion.expected_output_tokens ?? []}
                onChange={(expected_output_tokens) => patch({ expected_output_tokens })}
                placeholder="3"
                addLabel="Thêm token"
                emptyLabel="Chưa có token nào — sai khớp tuyệt đối là mất trọn điểm, không có bán phần."
              />
            </Field>

            <MatchingPreview
              expectedOutputs={criterion.expected_outputs ?? []}
              tokens={criterion.expected_output_tokens ?? []}
              maxScore={criterion.score ?? 0}
              partialCreditRule={criterion.partial_credit_rule}
            />

            <fieldset className={styles.subsection}>
              <legend>partial_credit_rule</legend>
              {(() => {
                const rule = firstRule(criterion.partial_credit_rule);
                if (!rule) {
                  return (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        patch({
                          partial_credit_rule: {
                            type: "count_correct_tokens",
                            partial_score: 0.25,
                            condition: "correct_token_count in [2, 3]",
                          },
                        })
                      }
                    >
                      Thêm quy tắc điểm bán phần
                    </Button>
                  );
                }
                const update = (updates: Partial<PartialCreditRule>) =>
                  patch({ partial_credit_rule: { ...rule, ...updates } });
                return (
                  <>
                    <Row>
                      <Field label="type">
                        <Select
                          value={rule.type}
                          onChange={(value) => update({ type: value })}
                          options={[
                            { value: "count_correct_tokens", label: "count_correct_tokens" },
                            { value: "count_wrong_tokens", label: "count_wrong_tokens" },
                            { value: "date_partial_match", label: "date_partial_match" },
                            { value: "position_tolerance", label: "position_tolerance" },
                          ]}
                        />
                      </Field>
                      <Field label="partial_score">
                        <NumberInput
                          value={rule.partial_score}
                          onChange={(partial_score) => update({ partial_score: partial_score ?? 0 })}
                        />
                      </Field>
                    </Row>
                    <Field
                      label="condition"
                      hint="Biến dùng được tuỳ type: correct_token_count, wrong_token_count, month, year."
                    >
                      <TextInput value={rule.condition} onChange={(condition) => update({ condition })} mono />
                    </Field>
                    <Button size="sm" variant="ghost" onClick={() => patch({ partial_credit_rule: undefined })}>
                      Bỏ quy tắc
                    </Button>
                  </>
                );
              })()}
            </fieldset>

            <fieldset className={styles.subsection}>
              <legend>Đáp án phụ thuộc từng học sinh</legend>
              {criterion.conditional_outputs?.length ? (
                <ConditionalEditor
                  conditionalOutputs={criterion.conditional_outputs}
                  conditionSource={criterion.condition_source}
                  availableSlots={availableSlots}
                  onChangeOutputs={(conditional_outputs) =>
                    patch({
                      conditional_outputs: conditional_outputs.length ? conditional_outputs : undefined,
                      condition_source: conditional_outputs.length ? criterion.condition_source : undefined,
                    })
                  }
                  onChangeSource={(condition_source) => patch({ condition_source })}
                />
              ) : (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    patch({
                      conditional_outputs: [
                        { condition: "value % 4 == 0", expected_outputs: [], expected_output_tokens: [] },
                      ],
                      condition_source: { type: "sample_field", field: "student_index" },
                    })
                  }
                >
                  Thêm conditional_outputs
                </Button>
              )}
            </fieldset>
          </>
        )}

        {!isWrapper && type === "logical" && (
          <Row>
            <Field
              label="keywords"
              hint="Mỗi dòng một từ khoá. CHỈ liệt kê thứ sinh viên THỰC SỰ phải tự gõ — tên hàm đề đã in sẵn sẽ luôn báo 'missing' và đẩy tín hiệu sai vào prompt LLM."
            >
              <ListInput
                value={asLogicalValue(criterion.expected_value).keywords ?? []}
                onChange={(keywords) =>
                  patch({ expected_value: { ...asLogicalValue(criterion.expected_value), keywords } })
                }
                placeholder={"KiemTraSNT\nTongSNT"}
                rows={4}
              />
            </Field>
            <Field label="sample_solution" hint="Code mẫu tham khảo — chỉ hiện cho LLM đối chiếu, không bị quét từ khoá.">
              <TextArea
                value={asLogicalValue(criterion.expected_value).sample_solution ?? ""}
                onChange={(sample_solution) =>
                  patch({ expected_value: { ...asLogicalValue(criterion.expected_value), sample_solution } })
                }
                rows={6}
                mono
              />
            </Field>
          </Row>
        )}

        {!isWrapper && type === "table" && (
          <Row>
            <Field label="row_id" required>
              <Select
                value={criterion.row_id ?? ""}
                onChange={(row_id) => patch({ row_id })}
                options={[{ value: "", label: "—" }, ...rows.map((r) => ({ value: r, label: r }))]}
              />
            </Field>
            <Field label="col_id" required>
              <Select
                value={criterion.col_id ?? ""}
                onChange={(col_id) => patch({ col_id })}
                options={[{ value: "", label: "—" }, ...cols.map((c) => ({ value: c, label: c }))]}
              />
            </Field>
            <Field
              label="expected_value.sample_solution"
              hint="CHỈ là ví dụ gợi ý cho LLM — không dùng so khớp cứng, vì đề dạng 'cho 3 ví dụ' chấp nhận mọi cặp hợp lệ."
            >
              <TextInput
                value={asLogicalValue(criterion.expected_value).sample_solution ?? ""}
                onChange={(sample_solution) => patch({ expected_value: { sample_solution } })}
                mono
              />
            </Field>
          </Row>
        )}

        {!isWrapper && type === "visual" && (
          <div className={styles.notice}>
            Vision LLM chấm trực tiếp từ ảnh bài làm dựa trên <code>content</code> và <code>grader_note</code> — không
            có heuristic advisory, không blend điểm, không cần khai <code>expected_*</code>.
          </div>
        )}

        {children && <div className={styles.subCriteria}>{children}</div>}

        {(isWrapper || depth === 0) && (
          <Button size="sm" variant="ghost" onClick={onAddSubCriterion}>
            + Tiêu chí con
          </Button>
        )}
      </div>
    </div>
  );
}
