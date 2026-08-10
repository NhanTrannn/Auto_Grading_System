import { useMemo } from "react";

import type { StudentSummary } from "@/types/grading";

import styles from "./ScoreDistribution.module.css";

const BUCKET_COUNT = 5;

/** Histogram of students per score band, drawn with plain CSS (no chart lib). */
export default function ScoreDistribution({ summary }: { summary: StudentSummary[] }) {
  const buckets = useMemo(() => {
    const maxScore = summary[0]?.max_score ?? 0;
    const width = maxScore / BUCKET_COUNT;
    const counts = Array.from({ length: BUCKET_COUNT }, () => 0);

    summary.forEach((s) => {
      if (!maxScore) return;
      const index = Math.min(BUCKET_COUNT - 1, Math.floor(s.score / width));
      counts[index] += 1;
    });

    return counts.map((count, index) => ({
      count,
      from: width * index,
      to: width * (index + 1),
      percentLabel: `${index * (100 / BUCKET_COUNT)}–${(index + 1) * (100 / BUCKET_COUNT)}%`,
    }));
  }, [summary]);

  const peak = Math.max(1, ...buckets.map((b) => b.count));

  if (summary.length === 0) {
    return <p className={styles.empty}>Chưa có dữ liệu.</p>;
  }

  return (
    <div className={styles.chart}>
      {buckets.map((bucket, index) => (
        <div key={index} className={styles.column}>
          <div className={styles.barArea}>
            <span className={styles.count}>{bucket.count}</span>
            <span
              className={`${styles.bar} ${styles[`band${index}`]}`}
              style={{ height: `${(bucket.count / peak) * 100}%` }}
            />
          </div>
          <span className={styles.rangeLabel}>{bucket.percentLabel}</span>
          <span className={styles.scoreLabel}>
            {bucket.from.toFixed(1)}–{bucket.to.toFixed(1)}
          </span>
        </div>
      ))}
    </div>
  );
}
