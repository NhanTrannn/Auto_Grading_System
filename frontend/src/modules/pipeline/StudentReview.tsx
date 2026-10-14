import { useEffect, useMemo, useState } from "react";

import Badge, { type Tone } from "@/components/core/Badge";
import Button from "@/components/core/Button";
import EmptyState from "@/components/core/EmptyState";
import { IconChevronRight, IconImage } from "@/components/core/Icon";
import { cropUrl, getJobEdits, overrideCriterionScore, saveOcrCorrection } from "@/services/pipelineApi";
import type { CriterionResult, GradingJobResult, GradingResultSample } from "@/types/grading";
import type { JobEdits, OcrCauEntry, OcrCorrection, OcrResultsFile } from "@/types/pipeline";

import styles from "./StudentReview.module.css";

interface StudentReviewProps {
  jobId: string;
  result: GradingJobResult;
  ocr: OcrResultsFile | null;
  /** Refetch the result after a score override (rejects on failure). */
  onResultChanged: () => Promise<void>;
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

const REVIEWER_KEY = "mmlab.reviewer";

function loadReviewer(): string {
  try {
    return localStorage.getItem(REVIEWER_KEY) ?? "";
  } catch {
    return "";
  }
}

function formatTime(iso: string | null): string {
  return iso ? new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleString("vi-VN") : "";
}

/**
 * The OCR reading, plus the teacher's correction when there is one.
 *
 * Correcting only records what the student really wrote; it does not
 * re-grade, since the score came from the misread text. That's why the
 * criterion rows below carry their own "Sửa điểm".
 */
function OcrBlock({
  text,
  correction,
  onSave,
}: {
  text: string;
  correction: OcrCorrection | undefined;
  onSave: (value: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(value: string) {
    setBusy(true);
    setError(null);
    try {
      await onSave(value);
      setEditing(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.readBox}>
      <span className={styles.readLabel}>Máy đọc được</span>
      <pre className={`${styles.readText} ${correction ? styles.readTextStale : ""}`}>{text || "(trống)"}</pre>

      {correction && !editing && (
        <>
          <span className={`${styles.readLabel} ${styles.fixedLabel}`}>
            Giáo viên sửa{correction.corrected_by ? ` · ${correction.corrected_by}` : ""}
            {correction.corrected_at ? ` · ${formatTime(correction.corrected_at)}` : ""}
          </span>
          <pre className={`${styles.readText} ${styles.fixedText}`}>{correction.text}</pre>
        </>
      )}

      {editing ? (
        <div className={styles.editBox}>
          <textarea
            className={styles.editArea}
            value={draft}
            rows={Math.min(10, Math.max(2, draft.split("\n").length))}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className={styles.editActions}>
            <Button size="sm" loading={busy} onClick={() => save(draft)}>
              Lưu
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setEditing(false)}>
              Huỷ
            </Button>
          </div>
        </div>
      ) : (
        <div className={styles.editActions}>
          <button
            type="button"
            className={styles.linkButton}
            onClick={() => {
              setDraft(correction?.text ?? text);
              setEditing(true);
            }}
          >
            {correction ? "Sửa lại" : "Sửa chữ máy đọc sai"}
          </button>
          {correction && (
            <button type="button" className={styles.linkButton} disabled={busy} onClick={() => save("")}>
              Bỏ bản sửa
            </button>
          )}
        </div>
      )}
      {error && <span className={styles.editError}>{error}</span>}
    </div>
  );
}

function RegionCard({
  jobId,
  hsKey,
  cauKey,
  entry,
  correction,
  onSaveOcr,
}: {
  jobId: string;
  hsKey: string;
  cauKey: string;
  entry: OcrCauEntry;
  correction: OcrCorrection | undefined;
  onSaveOcr: (cauKey: string, value: string) => Promise<void>;
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
        {correction && <Badge tone="accent">Đã sửa chữ</Badge>}
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
        <OcrBlock text={text} correction={correction} onSave={(value) => onSaveOcr(cauKey, value)} />
      </div>
    </div>
  );
}

/**
 * A criterion's verdict, with the teacher's score change on top of it.
 *
 * Overrides are applied by the backend to the result every screen reads, so
 * after saving, the parent just reloads that result — the totals here, the
 * results table and the PDF all move together.
 */
function CriterionRow({
  cr,
  onOverride,
}: {
  cr: CriterionResult;
  onOverride: (criterionId: string, score: number, note: string) => Promise<void>;
}) {
  const reasoning = typeof cr.llm_reasoning === "string" ? cr.llm_reasoning : null;
  const override = cr.teacher_override;
  const maxScore = Number(cr.max_score ?? 0);
  const [editing, setEditing] = useState(false);
  const [score, setScore] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(value: number, noteText: string) {
    setBusy(true);
    setError(null);
    try {
      await onOverride(cr.criterion_id, value, noteText);
      setEditing(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const parsed = Number(score.replace(",", "."));
  const valid = score.trim() !== "" && Number.isFinite(parsed) && parsed >= 0 && parsed <= maxScore;

  return (
    <div className={styles.criterion}>
      <div className={styles.criterionHeader}>
        <span className={styles.criterionId}>{cr.criterion_id}</span>
        <span className={styles.criterionScore}>
          {Number(cr.score ?? 0).toFixed(2)} / {maxScore.toFixed(2)}
        </span>
        <Badge tone={tone(cr.status)}>{label(cr.status)}</Badge>
        {override && <Badge tone="accent">GV đã sửa điểm</Badge>}
        {!editing && (
          <button
            type="button"
            className={`${styles.linkButton} ${styles.pushRight}`}
            onClick={() => {
              setScore(String(cr.score ?? 0));
              setNote("");
              setEditing(true);
            }}
          >
            Sửa điểm
          </button>
        )}
      </div>

      {override && (
        <div className={styles.overrideInfo}>
          Máy chấm <strong>{Number(cr.ai_score ?? 0).toFixed(2)}</strong> → giáo viên sửa thành{" "}
          <strong>{override.new_score.toFixed(2)}</strong>
          {override.created_by && <> · {override.created_by}</>}
          {override.created_at && <> · {formatTime(override.created_at)}</>}
          {override.note && <> — “{override.note}”</>}
          <button
            type="button"
            className={styles.linkButton}
            disabled={busy}
            onClick={() => submit(Number(cr.ai_score ?? 0), "Hoàn về điểm máy chấm")}
          >
            Hoàn về điểm máy chấm
          </button>
        </div>
      )}

      {editing && (
        <form
          className={styles.overrideForm}
          onSubmit={(e) => {
            e.preventDefault();
            if (valid) void submit(parsed, note.trim());
          }}
        >
          <label className={styles.overrideField}>
            Điểm mới (0 – {maxScore.toFixed(2)})
            <input
              className={styles.overrideInput}
              type="number"
              step={0.05}
              min={0}
              max={maxScore}
              value={score}
              autoFocus
              onChange={(e) => setScore(e.target.value)}
            />
          </label>
          <label className={`${styles.overrideField} ${styles.overrideNote}`}>
            Lý do (không bắt buộc)
            <input
              className={styles.overrideInput}
              value={note}
              placeholder="VD: OCR đọc sai, học sinh làm đúng"
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <Button size="sm" type="submit" loading={busy} disabled={!valid}>
            Lưu điểm
          </Button>
          <Button size="sm" variant="ghost" type="button" disabled={busy} onClick={() => setEditing(false)}>
            Huỷ
          </Button>
        </form>
      )}
      {error && <span className={styles.editError}>{error}</span>}

      {reasoning && <p className={styles.criterionReason}>{reasoning}</p>}
    </div>
  );
}

export default function StudentReview({ jobId, result, ocr, onResultChanged }: StudentReviewProps) {
  const [edits, setEdits] = useState<JobEdits["ocr_corrections"]>({});
  const [reviewer, setReviewer] = useState(loadReviewer);

  useEffect(() => {
    let cancelled = false;
    getJobEdits(jobId)
      .then((data) => {
        if (!cancelled) setEdits(data.ocr_corrections);
      })
      .catch(() => {
        // Non-fatal: the screen still works, just without earlier corrections shown.
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  function rememberReviewer(name: string) {
    setReviewer(name);
    try {
      localStorage.setItem(REVIEWER_KEY, name);
    } catch {
      // Remembered for this session only.
    }
  }

  async function handleSaveOcr(hsKey: string, cauKey: string, value: string) {
    await saveOcrCorrection(jobId, hsKey, cauKey, value, reviewer.trim());
    const data = await getJobEdits(jobId);
    setEdits(data.ocr_corrections);
  }

  async function handleOverride(hsKey: string, criterionId: string, score: number, note: string) {
    await overrideCriterionScore(jobId, hsKey, criterionId, score, note, reviewer.trim());
    await onResultChanged();
  }

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

      <div className={styles.tipRow}>
        <p className={styles.tip}>
          Dùng phím ← → để lướt qua cả lớp. Ảnh bên trái là đúng vùng máy đã cắt; chữ bên phải là
          thứ máy đọc ra — lệch nhau nghĩa là OCR sai, không phải học sinh sai. Sửa chữ chỉ để ghi lại
          bài làm đúng; muốn đổi điểm thì bấm “Sửa điểm” ở tiêu chí.
        </p>
        <label className={styles.reviewer}>
          Người soát
          <input
            className={styles.reviewerInput}
            value={reviewer}
            placeholder="Tên giáo viên"
            onChange={(e) => rememberReviewer(e.target.value)}
          />
        </label>
      </div>

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
                    correction={edits[current.hs]?.[key]}
                    onSaveOcr={(cauKey, value) => handleSaveOcr(current.hs, cauKey, value)}
                  />
                ))}
              </div>
            )}

            <div className={styles.criteria}>
              {(sample.criterion_results ?? []).map((cr) => (
                <CriterionRow
                  key={`${current.hs}:${cr.criterion_id}`}
                  cr={cr}
                  onOverride={(criterionId, score, note) => handleOverride(current.hs, criterionId, score, note)}
                />
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
                  correction={edits[current.hs]?.[key]}
                  onSaveOcr={(cauKey, value) => handleSaveOcr(current.hs, cauKey, value)}
                />
              ))}
            </div>
          </section>
        );
      })()}
    </div>
  );
}
