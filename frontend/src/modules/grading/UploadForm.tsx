import { useState, type FormEvent } from "react";

import Button from "@/components/core/Button";
import FileDrop from "@/components/core/FileDrop";
import { IconAlert, IconUpload } from "@/components/core/Icon";

import styles from "./UploadForm.module.css";

interface UploadFormProps {
  disabled: boolean;
  error?: string | null;
  onSubmit: (inputFile: File, baremFile: File) => void;
}

export default function UploadForm({ disabled, error, onSubmit }: UploadFormProps) {
  const [inputFiles, setInputFiles] = useState<File[]>([]);
  const [baremFiles, setBaremFiles] = useState<File[]>([]);

  const inputFile = inputFiles[0] ?? null;
  const baremFile = baremFiles[0] ?? null;
  const canSubmit = inputFile !== null && baremFile !== null && !disabled;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (inputFile && baremFile) onSubmit(inputFile, baremFile);
  }

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.grid}>
        <FileDrop
          label="Bài làm học sinh — Results JSON"
          hint="File .json xuất từ OCR (khoá HS_1, HS_2, …)"
          accept=".json,application/json"
          disabled={disabled}
          files={inputFiles}
          onChange={setInputFiles}
        />
        <FileDrop
          label="Barem chấm điểm — JSON"
          hint="File barem/rubric .json (vd: sample_parem.json)"
          accept=".json,application/json"
          disabled={disabled}
          files={baremFiles}
          onChange={setBaremFiles}
        />
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
