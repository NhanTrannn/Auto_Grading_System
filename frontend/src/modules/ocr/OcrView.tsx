import { useEffect, useMemo, useState } from "react";

import Badge from "@/components/core/Badge";
import Button from "@/components/core/Button";
import Card from "@/components/core/Card";
import EmptyState from "@/components/core/EmptyState";
import FileDrop from "@/components/core/FileDrop";
import { IconAlert, IconDownload, IconText } from "@/components/core/Icon";
import { downloadJson } from "@/modules/grading/downloadUtils";
import { runOcr } from "@/services/ocrApi";
import type { OcrResult, OcrTaskType } from "@/types/ocr";

import OcrContent from "./OcrContent";
import styles from "./OcrView.module.css";

const TASK_TYPES: { id: OcrTaskType; label: string; hint: string }[] = [
  { id: "short_text", label: "Chữ ngắn", hint: "Điền vào chỗ trống, 1–2 dòng" },
  { id: "long_text", label: "Đoạn dài", hint: "Diễn giải nhiều dòng" },
  { id: "code", label: "Mã C++", hint: "Giữ nguyên cú pháp, thứ tự dòng" },
  { id: "table", label: "Bảng", hint: "Cần khai số hàng và số cột" },
];

export default function OcrView() {
  const [files, setFiles] = useState<File[]>([]);
  const [taskType, setTaskType] = useState<OcrTaskType>("short_text");
  const [nRows, setNRows] = useState(3);
  const [nCols, setNCols] = useState(2);
  const [result, setResult] = useState<OcrResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const preview = useMemo(
    () => (files[0] ? URL.createObjectURL(files[0]) : null),
    [files],
  );
  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  const tableInvalid = taskType === "table" && (nRows < 1 || nCols < 1);

  async function handleRun() {
    if (!files[0] || tableInvalid) return;
    setRunning(true);
    setError(null);
    try {
      setResult(await runOcr(files[0], taskType, nRows, nCols));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className={styles.layout}>
      <Card title="Ảnh cần nhận dạng" subtitle="Một ảnh crop của đúng một vùng trả lời">
        <div className={styles.form}>
          <FileDrop
            label="Ảnh crop"
            hint="Định dạng .jpg, .png"
            accept="image/png,image/jpeg"
            disabled={running}
            files={files}
            onChange={(next) => {
              setFiles(next);
              setResult(null);
            }}
          />

          <div className={styles.field}>
            <span className={styles.label}>Loại nội dung</span>
            <div className={styles.taskGrid}>
              {TASK_TYPES.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`${styles.taskOption} ${taskType === t.id ? styles.taskActive : ""}`}
                  onClick={() => setTaskType(t.id)}
                  disabled={running}
                >
                  <span className={styles.taskLabel}>{t.label}</span>
                  <span className={styles.taskHint}>{t.hint}</span>
                </button>
              ))}
            </div>
          </div>

          {taskType === "table" && (
            <div className={styles.dims}>
              <label className={styles.dimField}>
                <span className={styles.label}>Số hàng dữ liệu</span>
                <input
                  className={styles.numberInput}
                  type="number"
                  min={1}
                  value={nRows}
                  disabled={running}
                  onChange={(e) => setNRows(Number(e.target.value))}
                />
              </label>
              <label className={styles.dimField}>
                <span className={styles.label}>Số cột dữ liệu</span>
                <input
                  className={styles.numberInput}
                  type="number"
                  min={1}
                  value={nCols}
                  disabled={running}
                  onChange={(e) => setNCols(Number(e.target.value))}
                />
              </label>
            </div>
          )}

          {error && (
            <div className={styles.error}>
              <IconAlert size={15} />
              <span>{error}</span>
            </div>
          )}

          <Button
            onClick={handleRun}
            disabled={files.length === 0 || tableInvalid}
            loading={running}
            icon={<IconText size={15} />}
            block
          >
            {running ? "Đang nhận dạng…" : "Nhận dạng chữ viết"}
          </Button>

          <p className={styles.note}>
            Chạy 2 lượt: trích xuất rồi tự soát lại (self-reflection) bằng Qwen3-VL qua API —{" "}
            <strong>mỗi lần chạy đều tốn chi phí LLM thật</strong>.
          </p>

          {preview && (
            <div className={styles.previewBox}>
              <span className={styles.label}>Xem trước</span>
              <img className={styles.previewImage} src={preview} alt="Ảnh crop" />
            </div>
          )}
        </div>
      </Card>

      {!result ? (
        <Card>
          <EmptyState
            icon={<IconText size={20} />}
            title="Chưa có kết quả OCR"
            description="Chọn ảnh crop và loại nội dung tương ứng, kết quả 2 lượt sẽ hiển thị cạnh nhau để đối chiếu."
          />
        </Card>
      ) : (
        <div className={styles.results}>
          <div className={styles.summary}>
            <Badge tone={result.status === "completed" ? "success" : "danger"}>
              {result.status === "completed" ? "Nhận dạng thành công" : "Thất bại cả 2 lượt"}
            </Badge>
            <span className={styles.confidence}>
              Độ tin cậy: <strong>{(result.confidence ?? 0).toFixed(2)}</strong>
            </span>
            <Button
              variant="secondary"
              size="sm"
              icon={<IconDownload size={14} />}
              onClick={() => downloadJson(result, "ocr_result.json")}
            >
              Tải JSON
            </Button>
          </div>

          {result.structure_warning && (
            <div className={styles.warning}>
              <IconAlert size={15} />
              <span>{result.structure_warning}</span>
            </div>
          )}

          <div className={styles.passes}>
            <Card title="Lượt 2 — kết quả cuối" subtitle="Sau bước tự soát lại">
              <OcrContent content={result.content} />
            </Card>
            <Card title="Lượt 1 — trích xuất thô" subtitle="Trước khi tự soát lại">
              <OcrContent content={result.pass1_content} />
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
