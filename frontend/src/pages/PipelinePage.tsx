import { useState } from "react";
import { useNavigate } from "react-router-dom";

import Card from "@/components/core/Card";
import { IconLayers } from "@/components/core/Icon";
import PageHeader from "@/components/core/PageHeader";
import PipelineUploadForm from "@/modules/pipeline/PipelineUploadForm";
import { createPipelineJob } from "@/services/pipelineApi";
import type { RoiConfigEntry } from "@/types/pipeline";

import styles from "./PipelinePage.module.css";

const EXAMPLE_TREE = `HKI2025_2026/
└─ Made_1/
   └─ Bai_lam/
      ├─ HS_2/   page_1.png  page_2.png  …
      └─ HS_10/  page_1.png  page_2.png  …`;

const EXAMPLE_CONFIG = `{
  "rois": [
    { "cau_key": "Cau_01", "page": 1,
      "x": 124, "y": 210, "w": 232, "h": 71, "task_type": "short_text" },
    { "cau_key": "Cau_15b_1", "page": 6,
      "x": 100, "y": 900, "w": 500, "h": 200,
      "task_type": "table", "n_rows": 3, "n_cols": 2 },
    { "cau_key": "Cau_13c", "page": 5,
      "x": 100, "y": 1200, "w": 400, "h": 300, "task_type": "diagram" }
  ]
}`;

export default function PipelinePage() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(input: {
    uploadId: string;
    maDe: string;
    baremId: string;
    rois: RoiConfigEntry[];
  }) {
    setSubmitting(true);
    setError(null);
    try {
      const job = await createPipelineJob(input);
      navigate(`/pipeline/${job.job_id}`);
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
            <IconLayers size={13} />
            Luồng tự động
          </>
        }
        title="Chấm cả lớp từ ảnh bài làm"
        description="Đưa nguyên hai file zip vào — ảnh đề mẫu và thư mục bài làm cả lớp. Hệ thống căn chỉnh từng trang về khung đề, cắt và OCR mọi vùng trả lời, rồi chấm toàn bộ theo barem đã chọn."
      />

      <PipelineUploadForm disabled={submitting} error={error} onSubmit={handleSubmit} />

      <div className={styles.help}>
        <Card
          title="Cấu trúc file zip và roi_config"
          subtitle="Đường dẫn ảnh do hệ thống tự điền — bạn chỉ khai vùng"
        >
          <p className={styles.helpText}>
            <strong>Zip đề mẫu</strong> chứa ảnh các trang đề chưa làm; thứ tự trang lấy theo tên
            file (<code>image_2</code> đứng trước <code>image_10</code>).{" "}
            <strong>Zip bài làm</strong> giữ nguyên cây thư mục sẵn có, mỗi học sinh một thư mục:
          </p>
          <pre className={styles.snippet}>{EXAMPLE_TREE}</pre>
          <p className={styles.helpText}>
            Tên thư mục học sinh được đổi sang <code>HS_&lt;số&gt;</code> để khớp quy ước của
            pipeline — bảng ở bước 2 hiện rõ ai thành mã nào trước khi chạy.
          </p>

          <p className={styles.helpText}>
            Nếu tự khai <code>roi_config.json</code>: mỗi phần tử trong <code>rois</code> cần{" "}
            <code>cau_key</code> theo quy ước <code>Cau_XX</code> / <code>Cau_XXa_N</code> của
            barem, <code>page</code> (trang mấy của đề), toạ độ <code>x/y/w/h</code> đo trên ảnh
            đề mẫu, và <code>task_type</code> là một trong <code>short_text</code>,{" "}
            <code>long_text</code>, <code>code</code>, <code>table</code>, <code>diagram</code>.
            Vùng bảng bắt buộc thêm <code>n_rows</code> và <code>n_cols</code>.
          </p>
          <pre className={styles.snippet}>{EXAMPLE_CONFIG}</pre>
          <p className={styles.helpText}>
            Không muốn viết tay thì chọn <em>Gán vùng trên ảnh</em> ở bước 4: Module 1 quét ra các
            khung, bạn bấm từng khung để gán câu (danh sách câu lấy sẵn từ barem đã chọn), hoặc
            kéo chuột để vẽ thêm vùng Module 1 bỏ sót.
          </p>
        </Card>
      </div>
    </>
  );
}
