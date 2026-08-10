import { useRef, useState, type DragEvent, type ReactNode } from "react";

import { IconClose, IconFile } from "./Icon";
import styles from "./FileDrop.module.css";

interface FileDropProps {
  label: string;
  hint?: ReactNode;
  accept: string;
  multiple?: boolean;
  disabled?: boolean;
  files: File[];
  onChange: (files: File[]) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function FileDrop({
  label,
  hint,
  accept,
  multiple = false,
  disabled,
  files,
  onChange,
}: FileDropProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function accepted(list: FileList | null): File[] {
    if (!list) return [];
    return multiple ? Array.from(list) : Array.from(list).slice(0, 1);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    const next = accepted(e.dataTransfer.files);
    if (next.length) onChange(multiple ? [...files, ...next] : next);
  }

  function removeAt(index: number) {
    onChange(files.filter((_, i) => i !== index));
  }

  return (
    <div className={styles.field}>
      <label className={styles.label}>{label}</label>
      <div
        className={[styles.zone, dragging ? styles.dragging : "", disabled ? styles.disabled : ""]
          .filter(Boolean)
          .join(" ")}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        role="button"
        tabIndex={disabled ? -1 : 0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
      >
        <input
          ref={inputRef}
          className={styles.hiddenInput}
          type="file"
          accept={accept}
          multiple={multiple}
          disabled={disabled}
          onChange={(e) => {
            const next = accepted(e.target.files);
            if (next.length) onChange(multiple ? [...files, ...next] : next);
            e.target.value = "";
          }}
        />
        <span className={styles.zoneIcon}>
          <IconFile size={20} />
        </span>
        <span className={styles.zoneText}>
          <strong>Kéo thả</strong> hoặc bấm để chọn file
        </span>
        {hint && <span className={styles.hint}>{hint}</span>}
      </div>

      {files.length > 0 && (
        <ul className={styles.fileList}>
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`} className={styles.fileItem}>
              <span className={styles.fileIcon}>
                <IconFile size={14} />
              </span>
              <span className={styles.fileName} title={file.name}>
                {file.name}
              </span>
              <span className={styles.fileSize}>{formatBytes(file.size)}</span>
              <button
                type="button"
                className={styles.removeButton}
                onClick={() => removeAt(index)}
                disabled={disabled}
                aria-label={`Bỏ ${file.name}`}
              >
                <IconClose size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
