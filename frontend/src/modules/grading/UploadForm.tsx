import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import Button from "@/components/core/Button";
import FileDrop from "@/components/core/FileDrop";
import { IconAlert, IconUpload } from "@/components/core/Icon";

import styles from "./UploadForm.module.css";

interface UploadFormProps {
  disabled: boolean;
  error?: string | null;
  onSubmit: (inputFile: File) => void;
}

/**
 * Start a grading run from a Results JSON that has already been OCR'd.
 *
 * No barem is picked here any more. Every student in the file declares their
 * own `ma_de`, so one file can hold several exam codes at once, and the server
 * looks up a rubric per code in the library. Asking the teacher to choose one
 * would be both redundant and wrong for a mixed-code batch.
 */
export default function UploadForm({ disabled, error, onSubmit }: UploadFormProps) {
  const [inputFiles, setInputFiles] = useState<File[]>([]);

  const inputFile = inputFiles[0] ?? null;
  const canSubmit = inputFile !== null && !disabled;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (inputFile) onSubmit(inputFile);
  }

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <FileDrop
        label="Bài làm học sinh — Results JSON đã OCR"
        hint="Mỗi học sinh phải khai ma_de của mình; hệ thống tự tìm barem khớp mã đề trong kho."
        accept=".json,application/json"
        disabled={disabled}
        files={inputFiles}
        onChange={setInputFiles}
      />

      <p className={styles.baremNote}>
        Không cần chọn barem. Một file chấm được nhiều mã đề cùng lúc — miễn là{" "}
        <Link to="/barem/kho" className={styles.baremLink}>
          kho barem
        </Link>{" "}
        có đủ rubric cho mọi mã đề xuất hiện trong file.
      </p>

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
