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

import { useAdvancedMode } from "./advancedMode";
import ConditionalEditor from "./ConditionalEditor";
import ConfirmDelete from "@/components/core/ConfirmDelete";
import MatchingPreview from "./MatchingPreview";
import { Checkbox, EntryListInput, Field, ListInput, NumberInput, Row, Select, TextArea, TextInput } from "./Field";
import styles from "./CriterionEditor.module.css";

const TYPE_LABELS: Record<QuestionType, string> = {
  matching: "So khớp đáp án — kết quả in ra, giá trị cụ thể",
  logical: "Chấm theo logic — viết code, giải thích",
  table: "Một ô trong bảng",
  visual: "Hình vẽ — AI đọc thẳng từ ảnh bài làm",
};

/** Short form for the criterion's header badge. */
const TYPE_BADGES: Record<QuestionType, string> = {
  matching: "So khớp",
  logical: "Logic",
  table: "Ô bảng",
  visual: "Hình vẽ",
};

const RULE_TYPE_LABELS: Record<string, string> = {
  count_correct_tokens: "Theo số mảnh đúng",
  count_wrong_tokens: "Theo số mảnh sai",
  custom_condition: "Điều kiện tự viết",
  date_partial_match: "Ngày tháng: đúng tháng + năm",
  position_tolerance: "Chỉ sai 2 vị trí đầu/cuối",
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

/**
 * `partial_credit_rule` is a single rule OR a list of tiers, and the editor has
 * to hold both without changing the file more than the author asked.
 *
 * Reading always yields a list. Writing collapses a one-element list back to a
 * bare object, because that is how every criterion in `sample_parem.json` is
 * written — emitting a list there would rewrite eight criteria the author never
 * touched. This used to read `rule[0]` and write a bare object unconditionally,
 * so opening a criterion with tiered rules and editing anything silently threw
 * the other tiers away.
 */
function rulesOf(rule: Criterion["partial_credit_rule"]): PartialCreditRule[] {
  if (!rule) return [];
  return Array.isArray(rule) ? rule : [rule];
}

const CONDITION_HINT: Record<string, string> = {
  count_correct_tokens: "Biến dùng được: correct_token_count. VD: correct_token_count in [2, 3]",
  count_wrong_tokens: "Biến dùng được: wrong_token_count. VD: wrong_token_count in [1, 2]",
  custom_condition: "Dùng được cả correct_token_count và wrong_token_count.",
  date_partial_match:
    "Không đọc condition — luật cứng trong code: đúng cả tháng và năm thì được điểm. Ô này chỉ để ghi chú.",
  position_tolerance:
    "Không đọc condition — luật cứng trong code: chỉ sai ở 2 vị trí đầu hoặc 2 vị trí cuối thì được điểm.",
  default: "Biến dùng được tuỳ type.",
};

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
  const advanced = useAdvancedMode();
  const isWrapper = Boolean(criterion.sub_criteria?.length);
  const type = criterion.question_type as QuestionType | undefined;
  const patch = (updates: Partial<Criterion>) => onChange({ ...criterion, ...updates });

  const rows = [...new Set(availableCells.map((cell) => cell.split("C")[0]))].sort();
  const cols = [...new Set(availableCells.map((cell) => `C${cell.split("C")[1]}`))].sort();

  const rules = rulesOf(criterion.partial_credit_rule);
  const writeRules = (next: PartialCreditRule[]) =>
    patch({ partial_credit_rule: next.length === 0 ? undefined : next.length === 1 ? next[0] : next });

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
              {type ? (TYPE_BADGES[type] ?? type) : "chưa chọn kiểu chấm"}
            </Badge>
          )}
        </div>
        <ConfirmDelete compact label="Xoá" onConfirm={onRemove} />
      </header>

      <div className={styles.body}>
        <Row>
          {!isWrapper && (
            <Field label="Kiểu chấm" name="question_type" required hint="Quyết định cách hệ thống chấm tiêu chí này.">
              <Select
                value={(criterion.question_type as string) ?? ""}
                onChange={(value) => patch({ question_type: value })}
                options={[
                  { value: "", label: "— chọn kiểu chấm —" },
                  ...QUESTION_TYPES.map((item) => ({ value: item, label: TYPE_LABELS[item] })),
                ]}
              />
            </Field>
          )}
          <Field
            label="Thuộc phần" name="part_label"
            advanced={availablePartLabels.length <= 1}
            hint="Phần của câu mà tiêu chí này chấm."
          >
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
              label="Tỷ trọng trong nhóm" name="weight"
              hint="Nhóm “đúng hết mới được điểm”: điểm thật nằm ở tiêu chí cha, đây chỉ là tỷ trọng nội bộ."
            >
              <NumberInput value={criterion.weight ?? null} step={0.05} onChange={(weight) => patch({ weight: weight ?? undefined })} />
            </Field>
          ) : derivedScore !== undefined ? (
            <Field
              label="Tỷ trọng trong nhóm" name="weight"
              hint={`Tiêu chí này chia theo tỷ trọng từ điểm của tiêu chí cha ⇒ đang là ${derivedScore.toFixed(2)} điểm. Muốn ghi điểm cố định thì xoá tỷ trọng rồi nhập điểm.`}
            >
              <NumberInput
                value={criterion.weight ?? null}
                step={0.05}
                onChange={(weight) => patch({ weight: weight ?? undefined })}
              />
            </Field>
          ) : (
            <Field label="Điểm tối đa" name="score" required hint="Điểm tối đa của tiêu chí này.">
              <NumberInput value={criterion.score ?? null} onChange={(score) => patch({ score })} nullable />
            </Field>
          )}
        </Row>

        <Field
          label="Mô tả tiêu chí" name="content"
          required
          hint="Nguồn chính AI chấm dùng để hiểu tiêu chí. Viết càng cụ thể càng tốt — nêu rõ cả ví dụ SAI nếu muốn chấm chặt, vì mặc định AI được dặn 'chấp nhận cách làm tương đương'."
        >
          <TextArea value={criterion.content ?? ""} onChange={(content) => patch({ content })} rows={3} math />
        </Field>

        <Field
          label="Ghi chú cho người chấm" name="grader_note"
          hint="Ngoại lệ / cách xử lý case đặc biệt. Ghi ở tiêu chí cha sẽ được GỘP (không ghi đè) vào mọi tiêu chí con."
        >
          <TextArea
            value={criterion.grader_note ?? ""}
            onChange={(grader_note) => patch({ grader_note: grader_note || undefined })}
            rows={2}
            math
          />
        </Field>

        {!isWrapper && (
          <Field
            label="Chấm dựa trên ô trả lời nào" name="slot_ids"
            advanced={availableSlots.length <= 1}
            hint="Chọn đúng ô giúp lấy bài làm chính xác hơn."
          >
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
              label="Đúng hết mới được điểm" name="all_or_nothing"
              hint="Chỉ cho điểm khi TẤT CẢ tiêu chí con đúng; cả nhóm được cộng một lần bằng điểm của tiêu chí cha. Tắt đi thì mỗi tiêu chí con tự có điểm — chỗ nào chưa có sẽ được chia đều từ điểm của tiêu chí cha."
            />
            {!criterion.all_or_nothing && criterion.grader_note && (
              <div className={styles.notice}>
                Nhóm này có ghi chú cho người chấm, nên nếu các tiêu chí con là ô bảng thì AI sẽ đọc ghi chú và{" "}
                <strong>tự quyết điểm cả nhóm</strong> thay vì cộng dồn điểm từng ô. Điểm từng ô vẫn hiển thị để đối
                chiếu nhưng không quyết định điểm thật của nhóm.
              </div>
            )}
          </>
        )}

        {!isWrapper && type === "matching" && (
          <>
            <Field
              label="Các cách viết được chấp nhận" name="expected_outputs"
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
              label="Mảnh nhỏ để chấm điểm bán phần" name="expected_output_tokens"
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
              <legend>
                Các mức điểm bán phần
                {advanced && <code className={styles.legendName}>partial_credit_rule</code>}
              </legend>
              <p className={styles.sectionNote}>
                Khai được <strong>nhiều mức</strong>. Khi chấm, hệ thống thử <em>tất cả</em> rồi lấy mức có{" "}
                <strong>partial_score cao nhất</strong> trong số các mức khớp — nên thứ tự khai không quan trọng.
                Chỉ cần có một mức bất kỳ ở đây là điểm theo tỉ lệ token bị <strong>thay thế hoàn toàn</strong>:
                không mức nào khớp thì về 0, kể cả khi đúng gần hết token.
              </p>
              {rules.length === 0 && <p className={styles.sectionNote}>Chưa có mức nào — sai khớp tuyệt đối là mất trọn điểm.</p>}

              {rules.map((rule, index) => {
                const update = (updates: Partial<PartialCreditRule>) =>
                  writeRules(rules.map((r, i) => (i === index ? { ...r, ...updates } : r)));
                return (
                  <div key={index} className={styles.ruleCard}>
                    <div className={styles.ruleHead}>
                      <span className={styles.ruleIndex}>Mức {index + 1}</span>
                      <button
                        type="button"
                        className={styles.ruleRemove}
                        onClick={() => writeRules(rules.filter((_, i) => i !== index))}
                      >
                        Xoá mức
                      </button>
                    </div>
                    <Row>
                      <Field label="Cách xét" name="type">
                        <Select
                          value={rule.type}
                          onChange={(value) => update({ type: value })}
                          options={Object.entries(RULE_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
                        />
                      </Field>
                      <Field label="Điểm được hưởng" name="partial_score">
                        <NumberInput
                          value={rule.partial_score}
                          onChange={(partial_score) => update({ partial_score: partial_score ?? 0 })}
                        />
                      </Field>
                    </Row>
                    <Field label="Điều kiện" name="condition" hint={CONDITION_HINT[rule.type] ?? CONDITION_HINT.default}>
                      <TextInput value={rule.condition} onChange={(condition) => update({ condition })} mono />
                    </Field>
                  </div>
                );
              })}

              <Button
                size="sm"
                variant="secondary"
                onClick={() =>
                  writeRules([
                    ...rules,
                    { type: "count_correct_tokens", partial_score: 0.25, condition: "correct_token_count in [2, 3]" },
                  ])
                }
              >
                Thêm mức điểm bán phần
              </Button>
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
                  Thêm đáp án theo từng học sinh
                </Button>
              )}
            </fieldset>
          </>
        )}

        {!isWrapper && type === "logical" && (
          <Row>
            <Field
              label="Từ khoá bắt buộc có" name="keywords"
              hint="Mỗi dòng một từ khoá. CHỈ liệt kê thứ sinh viên THỰC SỰ phải tự viết — tên hàm đề đã in sẵn sẽ luôn bị báo là thiếu và làm AI chấm hiểu sai."
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
            <Field
              label="Đáp án mẫu"
              name="sample_solution"
              hint="Đưa nguyên văn cho AI chấm để đối chiếu — kèm sẵn lời dặn bài học sinh KHÔNG cần giống hệt, chỉ cần đúng logic. Viết được cả lời giải thích lẫn code. Tab để thụt lề, Esc để rời ô."
            >
              <TextArea
                value={asLogicalValue(criterion.expected_value).sample_solution ?? ""}
                onChange={(sample_solution) =>
                  patch({ expected_value: { ...asLogicalValue(criterion.expected_value), sample_solution } })
                }
                rows={6}
                mono
                code
                math
              />
            </Field>
          </Row>
        )}

        {!isWrapper && type === "table" && (
          <Row>
            <Field label="Hàng" name="row_id" required>
              <Select
                value={criterion.row_id ?? ""}
                onChange={(row_id) => patch({ row_id })}
                options={[{ value: "", label: "—" }, ...rows.map((r) => ({ value: r, label: r }))]}
              />
            </Field>
            <Field label="Cột" name="col_id" required>
              <Select
                value={criterion.col_id ?? ""}
                onChange={(col_id) => patch({ col_id })}
                options={[{ value: "", label: "—" }, ...cols.map((c) => ({ value: c, label: c }))]}
              />
            </Field>
            <Field
              label="Ví dụ gợi ý cho ô này" name="expected_value.sample_solution"
              hint="CHỈ là ví dụ gợi ý cho AI chấm — không so khớp cứng, vì đề dạng 'cho 3 ví dụ' chấp nhận mọi cặp hợp lệ."
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
            AI đọc thẳng ảnh bài làm và chấm dựa trên <strong>Mô tả tiêu chí</strong> và{" "}
            <strong>Ghi chú cho người chấm</strong> ở trên — không cần khai đáp án.
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
