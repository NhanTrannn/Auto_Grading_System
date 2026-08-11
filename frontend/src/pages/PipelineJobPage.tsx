import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import Button from "@/components/core/Button";
import Card from "@/components/core/Card";
import EmptyState from "@/components/core/EmptyState";
import { IconDownload, IconGrade, IconLayers, IconPlus, IconScan } from "@/components/core/Icon";
import PageHeader from "@/components/core/PageHeader";
import Spinner from "@/components/core/Spinner";
import Tabs, { type TabItem } from "@/components/core/Tabs";
import { downloadJson } from "@/modules/grading/downloadUtils";
import ResultsView from "@/modules/grading/ResultsView";
import LiveLogPanel from "@/modules/pipeline/LiveLogPanel";
import PipelineProgress from "@/modules/pipeline/PipelineProgress";
import StudentReview from "@/modules/pipeline/StudentReview";
import { usePipelineJob } from "@/modules/pipeline/usePipelineJob";
import { getPipelineOcrResult } from "@/services/pipelineApi";
import type { OcrResultsFile } from "@/types/pipeline";

type View = "table" | "review";

const TABS: TabItem<View>[] = [
  { id: "table", label: "Bảng điểm", hint: "Toàn lớp, lọc và tải về", icon: <IconGrade size={16} /> },
  { id: "review", label: "Soát bài", hint: "Từng học sinh, ảnh cắt + chữ OCR", icon: <IconScan size={16} /> },
];

export default function PipelineJobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { job, error, result, loading } = usePipelineJob(jobId ?? null);
  const [view, setView] = useState<View>("table");
  const [ocr, setOcr] = useState<OcrResultsFile | null>(null);

  const busy = job?.status === "pending" || job?.status === "running";
  // The intermediate Results JSON exists from the moment OCR finishes, so the
  // download is offered during grading too — not only at the very end.
  const ocrAvailable = job?.stage === "grading" || job?.status === "done";

  // The review screen needs the OCR text beside each crop; fetch it once the
  // OCR stage is past, independently of whether grading has finished.
  useEffect(() => {
    if (!jobId || !ocrAvailable || ocr) return;
    let cancelled = false;
    getPipelineOcrResult(jobId)
      .then((data) => {
        if (!cancelled) setOcr(data);
      })
      .catch(() => {
        // Non-fatal: the review screen falls back to "no crop/text".
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, ocrAvailable, ocr]);

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <IconLayers size={13} />
            Luồng tự động
          </>
        }
        title={`Phiên ${jobId?.slice(0, 12) ?? ""}`}
        description={
          job?.ma_de
            ? `Mã đề ${job.ma_de}${job.barem_name ? ` · barem ${job.barem_name}` : ""} — ảnh bài làm → OCR → chấm điểm.`
            : "Ảnh bài làm → OCR → chấm điểm. Trang tự cập nhật tiến độ, không cần tải lại."
        }
        actions={
          <>
            {ocrAvailable && (
              <Button
                variant="secondary"
                icon={<IconDownload size={15} />}
                onClick={async () =>
                  jobId && downloadJson(await getPipelineOcrResult(jobId), "results.json")
                }
              >
                Tải kết quả OCR
              </Button>
            )}
            <Button to="/pipeline" variant="secondary" icon={<IconPlus size={15} />}>
              Phiên mới
            </Button>
          </>
        }
      />

      {job && <PipelineProgress job={job} />}
      {jobId && <LiveLogPanel jobId={jobId} active={Boolean(busy)} />}

      {error && !job && (
        <Card>
          <EmptyState title="Không tải được phiên chấm" description={error} />
        </Card>
      )}

      {result ? (
        <>
          <div style={{ marginBottom: "var(--space-5)" }}>
            <Tabs items={TABS} active={view} onChange={setView} />
          </div>
          {view === "table" ? (
            <ResultsView result={result} />
          ) : (
            <StudentReview jobId={jobId as string} result={result} ocr={ocr} />
          )}
        </>
      ) : (
        !loading &&
        job?.status !== "failed" && (
          <Card>
            <EmptyState
              icon={busy ? <Spinner size={20} /> : <IconLayers size={20} />}
              title={busy ? "Đang xử lý cả lớp…" : "Chưa có kết quả"}
              description={
                busy
                  ? "OCR chạy 2 lượt cho mỗi vùng trả lời của mỗi học sinh, nên bước này là phần lâu nhất. Bạn có thể rời trang và quay lại sau."
                  : "Phiên này chưa có file kết quả để hiển thị."
              }
            />
          </Card>
        )
      )}
    </>
  );
}
