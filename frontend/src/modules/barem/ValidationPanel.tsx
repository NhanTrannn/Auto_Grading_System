/**
 * Validation report, split by severity.
 *
 * Errors and warnings are separated because they mean different things on the
 * backend: an error is something `load_barem()` refuses or that provably
 * mis-grades, a warning is something that loads fine but is probably not what
 * the author meant. Collapsing them into one list would make a blocking problem
 * look like a style note.
 */
import Badge from "@/components/core/Badge";
import { IconAlert, IconCheck } from "@/components/core/Icon";
import type { ValidationIssue, ValidationReport } from "@/types/barem";

import styles from "./ValidationPanel.module.css";

interface ValidationPanelProps {
  report: ValidationReport;
  declaredTotal: number;
  onJumpToQuestion: (questionNumber: number) => void;
}

function IssueList({
  issues,
  onJump,
}: {
  issues: ValidationIssue[];
  onJump: (questionNumber: number) => void;
}) {
  return (
    <ul className={styles.list}>
      {issues.map((issue, index) => (
        <li key={index} className={styles.item}>
          {issue.questionNumber !== undefined ? (
            <button type="button" className={styles.jump} onClick={() => onJump(issue.questionNumber!)}>
              Câu {issue.questionNumber}
            </button>
          ) : (
            <span className={styles.globalTag}>Toàn barem</span>
          )}
          <span className={styles.message}>{issue.message}</span>
        </li>
      ))}
    </ul>
  );
}

export default function ValidationPanel({ report, declaredTotal, onJumpToQuestion }: ValidationPanelProps) {
  const totalMatches = Math.abs(report.computedTotal - declaredTotal) <= 0.01;

  return (
    <div className={styles.wrapper}>
      <div className={styles.summary}>
        <div className={`${styles.totals} ${totalMatches ? styles.totalsOk : styles.totalsBad}`}>
          <span className={styles.totalsLabel}>Tổng điểm tính từ tiêu chí</span>
          <span className={styles.totalsValue}>
            {report.computedTotal.toFixed(2)}
            <span className={styles.totalsDeclared}> / {declaredTotal.toFixed(2)} khai báo</span>
          </span>
        </div>
        <div className={styles.counts}>
          <Badge tone={report.errors.length ? "danger" : "success"} dot={false}>
            {report.errors.length} lỗi
          </Badge>
          <Badge tone={report.warnings.length ? "warning" : "neutral"} dot={false}>
            {report.warnings.length} cảnh báo
          </Badge>
        </div>
      </div>

      {report.errors.length === 0 && report.warnings.length === 0 && (
        <div className={styles.clean}>
          <IconCheck size={16} />
          Barem hợp lệ — <code>load_barem()</code> sẽ nạp được mà không báo lỗi.
        </div>
      )}

      {report.errors.length > 0 && (
        <section className={styles.section}>
          <h3 className={`${styles.sectionTitle} ${styles.errorTitle}`}>
            <IconAlert size={14} />
            Lỗi — chặn chạy
          </h3>
          <IssueList issues={report.errors} onJump={onJumpToQuestion} />
        </section>
      )}

      {report.warnings.length > 0 && (
        <section className={styles.section}>
          <h3 className={`${styles.sectionTitle} ${styles.warnTitle}`}>
            <IconAlert size={14} />
            Cảnh báo — nạp được nhưng có thể chấm sai ý
          </h3>
          <IssueList issues={report.warnings} onJump={onJumpToQuestion} />
        </section>
      )}
    </div>
  );
}
