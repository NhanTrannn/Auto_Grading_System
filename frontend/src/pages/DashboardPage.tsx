import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import Badge from "@/components/core/Badge";
import Card from "@/components/core/Card";
import EmptyState from "@/components/core/EmptyState";
import {
  IconChevronRight,
  IconGrade,
  IconHistory,
  IconSparkles,
} from "@/components/core/Icon";
import PageHeader from "@/components/core/PageHeader";
import StatCard from "@/components/core/StatCard";
import UploadForm from "@/modules/grading/UploadForm";
import { createGradingJob, listGradingJobs } from "@/services/api";
import type { GradingJobStatus } from "@/types/grading";

import styles from "./DashboardPage.module.css";

const dateFormatter = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

// What this page actually does — it starts from a Results JSON that already
// exists. The card used to open with "Ảnh bài làm → Pipeline OCR", which
// belongs to /pipeline: no image is read here and no ROI is declared, so a
// teacher landing here was told to expect a step that never runs.
const GRADING_STEPS = [
  { title: "Results JSON", detail: "Bài làm đã OCR, khoá theo HS_N" },
  { title: "Chọn barem", detail: "Lấy từ thư viện đã lưu" },
  { title: "Chấm từng tiêu chí", detail: "Heuristic + LLM Chain-of-Thought" },
  { title: "Bảng điểm", detail: "Điểm và lý do cho từng học sinh" },
];

export default function DashboardPage() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<GradingJobStatus[]>([]);

  useEffect(() => {
    let cancelled = false;
    listGradingJobs()
      .then((data) => {
        if (!cancelled) setJobs(data);
      })
      .catch(() => {
        // Overview stats are best-effort; the sidebar shows connection state.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const stats = useMemo(() => {
    const done = jobs.filter((j) => j.status === "done").length;
    const running = jobs.filter((j) => j.status === "running" || j.status === "pending").length;
    const failed = jobs.filter((j) => j.status === "failed").length;
    return { total: jobs.length, done, running, failed };
  }, [jobs]);

  const recentJobs = jobs.slice(0, 5);

  async function handleSubmit(inputFile: File, baremId: string) {
    setSubmitting(true);
    setError(null);
    try {
      const job = await createGradingJob(inputFile, baremId);
      navigate(`/jobs/${job.job_id}`);
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <IconSparkles size={13} />
            Bảng điều khiển
          </>
        }
        title="Chấm điểm tự động IT001"
        description="Tải lên bài làm đã OCR cùng barem, hệ thống sẽ chấm từng tiêu chí bằng heuristic kết hợp LLM Chain-of-Thought và trả về điểm chi tiết cho từng học sinh."
      />

      <div className={styles.stats}>
        <StatCard
          label="Tổng phiên chấm"
          value={stats.total}
          tone="accent"
          icon={<IconHistory size={16} />}
        />
        <StatCard label="Hoàn tất" value={stats.done} tone="success" />
        <StatCard label="Đang chạy" value={stats.running} tone="info" />
        <StatCard label="Thất bại" value={stats.failed} tone="danger" />
      </div>

      <div className={styles.columns}>
        <Card
          title="Tạo phiên chấm mới"
          subtitle="Cần đúng 2 file JSON: bài làm học sinh và barem"
        >
          <UploadForm disabled={submitting} error={error} onSubmit={handleSubmit} />
        </Card>

        <div className={styles.side}>
          <Card title="Luồng xử lý" subtitle="Chấm từ file JSON đã có sẵn">
            <ol className={styles.pipeline}>
              {GRADING_STEPS.map((step, index) => (
                <li key={step.title} className={styles.pipelineStep}>
                  <span className={styles.stepIndex}>{index + 1}</span>
                  <span className={styles.stepText}>
                    <span className={styles.stepTitle}>{step.title}</span>
                    <span className={styles.stepDetail}>{step.detail}</span>
                  </span>
                </li>
              ))}
            </ol>
            <p className={styles.pipelineNote}>
              Chưa có file JSON? Bắt đầu từ ảnh bài làm ở{" "}
              <Link to="/pipeline" className={styles.pipelineLink}>
                Chấm cả lớp từ ảnh
              </Link>{" "}
              — nơi đó mới chạy OCR (khai vùng, căn trang, nhận dạng chữ) rồi chấm luôn.
            </p>
          </Card>

          <Card title="Phiên gần đây" padded={false}>
            {recentJobs.length === 0 ? (
              <EmptyState
                compact
                icon={<IconGrade size={20} />}
                title="Chưa có phiên chấm nào"
                description="Phiên chấm đầu tiên của bạn sẽ hiện ở đây."
              />
            ) : (
              <ul className={styles.recentList}>
                {recentJobs.map((job) => (
                  <li key={job.job_id}>
                    <button
                      type="button"
                      className={styles.recentItem}
                      onClick={() => navigate(`/jobs/${job.job_id}`)}
                    >
                      <span className={styles.recentMain}>
                        <span className={styles.recentId}>{job.job_id.slice(0, 12)}</span>
                        <span className={styles.recentTime}>
                          {dateFormatter.format(new Date(job.created_at))}
                        </span>
                      </span>
                      <Badge status={job.status} />
                      <IconChevronRight size={15} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
