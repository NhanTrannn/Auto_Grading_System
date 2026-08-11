/**
 * Small labelled form controls shared across the barem editors.
 *
 * Kept local to the barem module rather than promoted to components/core: the
 * rest of the app is read-only dashboards and upload forms, so these are the
 * only dense data-entry controls in the codebase and have no second caller yet.
 */
import type { ReactNode } from "react";

import styles from "./Field.module.css";

interface FieldProps {
  label: ReactNode;
  hint?: ReactNode;
  /** Marks a field the backend requires — not HTML validation, just a cue. */
  required?: boolean;
  children: ReactNode;
}

export function Field({ label, hint, required, children }: FieldProps) {
  return (
    <label className={styles.field}>
      <span className={styles.label}>
        {label}
        {required && <span className={styles.required}>*</span>}
      </span>
      {children}
      {hint && <span className={styles.hint}>{hint}</span>}
    </label>
  );
}

interface TextInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  mono?: boolean;
  disabled?: boolean;
}

export function TextInput({ value, onChange, placeholder, mono, disabled }: TextInputProps) {
  return (
    <input
      className={`${styles.input} ${mono ? styles.mono : ""}`}
      value={value}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

interface NumberInputProps {
  value: number | null | undefined;
  onChange: (value: number | null) => void;
  step?: number;
  min?: number;
  placeholder?: string;
  /** Allow clearing to null — only valid for scores inside all_or_nothing groups. */
  nullable?: boolean;
}

export function NumberInput({ value, onChange, step = 0.25, min, placeholder, nullable }: NumberInputProps) {
  return (
    <input
      className={`${styles.input} ${styles.number}`}
      type="number"
      step={step}
      min={min}
      placeholder={placeholder}
      value={value ?? ""}
      onChange={(event) => {
        const raw = event.target.value;
        if (raw === "") {
          onChange(nullable ? null : 0);
          return;
        }
        const parsed = Number(raw);
        onChange(Number.isFinite(parsed) ? parsed : 0);
      }}
    />
  );
}

interface TextAreaProps {
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  placeholder?: string;
  mono?: boolean;
}

export function TextArea({ value, onChange, rows = 3, placeholder, mono }: TextAreaProps) {
  return (
    <textarea
      className={`${styles.input} ${styles.textarea} ${mono ? styles.mono : ""}`}
      rows={rows}
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

interface SelectProps<T extends string> {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}

export function Select<T extends string>({ value, options, onChange }: SelectProps<T>) {
  return (
    <select
      className={`${styles.input} ${styles.select}`}
      value={value}
      onChange={(event) => onChange(event.target.value as T)}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

interface ListInputProps {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  rows?: number;
  hint?: ReactNode;
}

/**
 * One entry per line, trimmed, blanks dropped.
 *
 * Suits keywords — they are single words searched as substrings, so a stray
 * space is always a typo and a newline inside one is meaningless. Accepted
 * answers and output tokens need `EntryListInput` below instead: those are
 * compared byte-for-byte and may legitimately span lines, which this control
 * cannot represent at all.
 */

export function ListInput({ value, onChange, placeholder, rows = 3 }: ListInputProps) {
  return (
    <textarea
      className={`${styles.input} ${styles.textarea} ${styles.mono}`}
      rows={rows}
      placeholder={placeholder}
      value={value.join("\n")}
      onChange={(event) =>
        onChange(
          event.target.value
            .split(/\r?\n/)
            .map((line) => line.trim())
            .filter(Boolean),
        )
      }
    />
  );
}

interface EntryListInputProps {
  value: string[];
  onChange: (value: string[]) => void;
  /** One textarea per entry, so an entry may itself span several lines. */
  multiline?: boolean;
  /** Number each row — use where the array's order changes grading. */
  ordered?: boolean;
  placeholder?: string;
  addLabel?: string;
  emptyLabel?: string;
}

/**
 * A list of strings held **exactly** as typed, one control per entry.
 *
 * `ListInput` above cannot express these two fields. It is a single textarea
 * split on newlines, so (a) an entry can never contain a newline — a two-line
 * expected answer becomes two separate one-line answers, neither of which the
 * student can match — and (b) it `.trim()`s every line, silently deleting
 * leading/trailing spaces that `_check_exact_output_match` compares
 * byte-for-byte. Nothing is trimmed or dropped here; an entry that is empty or
 * has edge whitespace gets flagged instead, since both are usually a slip but
 * occasionally deliberate.
 */
export function EntryListInput({
  value,
  onChange,
  multiline,
  ordered,
  placeholder,
  addLabel = "Thêm dòng",
  emptyLabel = "Chưa có dòng nào.",
}: EntryListInputProps) {
  const replace = (index: number, next: string) =>
    onChange(value.map((entry, i) => (i === index ? next : entry)));
  const remove = (index: number) => onChange(value.filter((_, i) => i !== index));
  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= value.length) return;
    const next = [...value];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  return (
    <div className={styles.entryList}>
      {value.length === 0 && <p className={styles.entryEmpty}>{emptyLabel}</p>}

      {value.map((entry, index) => {
        const edgeSpace = entry !== entry.trim() && entry.trim() !== "";
        return (
          <div key={index} className={styles.entryRow}>
            {ordered && <span className={styles.entryIndex}>{index + 1}</span>}
            <div className={styles.entryBody}>
              {multiline ? (
                <textarea
                  className={`${styles.input} ${styles.textarea} ${styles.mono}`}
                  rows={Math.min(6, Math.max(1, entry.split("\n").length))}
                  value={entry}
                  placeholder={placeholder}
                  onChange={(event) => replace(index, event.target.value)}
                />
              ) : (
                <input
                  className={`${styles.input} ${styles.mono}`}
                  value={entry}
                  placeholder={placeholder}
                  onChange={(event) => replace(index, event.target.value)}
                />
              )}
              {entry === "" && <span className={styles.entryFlag}>Dòng rỗng — sẽ được lưu nguyên vào barem.</span>}
              {edgeSpace && (
                <span className={styles.entryFlag}>
                  Có khoảng trắng ở đầu/cuối — được giữ nguyên và tính vào so khớp.
                </span>
              )}
            </div>
            <div className={styles.entryActions}>
              {ordered && (
                <>
                  <button
                    type="button"
                    className={styles.entryButton}
                    onClick={() => move(index, -1)}
                    disabled={index === 0}
                    title="Lên"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className={styles.entryButton}
                    onClick={() => move(index, 1)}
                    disabled={index === value.length - 1}
                    title="Xuống"
                  >
                    ↓
                  </button>
                </>
              )}
              <button
                type="button"
                className={`${styles.entryButton} ${styles.entryRemove}`}
                onClick={() => remove(index)}
                title="Xoá"
              >
                ✕
              </button>
            </div>
          </div>
        );
      })}

      <button type="button" className={styles.entryAdd} onClick={() => onChange([...value, ""])}>
        + {addLabel}
      </button>
    </div>
  );
}

interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
}

export function Checkbox({ checked, onChange, label, hint }: CheckboxProps) {
  return (
    <label className={styles.checkbox}>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>
        <span className={styles.checkboxLabel}>{label}</span>
        {hint && <span className={styles.hint}>{hint}</span>}
      </span>
    </label>
  );
}

export function Row({ children }: { children: ReactNode }) {
  return <div className={styles.row}>{children}</div>;
}
