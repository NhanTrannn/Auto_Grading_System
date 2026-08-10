import Badge from "@/components/core/Badge";
import { IconAlert } from "@/components/core/Icon";
import Spinner from "@/components/core/Spinner";
import type { JobStatus } from "@/types/grading";

import styles from "./JobStatusView.module.css";

interface JobStatusViewProps {
  jobId: string | null;
  status: JobStatus | null;
  error: string | null;
}

const HINT: Record<JobStatus, string> = {
  pending: "Phiên chấm đã được tạo, đang chờ tiến trình chấm khởi động.",
  running: "Đang gọi LLM cho từng tiêu chí — với lớp nhiều học sinh, việc này có thể mất vài phút.",
  done: "Đã chấm xong. Kết quả hiển thị bên dưới.",
  failed: "Tiến trình chấm dừng giữa chừng. Xem chi tiết lỗi bên dưới.",
};

export default function JobStatusView({ jobId, status, error }: JobStatusViewProps) {
  if (!status) {
    return (
      <div className={styles.bar}>
        <Spinner />
        <span className={styles.hint}>Đang tải trạng thái phiên chấm…</span>
      </div>
    );
  }

  const busy = status === "pending" || status === "running";

  return (
    <div className={`${styles.bar} ${busy ? styles.busy : ""}`}>
      {busy && <Spinner />}
      <Badge status={status} />
      <span className={styles.hint}>{HINT[status]}</span>
      {jobId && <code className={styles.jobId}>{jobId}</code>}

      {error && (
        <div className={styles.error}>
          <IconAlert size={15} />
          <pre className={styles.errorText}>{error}</pre>
        </div>
      )}
    </div>
  );
}
