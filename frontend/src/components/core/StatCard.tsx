import type { ReactNode } from "react";

import type { Tone } from "./Badge";
import styles from "./StatCard.module.css";

interface StatCardProps {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
}

export default function StatCard({ label, value, unit, hint, tone = "neutral", icon }: StatCardProps) {
  return (
    <div className={`${styles.card} ${styles[tone]}`}>
      <div className={styles.top}>
        <span className={styles.label}>{label}</span>
        {icon && <span className={styles.icon}>{icon}</span>}
      </div>
      <div className={styles.value}>
        {value}
        {unit && <span className={styles.unit}>{unit}</span>}
      </div>
      {hint && <div className={styles.hint}>{hint}</div>}
    </div>
  );
}
