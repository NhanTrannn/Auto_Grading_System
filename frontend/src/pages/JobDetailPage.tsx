import { useParams } from "react-router-dom";

import Button from "@/components/core/Button";
import Card from "@/components/core/Card";
import EmptyState from "@/components/core/EmptyState";
import { IconGrade, IconPlus } from "@/components/core/Icon";
import PageHeader from "@/components/core/PageHeader";
import Spinner from "@/components/core/Spinner";
import JobStatusView from "@/modules/grading/JobStatusView";
import ResultsView from "@/modules/grading/ResultsView";
import { useJobStatus } from "@/modules/grading/useJobStatus";

export default function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { status, error, result, loading } = useJobStatus(jobId ?? null);

  const busy = status === "pending" || status === "running";

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <IconGrade size={13} />
            Kết quả chấm điểm
          </>
        }
        title={`Phiên ${jobId?.slice(0, 12) ?? ""}`}
        description="Bảng điểm tổng hợp toàn lớp. Bấm vào một học sinh để xem điểm và lý do chấm của LLM cho từng tiêu chí."
        actions={
          <Button to="/" variant="secondary" icon={<IconPlus size={15} />}>
            Phiên chấm mới
          </Button>
        }
      />

      <JobStatusView jobId={jobId ?? null} status={status} error={error} />

      {result ? (
        <ResultsView result={result} />
      ) : (
        !loading && (
          <Card>
            <EmptyState
              icon={busy ? <Spinner size={20} /> : <IconGrade size={20} />}
              title={busy ? "Đang chấm bài…" : "Chưa có kết quả"}
              description={
                busy
                  ? "Trang sẽ tự cập nhật ngay khi tiến trình chấm hoàn tất — bạn không cần tải lại."
                  : "Phiên chấm này chưa có file kết quả để hiển thị."
              }
            />
          </Card>
        )
      )}
    </>
  );
}
