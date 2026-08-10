import { useEffect, useMemo, useState } from "react";

import Button from "@/components/core/Button";
import Card from "@/components/core/Card";
import EmptyState from "@/components/core/EmptyState";
import FileDrop from "@/components/core/FileDrop";
import { IconAlert, IconDownload, IconScan } from "@/components/core/Icon";
import StatCard from "@/components/core/StatCard";
import { detectRois } from "@/services/ocrApi";
import type { RoiPageResult } from "@/types/ocr";

import { downloadJson } from "@/modules/grading/downloadUtils";
import styles from "./RoiDetectView.module.css";

/** Distinct outline colour per detected ROI type, cycled by first-seen order. */
const TYPE_COLORS = ["#5b53e8", "#0ea5e9", "#16a34a", "#d97706", "#db2777", "#7c3aed"];

export default function RoiDetectView() {
  const [files, setFiles] = useState<File[]>([]);
  const [results, setResults] = useState<RoiPageResult[] | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activePage, setActivePage] = useState(0);

  // Object URLs for the previews; revoked whenever the file list changes.
  const previews = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews]);

  const page = results?.[activePage] ?? null;
  const rois = page?.rois ?? [];

  const typeColor = useMemo(() => {
    const map = new Map<string, string>();
    rois.forEach((roi) => {
      if (!map.has(roi.type)) map.set(roi.type, TYPE_COLORS[map.size % TYPE_COLORS.length]);
    });
    return map;
  }, [rois]);

  async function handleRun() {
    if (files.length === 0) return;
    setRunning(true);
    setError(null);
    try {
      const data = await detectRois(files);
      setResults(data);
      setActivePage(0);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  }

  /** Skeleton roi_config.json — cau_key/task_type still need filling in by hand. */
  function exportConfig() {
    if (!page) return;
    downloadJson(
      {
        ma_de: "1",
        template_image: page.filename,
        crop_dir: "crops",
        students: [{ hs_key: "HS_1", image: "path/to/hs1.jpg" }],
        rois: (page.rois ?? []).map((roi, index) => ({
          cau_key: `Cau_${String(index + 1).padStart(2, "0")}`,
          x: roi.x,
          y: roi.y,
          w: roi.w,
          h: roi.h,
          task_type: "short_text",
          _detected_type: roi.type,
        })),
      },
      "roi_config.draft.json",
    );
  }

  return (
    <div className={styles.layout}>
      <Card title="Ảnh đầu vào" subtitle="Có thể chọn nhiều trang cùng lúc">
        <div className={styles.form}>
          <FileDrop
            label="Ảnh đề / bài làm"
            hint="Định dạng .jpg, .png"
            accept="image/png,image/jpeg"
            multiple
            disabled={running}
            files={files}
            onChange={(next) => {
              setFiles(next);
              setResults(null);
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
            disabled={files.length === 0}
            loading={running}
            icon={<IconScan size={15} />}
            block
          >
            {running ? "Đang phát hiện vùng…" : `Phát hiện vùng (${files.length} ảnh)`}
          </Button>
          <p className={styles.note}>
            Module 1 chỉ trả về hình học của vùng (x/y/w/h + loại phỏng đoán). Việc gán mỗi vùng cho
            câu nào trong barem (<code>cau_key</code>) vẫn phải khai bằng tay trong{" "}
            <code>roi_config.json</code>.
          </p>
        </div>
      </Card>

      {!results ? (
        <Card>
          <EmptyState
            icon={<IconScan size={20} />}
            title="Chưa có kết quả phát hiện vùng"
            description="Chọn một hoặc nhiều ảnh rồi bấm “Phát hiện vùng” để xem các ROI được khoanh trực tiếp trên ảnh."
          />
        </Card>
      ) : (
        <div className={styles.results}>
          {results.length > 1 && (
            <div className={styles.pageTabs}>
              {results.map((r, index) => (
                <button
                  key={`${r.filename}-${index}`}
                  type="button"
                  className={`${styles.pageTab} ${index === activePage ? styles.pageTabActive : ""}`}
                  onClick={() => setActivePage(index)}
                >
                  <span className={styles.pageTabName}>{r.filename}</span>
                  <span className={styles.pageTabMeta}>
                    {r.error ? "lỗi" : `${r.rois?.length ?? 0} vùng`}
                  </span>
                </button>
              ))}
            </div>
          )}

          {page?.error ? (
            <Card title={page.filename}>
              <div className={styles.error}>
                <IconAlert size={15} />
                <span>{page.error}</span>
              </div>
            </Card>
          ) : (
            page && (
              <>
                <div className={styles.stats}>
                  <StatCard label="Số vùng" value={rois.length} tone="accent" />
                  <StatCard
                    label="Kích thước ảnh"
                    value={`${page.width ?? 0}×${page.height ?? 0}`}
                  />
                  <StatCard label="Dòng chấm" value={page.stats?.dots ?? 0} tone="info" />
                  <StatCard label="Đoạn thẳng" value={page.stats?.segments ?? 0} tone="info" />
                  <StatCard label="Khối" value={page.stats?.blocks ?? 0} tone="warning" />
                  <StatCard label="Bảng" value={page.stats?.tables ?? 0} tone="success" />
                </div>

                <Card
                  title={page.filename}
                  subtitle="Các vùng được khoanh theo toạ độ Module 1 trả về"
                  actions={
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={<IconDownload size={14} />}
                      onClick={exportConfig}
                    >
                      Xuất roi_config nháp
                    </Button>
                  }
                >
                  <div className={styles.legend}>
                    {[...typeColor.entries()].map(([type, color]) => (
                      <span key={type} className={styles.legendItem}>
                        <span className={styles.legendSwatch} style={{ background: color }} />
                        {type}
                      </span>
                    ))}
                  </div>

                  <div className={styles.canvas}>
                    <img
                      className={styles.image}
                      src={previews[activePage]}
                      alt={page.filename}
                    />
                    {rois.map((roi, index) => {
                      const w = page.width || 1;
                      const h = page.height || 1;
                      const color = typeColor.get(roi.type) ?? TYPE_COLORS[0];
                      return (
                        <span
                          key={index}
                          className={styles.box}
                          style={{
                            left: `${(roi.x / w) * 100}%`,
                            top: `${(roi.y / h) * 100}%`,
                            width: `${(roi.w / w) * 100}%`,
                            height: `${(roi.h / h) * 100}%`,
                            borderColor: color,
                          }}
                          title={`${roi.type} — ${roi.x},${roi.y} ${roi.w}×${roi.h}`}
                        >
                          <span className={styles.boxLabel} style={{ background: color }}>
                            {index + 1}
                          </span>
                        </span>
                      );
                    })}
                  </div>
                </Card>

                <Card title="Danh sách vùng" padded={false}>
                  <div className={styles.tableWrapper}>
                    <table className={styles.table}>
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Loại</th>
                          <th>x</th>
                          <th>y</th>
                          <th>w</th>
                          <th>h</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rois.map((roi, index) => (
                          <tr key={index}>
                            <td>
                              <span
                                className={styles.rowSwatch}
                                style={{ background: typeColor.get(roi.type) }}
                              />
                              {index + 1}
                            </td>
                            <td>{roi.type}</td>
                            <td>{roi.x}</td>
                            <td>{roi.y}</td>
                            <td>{roi.w}</td>
                            <td>{roi.h}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </>
            )
          )}
        </div>
      )}
    </div>
  );
}
