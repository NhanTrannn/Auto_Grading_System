import type { ReactNode } from "react";

import type { JobStatus } from "@/types/grading";

import styles from "./Badge.module.css";

export type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "accent";

const JOB_LABEL: Record<JobStatus, string> = {
  pending: "Đang xếp hàng",
  running: "Đang chấm",
  done: "Hoàn tất",
  failed: "Thất bại",
};

const JOB_TONE: Record<JobStatus, Tone> = {
  pending: "warning",
  running: "info",
  done: "success",
  failed: "danger",
};

interface BadgeProps {
  /** Shorthand: render a grading-job status with its canonical label + tone. */
  status?: JobStatus;
  tone?: Tone;
  dot?: boolean;
  pulse?: boolean;
  children?: ReactNode;
}

export default function Badge({ status, tone, dot = true, pulse, children }: BadgeProps) {
  const resolvedTone: Tone = tone ?? (status ? JOB_TONE[status] : "neutral");
  const label = children ?? (status ? JOB_LABEL[status] : null);
  const animate = pulse ?? status === "running";

  return (
    <span className={`${styles.badge} ${styles[resolvedTone]}`}>
      {dot && <span className={`${styles.dot} ${animate ? styles.pulse : ""}`} />}
      {label}
    </span>
  );
}
