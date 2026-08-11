/**
 * Exam-level fields as one compact horizontal bar.
 *
 * `ma_de`, `subject` and `total_score` are three short values edited once per
 * barem and then left alone, so they don't earn a card in the working column —
 * they sit above the editor where they stay visible without competing for the
 * space the question editor actually needs.
 */
import styles from "./ExamMetaBar.module.css";

interface ExamMetaBarProps {
  maDe: string;
  subject: string;
  totalScore: number;
  /** Score summed from the criteria — shown next to the declared total. */
  computedTotal: number;
  onChange: (patch: { ma_de?: string; subject?: string; total_score?: number }) => void;
}

export default function ExamMetaBar({
  maDe,
  subject,
  totalScore,
  computedTotal,
  onChange,
}: ExamMetaBarProps) {
  const matches = Math.abs(computedTotal - totalScore) <= 0.01;

  return (
    <div className={styles.bar}>
      <label className={styles.field} style={{ flex: "0 0 92px" }}>
        <span className={styles.label}>ma_de</span>
        <input
          className={`${styles.input} ${styles.mono}`}
          value={maDe}
          onChange={(event) => onChange({ ma_de: event.target.value })}
        />
      </label>

      <label className={`${styles.field} ${styles.grow}`}>
        <span className={styles.label}>subject</span>
        <input
          className={styles.input}
          value={subject}
          placeholder="IT001 - Nhập môn lập trình"
          onChange={(event) => onChange({ subject: event.target.value })}
        />
      </label>

      <label className={styles.field} style={{ flex: "0 0 108px" }}>
        <span className={styles.label}>total_score</span>
        <input
          className={`${styles.input} ${styles.mono}`}
          type="number"
          step={0.25}
          value={totalScore}
          onChange={(event) => onChange({ total_score: Number(event.target.value) || 0 })}
        />
      </label>

      <div className={`${styles.tally} ${matches ? styles.tallyOk : styles.tallyBad}`}>
        <span className={styles.label}>Tính từ tiêu chí</span>
        <span className={styles.tallyValue}>{computedTotal.toFixed(2)}</span>
      </div>
    </div>
  );
}
