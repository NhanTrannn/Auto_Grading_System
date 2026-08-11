import { useState, type FormEvent } from "react";

import Button from "@/components/core/Button";
import FileDrop from "@/components/core/FileDrop";
import { IconAlert, IconUpload } from "@/components/core/Icon";
import BaremPicker from "@/modules/barem/BaremPicker";

import styles from "./UploadForm.module.css";

interface UploadFormProps {
  disabled: boolean;
  error?: string | null;
  onSubmit: (inputFile: File, baremId: string) => void;
}

/**
 * Start a grading run from a Results JSON that has already been OCR'd.
 *
 * The barem is chosen from the library rather than uploaded alongside: it is
 * the same rubric the pipeline flow uses, saved once from the builder, so
 * asking for the file again every run only invites grading against a stale
 * copy. The picker can still take a new `.json`, which adds it to the library
 * on the way in.
 */
export default function UploadForm({ disabled, error, onSubmit }: UploadFormProps) {
  const [inputFiles, setInputFiles] = useState<File[]>([]);
  const [baremId, setBaremId] = useState<string | null>(null);

  const inputFile = inputFiles[0] ?? null;
  const canSubmit = inputFile !== null && baremId !== null && !disabled;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (inputFile && baremId) onSubmit(inputFile, baremId);
  }

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.step}>
        <span className={styles.stepLabel}>1 · Bài làm học sinh</span>
        <FileDrop
          label="Results JSON đã OCR"
          hint="File .json có khoá HS_1, HS_2, … — xuất từ luồng OCR hoặc từ phiên chấm cả lớp"
          accept=".json,application/json"
          disabled={disabled}
          files={inputFiles}
          onChange={setInputFiles}
        />
      </div>

      <div className={styles.step}>
        <span className={styles.stepLabel}>2 · Barem</span>
        <BaremPicker value={baremId} onChange={(id) => setBaremId(id)} />
      </div>

      {error && (
        <div className={styles.error}>
          <IconAlert size={15} />
          <span>{error}</span>
        </div>
      )}

      <div className={styles.footer}>
        <p className={styles.notice}>
          Mỗi lần chấm sẽ <strong>gọi LLM thật</strong> cho từng tiêu chí — có phát sinh chi phí API.
        </p>
        <Button type="submit" size="lg" disabled={!canSubmit} loading={disabled} icon={<IconUpload size={16} />}>
          {disabled ? "Đang gửi…" : "Bắt đầu chấm"}
        </Button>
      </div>
    </form>
  );
}
