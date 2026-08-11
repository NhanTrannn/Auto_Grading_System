import { useEffect, useMemo, useState } from "react";

import Badge, { type Tone } from "@/components/core/Badge";
import Button from "@/components/core/Button";
import EmptyState from "@/components/core/EmptyState";
import { IconChevronRight, IconImage } from "@/components/core/Icon";
import { cropUrl } from "@/services/pipelineApi";
import type { CriterionResult, GradingJobResult, GradingResultSample } from "@/types/grading";
import type { OcrCauEntry, OcrResultsFile } from "@/types/pipeline";

import styles from "./StudentReview.module.css";

interface StudentReviewProps {
  jobId: string;
  result: GradingJobResult;
  ocr: OcrResultsFile | null;
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
  completed: "OCR xong",
  failed_at_cropping: "Không cắt/căn được",
};

function label(status: string): string {
  return STATUS_LABEL[status] ?? status;
}

function tone(status: string): Tone {
  return STATUS_TONE[status] ?? "neutral";
}

/** "Cau_15b_1" → 15, so an OCR region can be shown under its graded question. */
function questionOf(cauKey: string): number | null {
  const match = /^Cau_(\d+)/i.exec(cauKey);
  return match ? Number(match[1]) : null;
}

function ocrText(entry: OcrCauEntry): string {
  if (entry.type === "diagram") return "(vùng hình vẽ — không OCR)";
  const content = entry.content;
  if (!content) return "";
  if (content.error) return `Lỗi: ${content.error}`;
  if (Array.isArray(content.lines)) return content.lines.join("\n");
  if (Array.isArray(content.table_extracted)) {
    return content.table_extracted
      .map((row) => Object.values(row).map((v) => String(v ?? "")).join(" | "))
      .join("\n");
  }
  return JSON.stringify(content);
}

function RegionCard({
  jobId,
  hsKey,
  cauKey,
  entry,
}: {
  jobId: string;
  hsKey: string;
  cauKey: string;
  entry: OcrCauEntry;
}) {
  const [broken, setBroken] = useState(false);
  const text = ocrText(entry);

  return (
    <div className={styles.region}>
      <div className={styles.regionHeader}>
        <span className={styles.cauKey}>{cauKey}</span>
        <Badge tone={entry.status === "completed" ? "success" : "danger"}>
          {label(entry.status)}
        </Badge>
      </div>
      <div className={styles.regionBody}>
        <div className={styles.cropBox}>
          {broken ? (
            <span className={styles.cropMissing}>
              <IconImage size={18} />
              Không có ảnh cắt
            </span>
          ) : (
            <img
              className={styles.crop}
              src={cropUrl(jobId, hsKey, cauKey)}
              alt={`Bài làm ${cauKey}`}
              loading="lazy"
              onError={() => setBroken(true)}
            />
          )}
        </div>
        <div className={styles.readBox}>
          <span className={styles.readLabel}>Máy đọc được</span>
          <pre className={styles.readText}>{text || "(trống)"}</pre>
        </div>
      </div>
    </div>
  );
}

function CriterionRow({ cr }: { cr: CriterionResult }) {
  const reasoning = typeof cr.llm_reasoning === "string" ? cr.llm_reasoning : null;
  return (
    <div className={styles.criterion}>
      <div className={styles.criterionHeader}>
        <span className={styles.criterionId}>{cr.criterion_id}</span>
        <span className={styles.criterionScore}>
          {Number(cr.score ?? 0).toFixed(2)} / {Number(cr.max_score ?? 0).toFixed(2)}
        </span>
        <Badge tone={tone(cr.status)}>{label(cr.status)}</Badge>
      </div>
      {reasoning && <p className={styles.criterionReason}>{reasoning}</p>}
    </div>
  );
}

export default function StudentReview({ jobId, result, ocr }: StudentReviewProps) {
  const students = useMemo(
    () => [...result.student_summary].sort((a, b) => {
      const na = Number(a.hs.split("_").pop());
      const nb = Number(b.hs.split("_").pop());
      return (Number.isNaN(na) ? 0 : na) - (Number.isNaN(nb) ? 0 : nb);
    }),
    [result.student_summary],
  );

  const [index, setIndex] = useState(0);
  const current = students[index];

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = document.activeElement;
      if (el && ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)) return;
      if (e.key === "ArrowRight") setIndex((i) => Math.min(students.length - 1, i + 1));
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(0, i - 1));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [students.length]);

  const samples: GradingResultSample[] = useMemo(() => {
    if (!current) return [];
    return result.grading_results
      .filter((r) => r.sample_id.endsWith(`__${current.hs}`))
      .sort((a, b) => (a.question_number ?? 0) - (b.question_number ?? 0));
  }, [result.grading_results, current]);

  const regions = useMemo(() => {
    if (!current || !ocr) return {} as Record<string, OcrCauEntry>;
    const entry = ocr[current.hs];
    return (typeof entry === "object" && entry ? entry : {}) as Record<string, OcrCauEntry>;
  }, [ocr, current]);

  if (!current) {
    return <EmptyState title="Chưa có học sinh nào để soát" />;
  }

  const percent = current.max_score ? Math.round((current.score / current.max_score) * 100) : 0;
  const usedCauKeys = new Set<string>();

  return (
    <div className={styles.wrapper}>
      <header className={styles.bar}>
        <Button
          variant="secondary"
          size="sm"
          disabled={index === 0}
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
        >
          ← Trước
        </Button>

        <div className={styles.identity}>
          <span className={styles.hsKey}>{current.hs}</span>
          <span className={styles.position}>
            {index + 1} / {students.length}
          </span>
          <span className={styles.score}>
            {current.score.toFixed(2)} / {current.max_score.toFixed(2)} ({percent}%)
          </span>
        </div>

        <select
          className={styles.jump}
          value={index}
          onChange={(e) => setIndex(Number(e.target.value))}
        >
          {students.map((s, i) => (
            <option key={s.hs} value={i}>
              {s.hs} — {s.score.toFixed(2)}đ
            </option>
          ))}
        </select>

        <Button
          variant="secondary"
          size="sm"
          disabled={index >= students.length - 1}
          onClick={() => setIndex((i) => Math.min(students.length - 1, i + 1))}
        >
          Sau →
        </Button>
      </header>

      <p className={styles.tip}>
        Dùng phím ← → để lướt qua cả lớp. Ảnh bên trái là đúng vùng máy đã cắt; chữ bên phải là
        thứ máy đọc ra — lệch nhau nghĩa là OCR sai, không phải học sinh sai.
      </p>

      {samples.map((sample) => {
        const cauKeys = Object.keys(regions).filter(
          (key) => questionOf(key) === sample.question_number,
        );
        cauKeys.forEach((key) => usedCauKeys.add(key));

        return (
          <section key={sample.sample_id} className={styles.question}>
            <div className={styles.questionHeader}>
              <span className={styles.questionTitle}>Câu {sample.question_number}</span>
              <span className={styles.questionScore}>
                {Number(sample.score ?? 0).toFixed(2)} / {Number(sample.max_score ?? 0).toFixed(2)}
              </span>
              <Badge tone={tone(sample.status)}>{label(sample.status)}</Badge>
            </div>

            {cauKeys.length > 0 && (
              <div className={styles.regions}>
                {cauKeys.map((key) => (
                  <RegionCard
                    key={key}
                    jobId={jobId}
                    hsKey={current.hs}
                    cauKey={key}
                    entry={regions[key]}
                  />
                ))}
              </div>
            )}

            <div className={styles.criteria}>
              {(sample.criterion_results ?? []).map((cr) => (
                <CriterionRow key={cr.criterion_id} cr={cr} />
              ))}
            </div>
          </section>
        );
      })}

      {/* Regions whose cau_key matches no graded question — usually a typo in
          roi_config, and invisible everywhere else in the UI. */}
      {(() => {
        const orphans = Object.keys(regions).filter((key) => !usedCauKeys.has(key));
        if (orphans.length === 0) return null;
        return (
          <section className={styles.question}>
            <div className={styles.questionHeader}>
              <span className={styles.questionTitle}>
                <IconChevronRight size={14} /> Vùng không khớp câu nào trong barem
              </span>
              <Badge tone="warning">{orphans.length}</Badge>
            </div>
            <div className={styles.regions}>
              {orphans.map((key) => (
                <RegionCard
                  key={key}
                  jobId={jobId}
                  hsKey={current.hs}
                  cauKey={key}
                  entry={regions[key]}
                />
              ))}
            </div>
          </section>
        );
      })()}
    </div>
  );
}
