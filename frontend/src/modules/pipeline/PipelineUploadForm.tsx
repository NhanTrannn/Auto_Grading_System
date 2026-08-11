import { useEffect, useMemo, useState, type ReactNode } from "react";

import Badge from "@/components/core/Badge";
import Button from "@/components/core/Button";
import Card from "@/components/core/Card";
import FileDrop from "@/components/core/FileDrop";
import { IconAlert, IconCheck, IconClose, IconLayers, IconScan } from "@/components/core/Icon";
import StatCard from "@/components/core/StatCard";
import { getBarem } from "@/services/baremApi";
import { createUpload } from "@/services/pipelineApi";
import type { ExamRubric } from "@/types/barem";
import type { BaremSummary } from "@/types/baremLibrary";
import type { RoiConfigEntry, UploadInventory, UploadMaDe } from "@/types/pipeline";

import BaremPicker from "@/modules/barem/BaremPicker";
import { suggestCauKeys } from "./cauKeySuggestions";
import styles from "./PipelineUploadForm.module.css";
import RoiMapper from "./RoiMapper";
import {
  TASK_TYPE_LABEL,
  countByTaskType,
  estimateOcrCalls,
  parseRoiConfigFile,
  validateRois,
} from "./roiConfigUtils";

interface PipelineUploadFormProps {
  disabled: boolean;
  error?: string | null;
  onSubmit: (input: {
    uploadId: string;
    maDe: string;
    baremId: string;
    rois: RoiConfigEntry[];
  }) => void;
}

type RoiSource = "file" | "editor";

function Step({
  index,
  title,
  subtitle,
  done,
  children,
}: {
  index: number;
  title: string;
  subtitle?: string;
  done?: boolean;
  children: ReactNode;
}) {
  return (
    <Card
      title={
        <span className={styles.stepTitle}>
          <span className={`${styles.stepIndex} ${done ? styles.stepIndexDone : ""}`}>
            {done ? <IconCheck size={13} /> : index}
          </span>
          {title}
        </span>
      }
      subtitle={subtitle}
    >
      {children}
    </Card>
  );
}

export default function PipelineUploadForm({
  disabled,
  error,
  onSubmit,
}: PipelineUploadFormProps) {
  const [templateZip, setTemplateZip] = useState<File[]>([]);
  const [studentsZip, setStudentsZip] = useState<File[]>([]);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState<string | null>(null);
  const [inventory, setInventory] = useState<UploadInventory | null>(null);

  const [maDe, setMaDe] = useState<string | null>(null);
  const [barem, setBarem] = useState<BaremSummary | null>(null);
  const [rubric, setRubric] = useState<ExamRubric | null>(null);

  const [roiSource, setRoiSource] = useState<RoiSource>("editor");
  const [rois, setRois] = useState<RoiConfigEntry[]>([]);
  const [roiFileError, setRoiFileError] = useState<string | null>(null);
  const [mapperOpen, setMapperOpen] = useState(false);

  // The ROI editor's cau_key picker is driven by the chosen barem, so pull the
  // full rubric (the listing endpoint deliberately omits `content`).
  useEffect(() => {
    if (!barem) {
      setRubric(null);
      return;
    }
    let cancelled = false;
    getBarem(barem.barem_id)
      .then((detail) => {
        if (!cancelled) setRubric(detail.content);
      })
      .catch(() => {
        if (!cancelled) setRubric(null);
      });
    return () => {
      cancelled = true;
    };
  }, [barem]);

  const suggestions = useMemo(() => suggestCauKeys(rubric), [rubric]);

  const selectedMaDe: UploadMaDe | null =
    inventory?.ma_de_list.find((g) => g.ma_de === maDe) ?? null;
  const pageCount = inventory?.template_pages.length ?? 0;
  const issues = useMemo(
    () => (rois.length ? validateRois(rois, pageCount) : []),
    [rois, pageCount],
  );
  const taskCounts = useMemo(() => countByTaskType(rois), [rois]);
  const ocrCalls = estimateOcrCalls(rois, selectedMaDe?.student_count ?? 0);

  async function handleRead() {
    if (!templateZip[0] || !studentsZip[0]) return;
    setReading(true);
    setReadError(null);
    try {
      const result = await createUpload(templateZip[0], studentsZip[0]);
      setInventory(result);
      setMaDe(result.ma_de_list[0]?.ma_de ?? null);
    } catch (err) {
      setReadError((err as Error).message);
    } finally {
      setReading(false);
    }
  }

  async function handleRoiFile(files: File[]) {
    setRoiFileError(null);
    const file = files[0];
    if (!file) {
      setRois([]);
      return;
    }
    try {
      setRois(parseRoiConfigFile(await file.text()));
    } catch (err) {
      setRois([]);
      setRoiFileError((err as Error).message);
    }
  }

  const ready =
    inventory !== null &&
    maDe !== null &&
    barem !== null &&
    rois.length > 0 &&
    issues.length === 0 &&
    !disabled;

  return (
    <div className={styles.form}>
      <Step
        index={1}
        title="Tải dữ liệu"
        subtitle="Hai file .zip: ảnh đề mẫu và ảnh bài làm cả lớp"
        done={inventory !== null}
      >
        <div className={styles.grid}>
          <FileDrop
            label="Zip ảnh đề mẫu (bản chưa làm)"
            hint="Mỗi ảnh là một trang đề, sắp theo tên file"
            accept=".zip,application/zip"
            disabled={disabled || reading}
            files={templateZip}
            onChange={(next) => {
              setTemplateZip(next);
              setInventory(null);
            }}
          />
          <FileDrop
            label="Zip ảnh bài làm học sinh"
            hint="Cấu trúc .../Made_N/Bai_lam/HS_N/*.png"
            accept=".zip,application/zip"
            disabled={disabled || reading}
            files={studentsZip}
            onChange={(next) => {
              setStudentsZip(next);
              setInventory(null);
            }}
          />
        </div>

        {readError && (
          <div className={styles.error}>
            <IconAlert size={15} />
            <span>{readError}</span>
          </div>
        )}

        <div className={styles.stepFooter}>
          <Button
            onClick={handleRead}
            disabled={!templateZip[0] || !studentsZip[0] || disabled}
            loading={reading}
          >
            {inventory ? "Đọc lại file zip" : "Đọc file zip"}
          </Button>
          {inventory && (
            <span className={styles.readSummary}>
              {inventory.template_pages.length} trang đề · {inventory.ma_de_list.length} mã đề
            </span>
          )}
        </div>
      </Step>

      {inventory && (
        <Step
          index={2}
          title="Chọn mã đề để chấm"
          subtitle="Mỗi phiên chạy một mã đề — mã đề khác cần barem và vùng riêng"
          done={maDe !== null}
        >
          <div className={styles.maDeGrid}>
            {inventory.ma_de_list.map((group) => (
              <button
                key={group.ma_de}
                type="button"
                className={`${styles.maDeCard} ${maDe === group.ma_de ? styles.maDeActive : ""}`}
                onClick={() => setMaDe(group.ma_de)}
              >
                <span className={styles.maDeName}>{group.ma_de}</span>
                <span className={styles.maDeMeta}>{group.student_count} học sinh</span>
              </button>
            ))}
          </div>

          {selectedMaDe && (
            <div className={styles.studentTableWrapper}>
              <table className={styles.studentTable}>
                <thead>
                  <tr>
                    <th>Mã dùng khi chấm</th>
                    <th>Thư mục</th>
                    <th>Số trang</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedMaDe.students.map((student) => (
                    <tr key={student.folder}>
                      <td className={styles.hsKey}>{student.hs_key}</td>
                      <td>{student.folder}</td>
                      <td
                        className={
                          student.page_count < pageCount ? styles.pageWarn : undefined
                        }
                      >
                        {student.page_count}
                        {student.page_count < pageCount && ` (đề có ${pageCount})`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Step>
      )}

      {inventory && maDe && (
        <Step index={3} title="Chọn barem" subtitle="Lấy từ thư viện đã soạn ở mục Chuẩn bị" done={barem !== null}>
          <BaremPicker
            value={barem?.barem_id ?? null}
            onChange={(_, summary) => setBarem(summary)}
          />
        </Step>
      )}

      {inventory && maDe && barem && (
        <Step
          index={4}
          title="Khai vùng trả lời"
          subtitle="Toạ độ các vùng cần OCR trên từng trang đề"
          done={rois.length > 0 && issues.length === 0}
        >
          <div className={styles.sourceToggle}>
            <label className={styles.radio}>
              <input
                type="radio"
                checked={roiSource === "editor"}
                onChange={() => {
                  setRoiSource("editor");
                  setRoiFileError(null);
                }}
              />
              <span>
                <strong>Gán vùng trên ảnh</strong>
                <span className={styles.radioHint}>
                  Mở trình gán, quét bằng Module 1 rồi chỉ định câu cho từng vùng
                </span>
              </span>
            </label>
            <label className={styles.radio}>
              <input
                type="radio"
                checked={roiSource === "file"}
                onChange={() => {
                  setRoiSource("file");
                  setRois([]);
                }}
              />
              <span>
                <strong>Dùng roi_config.json có sẵn</strong>
                <span className={styles.radioHint}>Tải lên file bạn đã khai từ trước</span>
              </span>
            </label>
          </div>

          {roiSource === "file" ? (
            <>
              <FileDrop
                label="roi_config.json"
                hint="Chỉ cần mảng 'rois'; mỗi vùng nên có 'page'"
                accept=".json,application/json"
                disabled={disabled}
                files={[]}
                onChange={handleRoiFile}
              />
              {roiFileError && (
                <div className={styles.error}>
                  <IconAlert size={15} />
                  <span>{roiFileError}</span>
                </div>
              )}
            </>
          ) : (
            <div className={styles.editorLaunch}>
              <Button
                variant="secondary"
                icon={<IconScan size={15} />}
                onClick={() => setMapperOpen(true)}
              >
                {rois.length > 0 ? "Mở lại trình gán vùng" : "Mở trình gán vùng"}
              </Button>
              <span className={styles.editorHint}>
                Module 1 chỉ tìm ra hình dạng vùng, không biết vùng nào ứng với câu nào — nên
                bước gán câu là thủ công, có gợi ý sẵn từ barem đã chọn.
              </span>
            </div>
          )}

          {rois.length > 0 && (
            <>
              <div className={styles.chips}>
                <span className={styles.chip}>
                  Tổng vùng <strong>{rois.length}</strong>
                </span>
                {Object.entries(taskCounts).map(([type, count]) => (
                  <span key={type} className={styles.chip}>
                    {TASK_TYPE_LABEL[type as keyof typeof TASK_TYPE_LABEL] ?? type}
                    <strong>{count}</strong>
                  </span>
                ))}
              </div>

              {issues.length > 0 ? (
                <ul className={styles.issueList}>
                  {issues.map((issue, index) => (
                    <li key={index} className={styles.error}>
                      <IconAlert size={15} />
                      <span>{issue}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className={styles.ok}>
                  <IconCheck size={15} />
                  <span>Khai báo vùng hợp lệ.</span>
                </div>
              )}
            </>
          )}
        </Step>
      )}

      {ready || (rois.length > 0 && inventory && maDe && barem) ? (
        <div className={styles.summary}>
          <div className={styles.summaryStats}>
            <StatCard label="Học sinh" value={selectedMaDe?.student_count ?? 0} tone="accent" />
            <StatCard label="Vùng / trang" value={rois.length} tone="info" />
            <StatCard
              label="Lượt OCR"
              value={ocrCalls}
              tone="warning"
              hint="Mỗi lượt gọi LLM 2 lần"
            />
          </div>
          <div className={styles.summaryAction}>
            <p className={styles.notice}>
              Chấm <strong>{selectedMaDe?.ma_de}</strong> theo barem{" "}
              <strong>{barem?.name}</strong>. <Badge tone="warning">Tốn chi phí API thật</Badge>
            </p>
            <Button
              size="lg"
              disabled={!ready}
              loading={disabled}
              icon={<IconLayers size={16} />}
              onClick={() =>
                ready &&
                onSubmit({
                  uploadId: inventory!.upload_id,
                  maDe: maDe!,
                  baremId: barem!.barem_id,
                  rois,
                })
              }
            >
              {disabled ? "Đang gửi…" : "Chạy toàn bộ luồng"}
            </Button>
          </div>
        </div>
      ) : null}

      {error && (
        <div className={styles.error}>
          <IconAlert size={15} />
          <span>{error}</span>
        </div>
      )}

      {mapperOpen && inventory && (
        <div className={styles.modalOverlay} onClick={() => setMapperOpen(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <header className={styles.modalHeader}>
              <div>
                <h2 className={styles.modalTitle}>Gán vùng trả lời</h2>
                <p className={styles.modalSubtitle}>
                  {inventory.template_pages.length} trang đề · barem {barem?.name}
                </p>
              </div>
              <Button variant="ghost" size="sm" icon={<IconClose size={15} />} onClick={() => setMapperOpen(false)}>
                Xong
              </Button>
            </header>
            <div className={styles.modalBody}>
              <RoiMapper
                uploadId={inventory.upload_id}
                pages={inventory.template_pages}
                suggestions={suggestions}
                rois={rois}
                onChange={setRois}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
