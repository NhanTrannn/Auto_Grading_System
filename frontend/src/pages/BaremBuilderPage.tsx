/**
 * Barem builder — author a rubric in the exact schema pipeline.py reads, with
 * the backend's own validation rules running live.
 *
 * A barem is the one artefact in this system that is hand-authored JSON, and
 * the failure mode is quiet: `load_barem()` accepts a criterion whose
 * `question_type` is outside the four it dispatches on, a `conditional_outputs`
 * with no `condition_source`, or a nested table format `_attach_table_slots()`
 * cannot read — and every one of those grades wrong rather than erroring. This
 * page exists so those land as visible errors while writing, not as a suspicious
 * score sheet after a paid LLM run.
 *
 * Layout: exam fields as a bar on top, a narrow question rail on the left, and
 * everything else given to the editor — question editing is the dense part
 * (tables, nested criteria, conditional branches), so it gets the width, while
 * validation lives in a sticky strip that stays visible however far you scroll.
 */
import { useMemo, useRef, useState } from "react";

import Button from "@/components/core/Button";
import Card from "@/components/core/Card";
import EmptyState from "@/components/core/EmptyState";
import { IconAlert, IconCheck, IconDownload, IconFile, IconUpload } from "@/components/core/Icon";
import PageHeader from "@/components/core/PageHeader";
import ExamMetaBar from "@/modules/barem/ExamMetaBar";
import { makeQuestion } from "@/modules/barem/factory";
import { downloadExam, migrateExam, serialiseExam, type MigrationNote } from "@/modules/barem/migrate";
import QuestionEditor from "@/modules/barem/QuestionEditor";
import QuestionRail from "@/modules/barem/QuestionRail";
import StatusBar from "@/modules/barem/StatusBar";
import { useBaremDraft } from "@/modules/barem/useBaremDraft";
import { createBarem } from "@/services/baremApi";
import type { QuestionPreset } from "@/types/barem";

import styles from "./BaremBuilderPage.module.css";

export default function BaremBuilderPage() {
  const draft = useBaremDraft();
  const [migrationNotes, setMigrationNotes] = useState<MigrationNote[] | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const { exam, report } = draft;

  const errorQuestions = useMemo(
    () =>
      new Set(
        report.errors
          .map((issue) => issue.questionNumber)
          .filter((n): n is number => n !== undefined),
      ),
    [report.errors],
  );

  const nextQuestionNumber =
    exam.teacher_barem.length === 0
      ? 1
      : Math.max(...exam.teacher_barem.map((q) => q.question_number)) + 1;

  async function handleImport(file: File) {
    setImportError(null);
    setMigrationNotes(null);
    try {
      const text = await file.text();
      const { exam: imported, notes } = migrateExam(JSON.parse(text));
      draft.replaceExam(imported);
      setMigrationNotes(notes);
    } catch (err) {
      setImportError((err as Error).message);
    }
  }

  function addQuestion(preset: QuestionPreset) {
    draft.addQuestion(makeQuestion(preset, nextQuestionNumber));
  }

  /**
   * Push the current rubric into the server-side library so a grading run can
   * pick it without exporting a file first. Saved even when validation has
   * warnings — the library is a working shelf, and `load_barem()` reports the
   * same problems again at grading time anyway.
   */
  async function handleSaveToLibrary() {
    setSaving(true);
    setSaveMessage(null);
    try {
      const name =
        window.prompt("Tên barem để lưu vào thư viện:", `Mã đề ${exam.ma_de} — ${exam.subject}`) ??
        "";
      if (!name.trim()) return;
      const saved = await createBarem(name.trim(), exam);
      setSaveMessage(`Đã lưu “${saved.name}” vào thư viện (${saved.question_count} câu).`);
    } catch (err) {
      setSaveMessage(`Lưu thất bại: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <IconFile size={13} />
            Soạn barem
          </>
        }
        title="Trình soạn barem chấm điểm"
        description="Soạn rubric đúng schema pipeline.py đọc, kiểm tra ngay bằng chính luật validate_barem() của backend, rồi xuất ra sample_parem.json dùng thẳng cho phiên chấm."
        actions={
          <div className={styles.headerActions}>
            <input
              ref={fileInput}
              type="file"
              accept="application/json,.json"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleImport(file);
                event.target.value = "";
              }}
            />
            {draft.canUndo && (
              <Button variant="ghost" onClick={draft.undo}>
                Hoàn tác
              </Button>
            )}
            <Button variant="secondary" icon={<IconUpload size={15} />} onClick={() => fileInput.current?.click()}>
              Nạp barem
            </Button>
            <Button
              variant="secondary"
              icon={<IconDownload size={15} />}
              disabled={exam.teacher_barem.length === 0}
              onClick={() => downloadExam(exam)}
            >
              Xuất file
            </Button>
            <Button
              icon={<IconCheck size={15} />}
              disabled={exam.teacher_barem.length === 0 || saving}
              loading={saving}
              onClick={handleSaveToLibrary}
            >
              Lưu vào thư viện
            </Button>
          </div>
        }
      />

      {saveMessage && (
        <div className={styles.saveMessage}>
          <IconCheck size={15} />
          {saveMessage}
        </div>
      )}

      {importError && (
        <div className={styles.importError}>
          <IconAlert size={15} />
          Không đọc được file: {importError}
        </div>
      )}

      <div className={styles.metaBar}>
        <ExamMetaBar
          maDe={exam.ma_de}
          subject={exam.subject}
          totalScore={exam.total_score}
          computedTotal={report.computedTotal}
          onChange={draft.updateMeta}
        />
      </div>

      {migrationNotes && migrationNotes.length > 0 && (
        <div className={styles.notes}>
          <Card
            title="Đã chuyển đổi khi nạp file"
            subtitle="Barem cũ dùng schema khác với cái pipeline.py đọc — những thay đổi dưới đây đã được áp dụng tự động"
            actions={
              <Button size="sm" variant="ghost" onClick={() => setMigrationNotes(null)}>
                Ẩn
              </Button>
            }
          >
            <ul className={styles.noteList}>
              {migrationNotes.map((note, index) => (
                <li key={index}>
                  <span className={styles.noteWhere}>{note.where}</span>
                  <span>{note.message}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}

      <div className={styles.layout}>
        <aside className={styles.rail}>
          <QuestionRail
            questions={exam.teacher_barem}
            selected={draft.selectedQuestion}
            errorQuestions={errorQuestions}
            onSelect={draft.setSelectedQuestion}
            onAdd={addQuestion}
          />
        </aside>

        <main className={styles.editor}>
          {draft.activeQuestion ? (
            <QuestionEditor
              question={draft.activeQuestion}
              onChange={(next) => draft.updateQuestion(draft.activeQuestion!.question_number, () => next)}
              onRemove={() => draft.removeQuestion(draft.activeQuestion!.question_number)}
              onDuplicate={() => draft.duplicateQuestion(draft.activeQuestion!.question_number)}
            />
          ) : (
            <div className={styles.emptyWrap}>
              <EmptyState
                icon={<IconFile size={26} />}
                title="Chưa chọn câu nào"
                description={
                  exam.teacher_barem.length === 0
                    ? "Bấm 'Thêm câu' ở cột trái để tạo câu đầu tiên, hoặc nạp một sample_parem.json có sẵn để chỉnh sửa."
                    : "Chọn một câu ở cột trái để bắt đầu chỉnh sửa."
                }
              />
            </div>
          )}
        </main>
      </div>

      <StatusBar
        report={report}
        declaredTotal={exam.total_score}
        json={serialiseExam(exam)}
        onJumpToQuestion={draft.setSelectedQuestion}
      />
    </>
  );
}
