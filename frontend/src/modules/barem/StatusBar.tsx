/**
 * Sticky strip pinned to the bottom of the page: error/warning counts always
 * visible, with the full validation report or the JSON preview expanding above
 * it on demand.
 *
 * Validation used to live in the side column, which meant it competed for space
 * with the editor while usually showing nothing worth a whole panel. As a strip
 * it stays in view no matter how far down a long question you scroll — which is
 * what you want from a live validator — and only takes real estate when you ask
 * for the detail.
 */
import { useState } from "react";

import { IconAlert, IconCheck, IconClose } from "@/components/core/Icon";
import type { ValidationReport } from "@/types/barem";

import styles from "./StatusBar.module.css";
import ValidationPanel from "./ValidationPanel";

type Panel = "validate" | "json";

interface StatusBarProps {
  report: ValidationReport;
  declaredTotal: number;
  json: string;
  onJumpToQuestion: (questionNumber: number) => void;
}

export default function StatusBar({ report, declaredTotal, json, onJumpToQuestion }: StatusBarProps) {
  const [open, setOpen] = useState<Panel | null>(null);
  const clean = report.errors.length === 0 && report.warnings.length === 0;

  function toggle(panel: Panel) {
    setOpen((current) => (current === panel ? null : panel));
  }

  return (
    <div className={styles.wrapper}>
      {open && (
        <div className={styles.panel}>
          <div className={styles.panelHead}>
            <span className={styles.panelTitle}>
              {open === "validate" ? "Kết quả kiểm tra" : "sample_parem.json"}
            </span>
            <button type="button" className={styles.close} onClick={() => setOpen(null)} aria-label="Đóng">
              <IconClose size={14} />
            </button>
          </div>
          <div className={styles.panelBody}>
            {open === "validate" ? (
              <ValidationPanel
                report={report}
                declaredTotal={declaredTotal}
                onJumpToQuestion={(questionNumber) => {
                  onJumpToQuestion(questionNumber);
                  setOpen(null);
                }}
              />
            ) : (
              <pre className={styles.json}>{json}</pre>
            )}
          </div>
        </div>
      )}

      <div className={styles.strip}>
        <div className={styles.counts}>
          {clean ? (
            <span className={`${styles.pill} ${styles.pillOk}`}>
              <IconCheck size={13} />
              Barem hợp lệ
            </span>
          ) : (
            <>
              <span
                className={`${styles.pill} ${report.errors.length ? styles.pillError : styles.pillMuted}`}
              >
                <IconAlert size={13} />
                {report.errors.length} lỗi
              </span>
              <span
                className={`${styles.pill} ${report.warnings.length ? styles.pillWarn : styles.pillMuted}`}
              >
                {report.warnings.length} cảnh báo
              </span>
            </>
          )}
        </div>

        <div className={styles.actions}>
          <button
            type="button"
            className={`${styles.tab} ${open === "validate" ? styles.tabActive : ""}`}
            onClick={() => toggle("validate")}
          >
            Chi tiết kiểm tra
          </button>
          <button
            type="button"
            className={`${styles.tab} ${open === "json" ? styles.tabActive : ""}`}
            onClick={() => toggle("json")}
          >
            Xem JSON
          </button>
        </div>
      </div>
    </div>
  );
}
