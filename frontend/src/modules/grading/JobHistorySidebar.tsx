import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

import Badge from "@/components/core/Badge";
import { listGradingJobs } from "@/services/api";
import { listPipelineJobs } from "@/services/pipelineApi";
import type { JobStatus } from "@/types/grading";

import styles from "./JobHistorySidebar.module.css";

const REFRESH_INTERVAL_MS = 5000;

const timeFormatter = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

/** Both job kinds share one list, distinguished by the badge and their link. */
interface HistoryEntry {
  jobId: string;
  status: JobStatus;
  createdAt: string;
  kind: "pipeline" | "grading";
  to: string;
}

export default function JobHistorySidebar() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function refresh() {
      // allSettled: one backend list failing must not blank out the other.
      const [gradingRes, pipelineRes] = await Promise.allSettled([
        listGradingJobs(),
        listPipelineJobs(),
      ]);
      if (cancelled) return;

      const merged: HistoryEntry[] = [];
      if (gradingRes.status === "fulfilled") {
        gradingRes.value.forEach((job) =>
          merged.push({
            jobId: job.job_id,
            status: job.status,
            createdAt: job.created_at,
            kind: "grading",
            to: `/jobs/${job.job_id}`,
          }),
        );
      }
      if (pipelineRes.status === "fulfilled") {
        pipelineRes.value.forEach((job) =>
          merged.push({
            jobId: job.job_id,
            status: job.status,
            createdAt: job.created_at,
            kind: "pipeline",
            to: `/pipeline/${job.job_id}`,
          }),
        );
      }

      merged.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
      setEntries(merged);
      setLoaded(true);
    }

    refresh();
    const timer = setInterval(refresh, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (entries.length === 0) {
    return (
      <div className={styles.empty}>{loaded ? "Chưa có lần chấm nào." : "Đang tải lịch sử…"}</div>
    );
  }

  return (
    <div className={styles.list}>
      {entries.map((entry) => (
        <NavLink
          key={`${entry.kind}-${entry.jobId}`}
          to={entry.to}
          className={({ isActive }) => `${styles.item} ${isActive ? styles.itemActive : ""}`}
        >
          <div className={styles.itemTop}>
            <span className={styles.jobId}>{entry.jobId.slice(0, 8)}</span>
            <span className={styles.time}>{timeFormatter.format(new Date(entry.createdAt))}</span>
          </div>
          <div className={styles.itemBottom}>
            <Badge status={entry.status} />
            <span className={styles.kind}>{entry.kind === "pipeline" ? "Từ ảnh" : "Từ JSON"}</span>
          </div>
        </NavLink>
      ))}
    </div>
  );
}
