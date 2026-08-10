import { useEffect, useState } from "react";

import Badge, { type Tone } from "@/components/core/Badge";
import { IconClose } from "@/components/core/Icon";
import type { CriterionResult, GradingResultSample } from "@/types/grading";

import styles from "./StudentDetailPanel.module.css";

interface StudentDetailPanelProps {
  hs: string;
  samples: GradingResultSample[];
  onClose: () => void;
}

const STATUS_TONE: Record<string, Tone> = {
  correct: "success",
  partially_correct: "warning",
  wrong: "danger",
  needs_teacher_review: "info",
  needs_vision_teacher_review: "info",
  error: "danger",
};

const STATUS_LABEL: Record<string, string> = {
  correct: "Đúng",
  partially_correct: "Đúng một phần",
  wrong: "Sai",
  needs_teacher_review: "Cần GV xem lại",
  needs_vision_teacher_review: "Cần GV xem lại (ảnh)",
  error: "Lỗi",
  ungraded: "Chưa chấm",
};

function statusTone(status: string): Tone {
  return STATUS_TONE[status] ?? "neutral";
}

function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status;
}

/** Reads a string field off a criterion result without widening the whole type. */
function str(cr: CriterionResult, key: string): string | null {
  const value = cr[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function num(cr: CriterionResult, key: string): number | null {
  const value = cr[key];
  return typeof value === "number" ? value : null;
}

function studentAnswerOf(cr: CriterionResult): string | null {
  const evidence = cr.evidence as { student_answer?: unknown } | undefined;
  const answer = evidence?.student_answer;
  return typeof answer === "string" && answer.trim() ? answer : null;
}

function CriterionCard({ cr }: { cr: CriterionResult }) {
  const [open, setOpen] = useState(false);
  const answer = studentAnswerOf(cr);
  // The pipeline names the rubric text `criterion_content`; `content` is only
  // used on table-batch fallback dicts.
  const description = str(cr, "criterion_content") ?? str(cr, "content");
  const reasoning = str(cr, "llm_reasoning") ?? str(cr, "reason");
  const suggestion = str(cr, "suggestion");
  const cot = str(cr, "cot_reasoning");
  const groupReason = str(cr, "group_score_reasoning");
  const heuristicScore = num(cr, "heuristic_score");
  const llmScore = num(cr, "llm_score");
  const hasDetail = Boolean(answer || cot || groupReason || heuristicScore !== null);

  return (
    <div className={styles.criterion}>
      <div className={styles.criterionHeader}>
        <span className={styles.criterionId}>{cr.criterion_id}</span>
        <span className={styles.criterionScore}>
          {cr.score?.toFixed?.(2) ?? cr.score} / {cr.max_score?.toFixed?.(2) ?? cr.max_score}
        </span>
        <Badge tone={statusTone(cr.status)}>{statusLabel(cr.status)}</Badge>
      </div>

      {description && <p className={styles.criterionContent}>{description}</p>}

      {reasoning && (
        <div className={styles.reasoning}>
          <span className={styles.reasoningLabel}>Lý do LLM</span>
          {reasoning}
        </div>
      )}

      {suggestion && (
        <div className={styles.suggestion}>
          <span className={styles.suggestionLabel}>Gợi ý cho học sinh</span>
          {suggestion}
        </div>
      )}

      {hasDetail && (
        <button type="button" className={styles.moreButton} onClick={() => setOpen((v) => !v)}>
          {open ? "Ẩn chi tiết" : "Xem thêm chi tiết"}
        </button>
      )}

      {open && (
        <div className={styles.detail}>
          {(heuristicScore !== null || llmScore !== null) && (
            <div className={styles.scoreBreakdown}>
              {heuristicScore !== null && (
                <span className={styles.scoreChip}>
                  Heuristic: <strong>{heuristicScore.toFixed(2)}</strong>
                </span>
              )}
              {llmScore !== null && (
                <span className={styles.scoreChip}>
                  LLM: <strong>{llmScore.toFixed(2)}</strong>
                </span>
              )}
              {str(cr, "stage") && <span className={styles.scoreChip}>Giai đoạn: {str(cr, "stage")}</span>}
              {str(cr, "grading_method") && (
                <span className={styles.scoreChip}>Cách chấm: {str(cr, "grading_method")}</span>
              )}
            </div>
          )}

          {answer && (
            <div className={styles.block}>
              <span className={styles.blockLabel}>Bài làm học sinh</span>
              <pre className={styles.answer}>{answer}</pre>
            </div>
          )}

          {groupReason && (
            <div className={styles.block}>
              <span className={styles.blockLabel}>Điểm nhóm do LLM quyết định</span>
              <p className={styles.blockText}>{groupReason}</p>
            </div>
          )}

          {cot && (
            <div className={styles.block}>
              <span className={styles.blockLabel}>Chain-of-Thought</span>
              <pre className={styles.cot}>{cot}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function StudentDetailPanel({ hs, samples, onClose }: StudentDetailPanelProps) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const sorted = [...samples].sort((a, b) => (a.question_number ?? 0) - (b.question_number ?? 0));
  const total = sorted.reduce((sum, s) => sum + (s.score ?? 0), 0);
  const maxTotal = sorted.reduce((sum, s) => sum + (s.max_score ?? 0), 0);

  return (
    <div className={styles.overlay} onClick={onClose}>
      <aside className={styles.panel} onClick={(e) => e.stopPropagation()}>
        <header className={styles.header}>
          <div>
            <h2 className={styles.title}>{hs}</h2>
            <p className={styles.subtitle}>
              {total.toFixed(2)} / {maxTotal.toFixed(2)} điểm · {sorted.length} câu
            </p>
          </div>
          <button type="button" className={styles.closeButton} onClick={onClose} aria-label="Đóng">
            <IconClose size={16} />
          </button>
        </header>

        <div className={styles.body}>
          {sorted.map((sample) => (
            <section key={sample.sample_id} className={styles.sample}>
              <div className={styles.sampleHeader}>
                <span className={styles.sampleTitle}>Câu {sample.question_number}</span>
                <span className={styles.sampleScore}>
                  {(sample.score ?? 0).toFixed(2)} / {(sample.max_score ?? 0).toFixed(2)}
                </span>
                <Badge tone={statusTone(sample.status)}>{statusLabel(sample.status)}</Badge>
              </div>
              {(sample.group_overrides ?? []).map((group) => (
                <div key={group.group_id} className={styles.groupOverride}>
                  <div className={styles.groupHeader}>
                    <span className={styles.groupId}>Nhóm {group.group_id}</span>
                    <Badge tone={group.group_decision_source === "llm" ? "accent" : "info"}>
                      {group.group_decision_source === "llm" ? "LLM quyết định" : "Trọn gói"}
                    </Badge>
                    <span className={styles.groupScore}>
                      {group.group_score.toFixed(2)} / {group.group_max_score.toFixed(2)}
                    </span>
                  </div>
                  <p className={styles.groupNote}>
                    Điểm của nhóm này tính chung cho {group.members.join(", ")} — không phải tổng
                    điểm từng tiêu chí bên dưới.
                  </p>
                  {group.group_score_reasoning && (
                    <p className={styles.groupReason}>{group.group_score_reasoning}</p>
                  )}
                </div>
              ))}

              <div className={styles.criteria}>
                {(sample.criterion_results ?? []).map((cr) => (
                  <CriterionCard key={cr.criterion_id} cr={cr} />
                ))}
              </div>
            </section>
          ))}
        </div>
      </aside>
    </div>
  );
}
