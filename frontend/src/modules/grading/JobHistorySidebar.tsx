import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

import Badge from "@/components/core/Badge";
import { listGradingJobs } from "@/services/api";
import type { GradingJobStatus } from "@/types/grading";

import styles from "./JobHistorySidebar.module.css";

const REFRESH_INTERVAL_MS = 5000;

const timeFormatter = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export default function JobHistorySidebar() {
  const [jobs, setJobs] = useState<GradingJobStatus[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function refresh() {
      try {
        const data = await listGradingJobs();
        if (!cancelled) {
          setJobs(data);
          setLoaded(true);
        }
      } catch {
        // Sidebar refresh failing silently is fine — the main content area
        // surfaces real errors for whatever job is actually being viewed.
      }
    }

    refresh();
    const timer = setInterval(refresh, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (jobs.length === 0) {
    return (
      <div className={styles.empty}>
        {loaded ? "Chưa có lần chấm nào." : "Đang tải lịch sử…"}
      </div>
    );
  }

  return (
    <div className={styles.list}>
      {jobs.map((job) => (
        <NavLink
          key={job.job_id}
          to={`/jobs/${job.job_id}`}
          className={({ isActive }) => `${styles.item} ${isActive ? styles.itemActive : ""}`}
        >
          <div className={styles.itemTop}>
            <span className={styles.jobId}>{job.job_id.slice(0, 8)}</span>
            <span className={styles.time}>{timeFormatter.format(new Date(job.created_at))}</span>
          </div>
          <Badge status={job.status} />
        </NavLink>
      ))}
    </div>
  );
}
