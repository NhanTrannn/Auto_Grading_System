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
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import Button from "@/components/core/Button";
import Card from "@/components/core/Card";
import EmptyState from "@/components/core/EmptyState";
import { IconAlert, IconCheck, IconDownload, IconFile, IconUpload } from "@/components/core/Icon";
import PageHeader from "@/components/core/PageHeader";
import { AdvancedModeProvider, useAdvancedToggle } from "@/modules/barem/advancedMode";
import ConfirmDelete from "@/components/core/ConfirmDelete";
import ExamMetaBar from "@/modules/barem/ExamMetaBar";
import ModeSwitch from "@/modules/barem/ModeSwitch";
import { makeQuestion } from "@/modules/barem/factory";
import { downloadExam, migrateExam, serialiseExam, type MigrationNote } from "@/modules/barem/migrate";
import QuestionEditor from "@/modules/barem/QuestionEditor";
import QuestionRail from "@/modules/barem/QuestionRail";
import StatusBar from "@/modules/barem/StatusBar";
import { useBaremDraft } from "@/modules/barem/useBaremDraft";
import { createBarem, updateBarem } from "@/services/baremApi";
import type { ExamRubric, QuestionPreset } from "@/types/barem";

import styles from "./BaremBuilderPage.module.css";

export default function BaremBuilderPage() {
  const draft = useBaremDraft();
  const location = useLocation();
  const [migrationNotes, setMigrationNotes] = useState<MigrationNote[] | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [openedBarem, setOpenedBarem] = useState<{ baremId: string; name: string } | null>(null);
  // Non-null while the "name this barem" box is open (first save of a draft).
  const [pendingName, setPendingName] = useState<string | null>(null);
  const [advanced, setAdvanced] = useAdvancedToggle();
  const fileInput = useRef<HTMLInputElement>(null);

  // The library hands a rubric over through router state rather than by writing
  // the autosave key behind this page's back, so the draft is replaced through
  // the normal path — which means "Hoàn tác" restores it. Only within the
  // session, though: the autosave overwrites storage moments later, so the
  // library asks for confirmation before navigating here at all.
  const incoming = location.state as { exam?: ExamRubric; baremId?: string; name?: string } | null;
  useEffect(() => {
    if (!incoming?.exam || !incoming.baremId) return;
    draft.replaceExam(incoming.exam);
    setOpenedBarem({ baremId: incoming.baremId, name: incoming.name ?? "" });
    setSaveMessage(null);
    setSaveError(null);
    setPendingName(null);
    window.history.replaceState({}, "");
    // Runs once per navigation carrying a rubric; draft is stable for the page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incoming?.baremId]);

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
   *
   * Saves back over the opened rubric, or creates a new one when editing a draft.
   * Always creating would turn "open from the library, fix a typo, save" into a
   * second copy with the same name — and the pickers list every copy, so the
   * next run is a coin flip over which one gets graded against.
   *
   * After the first save the editor keeps the rubric and links to the new
   * library entry, so the next save updates it. Saving used to clear the
   * editor instead, because there was no other way to start a fresh barem;
   * "Barem mới" now does that explicitly, so a teacher who saves halfway
   * through no longer has to go to the library to keep working.
   */
  async function saveToLibrary(name?: string) {
    setSaving(true);
    setSaveMessage(null);
    setSaveError(null);
    try {
      if (openedBarem) {
        const saved = await updateBarem(openedBarem.baremId, { content: exam });
        setSaveMessage(`Đã cập nhật “${saved.name}” trong kho (${saved.question_count} câu).`);
        return;
      }
      if (!name?.trim()) return;
      const saved = await createBarem(name.trim(), exam);
      setOpenedBarem({ baremId: saved.barem_id, name: saved.name });
      setPendingName(null);
      setSaveMessage(`Đã lưu “${saved.name}” vào kho (${saved.question_count} câu). Lần lưu sau sẽ cập nhật bản này.`);
    } catch (err) {
      setSaveError(`Lưu thất bại: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  function handleSaveClick() {
    if (openedBarem) void saveToLibrary();
    else setPendingName(`Mã đề ${exam.ma_de} — ${exam.subject}`);
  }

  /**
   * Start a blank rubric. `setOpenedBarem(null)` is load-bearing: leaving it
   * set would point the next save at the rubric that was just open, so the
   * blank one would overwrite it on the next click.
   */
  function startNewBarem() {
    draft.reset();
    setOpenedBarem(null);
    setPendingName(null);
    setMigrationNotes(null);
    setImportError(null);
    setSaveError(null);
    setSaveMessage(null);
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
            {exam.teacher_barem.length > 0 ? (
              <ConfirmDelete
                label="Barem mới"
                variant="secondary"
                size="md"
                armedLabel={openedBarem ? "Bấm lần nữa để mở barem trống" : "Bấm lần nữa — bản nháp sẽ bị dọn"}
                onConfirm={startNewBarem}
              />
            ) : null}
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
              onClick={handleSaveClick}
            >
              {openedBarem ? "Lưu thay đổi" : "Lưu vào kho"}
            </Button>
          </div>
        }
      />

      {openedBarem && (
        <p className={styles.openedBarem}>
          Đang sửa: <strong>{openedBarem.name}</strong>
        </p>
      )}

      {pendingName !== null && (
        <form
          className={styles.namePanel}
          onSubmit={(event) => {
            event.preventDefault();
            void saveToLibrary(pendingName);
          }}
        >
          <label className={styles.nameLabel}>
            Tên barem trong kho
            <input
              className={styles.nameInput}
              value={pendingName}
              autoFocus
              onChange={(event) => setPendingName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") setPendingName(null);
              }}
            />
          </label>
          <Button type="submit" size="sm" loading={saving} disabled={!pendingName.trim() || saving}>
            Lưu
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setPendingName(null)}>
            Huỷ
          </Button>
        </form>
      )}

      {saveMessage && (
        <div className={styles.saveMessage}>
          <IconCheck size={15} />
          {saveMessage}
        </div>
      )}

      {saveError && (
        <div className={styles.importError}>
          <IconAlert size={15} />
          {saveError}
        </div>
      )}

      <div className={styles.modeBar}>
        <ModeSwitch advanced={advanced} onChange={setAdvanced} />
      </div>

      {importError && (
        <div className={styles.importError}>
          <IconAlert size={15} />
          Không đọc được file: {importError}
        </div>
      )}

      <AdvancedModeProvider value={advanced}>
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
              takenNumbers={exam.teacher_barem.map((q) => q.question_number)}
              onChange={(next) => draft.updateQuestion(draft.activeQuestion!.question_number, () => next)}
              onRenumber={(next) => draft.changeQuestionNumber(draft.activeQuestion!.question_number, next)}
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
      </AdvancedModeProvider>

      <StatusBar
        report={report}
        declaredTotal={exam.total_score}
        json={serialiseExam(exam)}
        onJumpToQuestion={draft.setSelectedQuestion}
      />
    </>
  );
}
