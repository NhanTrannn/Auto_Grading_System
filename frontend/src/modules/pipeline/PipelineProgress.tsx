import Badge from "@/components/core/Badge";
import { IconAlert, IconCheck, IconScan, IconText } from "@/components/core/Icon";
import Spinner from "@/components/core/Spinner";
import type { PipelineJobStatus, PipelineStage } from "@/types/pipeline";

import styles from "./PipelineProgress.module.css";

const STAGES: { id: PipelineStage; label: string; detail: string; icon: JSX.Element }[] = [
  {
    id: "ocr",
    label: "Nhận dạng bài làm",
    detail: "Căn chỉnh từng trang, cắt vùng và OCR chữ viết tay",
    icon: <IconScan size={16} />,
  },
  {
    id: "grading",
    label: "Chấm điểm",
    detail: "Chấm toàn bộ kết quả OCR theo barem bằng LLM",
    icon: <IconText size={16} />,
  },
];

type StageState = "waiting" | "active" | "done";

function stageStateOf(stage: PipelineStage, job: PipelineJobStatus): StageState {
  if (job.status === "done") return "done";
  const order: PipelineStage[] = ["ocr", "grading", "done"];
  const current = job.stage ?? "ocr";
  const currentIndex = order.indexOf(current);
  const thisIndex = order.indexOf(stage);
  if (thisIndex < currentIndex) return "done";
  if (thisIndex === currentIndex) return "active";
  return "waiting";
}

export default function PipelineProgress({ job }: { job: PipelineJobStatus }) {
  const percent =
    job.progress_total > 0
      ? Math.min(100, Math.round((job.progress_done / job.progress_total) * 100))
      : 0;

  const failed = job.status === "failed";
  const finished = job.status === "done";

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <Badge status={job.status} />
        <span className={styles.summary}>
          {job.student_count} học sinh · {job.roi_count} vùng/trang
        </span>
        <code className={styles.jobId}>{job.job_id}</code>
      </div>

      {!failed && (
        <>
          <div className={styles.barRow}>
            <span className={styles.barTrack}>
              <span
                className={`${styles.barFill} ${finished ? styles.barDone : ""}`}
                style={{ width: `${finished ? 100 : percent}%` }}
              />
            </span>
            <span className={styles.percent}>{finished ? 100 : percent}%</span>
          </div>

          <div className={styles.counter}>
            {finished ? (
              "Đã hoàn tất toàn bộ luồng."
            ) : (
              <>
                {job.progress_done} / {job.progress_total} vùng
                {job.progress_message && <span className={styles.message}> · {job.progress_message}</span>}
              </>
            )}
          </div>
        </>
      )}

      <ol className={styles.stages}>
        {STAGES.map((stage) => {
          const state = failed ? "waiting" : stageStateOf(stage.id, job);
          return (
            <li key={stage.id} className={`${styles.stage} ${styles[state]}`}>
              <span className={styles.stageIcon}>
                {state === "active" ? <Spinner size={15} /> : state === "done" ? <IconCheck size={15} /> : stage.icon}
              </span>
              <span className={styles.stageText}>
                <span className={styles.stageLabel}>{stage.label}</span>
                <span className={styles.stageDetail}>{stage.detail}</span>
              </span>
            </li>
          );
        })}
      </ol>

      {failed && job.error && (
        <div className={styles.error}>
          <IconAlert size={16} />
          <pre className={styles.errorText}>{job.error}</pre>
        </div>
      )}
    </div>
  );
}
