import { useEffect, useMemo, useState } from "react";

import Badge from "@/components/core/Badge";
import Button from "@/components/core/Button";
import Card from "@/components/core/Card";
import EmptyState from "@/components/core/EmptyState";
import FileDrop from "@/components/core/FileDrop";
import { IconAlert, IconDownload, IconLayers } from "@/components/core/Icon";
import StatCard from "@/components/core/StatCard";
import { alignImages } from "@/services/ocrApi";
import type { AlignResult } from "@/types/ocr";

import styles from "./AlignView.module.css";

const ERROR_HINT: Record<string, string> = {
  FEATURE_ERROR: "Không trích được đặc trưng ORB — ảnh quá mờ, quá tối hoặc sai định dạng.",
  MATCH_ERROR: "Quá ít cặp điểm khớp giữa hai ảnh — có thể không cùng một trang đề.",
  HOMOGRAPHY_ERROR: "Không ước lượng được phép biến đổi hình học từ các cặp điểm khớp.",
  GEOMETRY_WARP_ERROR: "Phép biến đổi tìm được bị méo bất thường, kết quả không dùng được.",
  HOUGH_SKEW_ERROR: "Ảnh sau căn chỉnh vẫn nghiêng quá ngưỡng cho phép.",
};

export default function AlignView() {
  const [templateFiles, setTemplateFiles] = useState<File[]>([]);
  const [studentFiles, setStudentFiles] = useState<File[]>([]);
  const [result, setResult] = useState<AlignResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overlay, setOverlay] = useState(50);

  const templatePreview = useMemo(
    () => (templateFiles[0] ? URL.createObjectURL(templateFiles[0]) : null),
    [templateFiles],
  );
  useEffect(() => {
    return () => {
      if (templatePreview) URL.revokeObjectURL(templatePreview);
    };
  }, [templatePreview]);

  const alignedSrc = result?.image_base64 ? `data:image/png;base64,${result.image_base64}` : null;

  async function handleRun() {
    if (!templateFiles[0] || !studentFiles[0]) return;
    setRunning(true);
    setError(null);
    try {
      setResult(await alignImages(templateFiles[0], studentFiles[0]));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  }

  function downloadAligned() {
    if (!alignedSrc) return;
    const a = document.createElement("a");
    a.href = alignedSrc;
    a.download = "aligned.png";
    a.click();
  }

  const inlierRate = result && result.matches ? Math.round((result.inliers / result.matches) * 100) : 0;

  return (
    <div className={styles.layout}>
      <Card title="Ảnh đầu vào" subtitle="Ảnh đề mẫu và ảnh bài làm cùng một trang">
        <div className={styles.form}>
          <FileDrop
            label="Ảnh template (đề mẫu)"
            accept="image/png,image/jpeg"
            disabled={running}
            files={templateFiles}
            onChange={(next) => {
              setTemplateFiles(next);
              setResult(null);
            }}
          />
          <FileDrop
            label="Ảnh bài làm học sinh"
            accept="image/png,image/jpeg"
            disabled={running}
            files={studentFiles}
            onChange={(next) => {
              setStudentFiles(next);
              setResult(null);
            }}
          />
          {error && (
            <div className={styles.error}>
              <IconAlert size={15} />
              <span>{error}</span>
            </div>
          )}
          <Button
            onClick={handleRun}
            disabled={!templateFiles[0] || !studentFiles[0]}
            loading={running}
            icon={<IconLayers size={15} />}
            block
          >
            {running ? "Đang căn chỉnh…" : "Căn chỉnh ảnh"}
          </Button>
          <p className={styles.note}>
            ORB + RANSAC homography (OpenCV). Ảnh kết quả luôn được đưa về đúng kích thước ảnh
            template, nên toạ độ ROI từ Module 1 dùng lại được nguyên vẹn.
          </p>
        </div>
      </Card>

      {!result ? (
        <Card>
          <EmptyState
            icon={<IconLayers size={20} />}
            title="Chưa căn chỉnh ảnh nào"
            description="Chọn ảnh template và ảnh bài làm, kết quả sẽ hiện kèm thanh trượt so sánh chồng ảnh."
          />
        </Card>
      ) : (
        <div className={styles.results}>
          <div className={styles.stats}>
            <StatCard
              label="Kết quả"
              value={result.error ? "Không đạt" : "Đạt"}
              tone={result.error ? "danger" : "success"}
            />
            <StatCard label="Cặp khớp" value={result.matches} tone="info" />
            <StatCard
              label="Inliers"
              value={result.inliers}
              hint={`${inlierRate}% số cặp khớp`}
              tone="accent"
            />
            <StatCard label="Độ nghiêng" value={result.skew?.toFixed?.(2) ?? result.skew} unit="°" tone="warning" />
            <StatCard label="Kích thước" value={`${result.width}×${result.height}`} />
          </div>

          {result.error && (
            <div className={styles.alignError}>
              <IconAlert size={16} />
              <div>
                <div className={styles.alignErrorTitle}>
                  <Badge tone="danger">{result.error.error_type}</Badge>
                </div>
                <p className={styles.alignErrorText}>
                  {ERROR_HINT[result.error.error_type] ?? result.error.reason}
                </p>
                <p className={styles.alignErrorRaw}>{result.error.reason}</p>
              </div>
            </div>
          )}

          {alignedSrc && (
            <Card
              title="So sánh chồng ảnh"
              subtitle="Kéo thanh trượt để chuyển giữa ảnh template và ảnh đã căn chỉnh"
              actions={
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<IconDownload size={14} />}
                  onClick={downloadAligned}
                >
                  Tải ảnh đã căn
                </Button>
              }
            >
              <div className={styles.sliderRow}>
                <span className={styles.sliderLabel}>Template</span>
                <input
                  className={styles.slider}
                  type="range"
                  min={0}
                  max={100}
                  value={overlay}
                  onChange={(e) => setOverlay(Number(e.target.value))}
                />
                <span className={styles.sliderLabel}>Đã căn chỉnh</span>
              </div>

              <div className={styles.compare}>
                {templatePreview && (
                  <img className={styles.compareBase} src={templatePreview} alt="Template" />
                )}
                <img
                  className={styles.compareOverlay}
                  src={alignedSrc}
                  alt="Ảnh đã căn chỉnh"
                  style={{ opacity: overlay / 100 }}
                />
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
