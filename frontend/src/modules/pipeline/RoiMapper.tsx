import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Badge from "@/components/core/Badge";
import Button from "@/components/core/Button";
import { IconAlert, IconCheck, IconClose, IconScan } from "@/components/core/Icon";
import Spinner from "@/components/core/Spinner";
import { detectRois } from "@/services/ocrApi";
import { templatePageUrl } from "@/services/pipelineApi";
import type { RoiConfigEntry, RoiTaskType, TemplatePage } from "@/types/pipeline";

import type { CauKeySuggestion } from "./cauKeySuggestions";
import styles from "./RoiMapper.module.css";
import { TASK_TYPE_LABEL } from "./roiConfigUtils";

interface RoiMapperProps {
  uploadId: string;
  pages: TemplatePage[];
  suggestions: CauKeySuggestion[];
  rois: RoiConfigEntry[];
  onChange: (rois: RoiConfigEntry[]) => void;
}

const TASK_TYPES: RoiTaskType[] = ["short_text", "long_text", "code", "table", "diagram"];

/** Minimum drag in image pixels before a click counts as drawing a box. */
const MIN_BOX = 8;

interface DragState {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export default function RoiMapper({
  uploadId,
  pages,
  suggestions,
  rois,
  onChange,
}: RoiMapperProps) {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  // Indices into the full list, so edits address the right entry even though
  // only the current page's boxes are drawn.
  const pageIndices = useMemo(
    () => rois.map((roi, index) => ({ roi, index })).filter((r) => (r.roi.page ?? 1) === page),
    [rois, page],
  );

  useEffect(() => {
    setSelected(null);
    setNatural(null);
  }, [page]);

  const patch = useCallback(
    (index: number, changes: Partial<RoiConfigEntry>) => {
      onChange(rois.map((roi, i) => (i === index ? { ...roi, ...changes } : roi)));
    },
    [rois, onChange],
  );

  const remove = useCallback(
    (index: number) => {
      onChange(rois.filter((_, i) => i !== index));
      setSelected(null);
    },
    [rois, onChange],
  );

  /** Pointer position in template-image pixel space. */
  function toImagePoint(clientX: number, clientY: number) {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect || !natural) return null;
    const x = ((clientX - rect.left) / rect.width) * natural.w;
    const y = ((clientY - rect.top) / rect.height) * natural.h;
    return {
      x: Math.max(0, Math.min(natural.w, Math.round(x))),
      y: Math.max(0, Math.min(natural.h, Math.round(y))),
    };
  }

  async function handleScan() {
    setScanning(true);
    setScanError(null);
    try {
      // Module 1 takes an uploaded image, so fetch the page the server already
      // holds and post it straight back to the OCR service.
      const response = await fetch(templatePageUrl(uploadId, page));
      if (!response.ok) throw new Error(`Không tải được ảnh trang ${page}`);
      const blob = await response.blob();
      const file = new File([blob], `page_${page}.png`, { type: blob.type || "image/png" });

      const [result] = await detectRois([file]);
      if (!result || result.error) throw new Error(result?.error ?? "Module 1 không trả về kết quả");

      const detected: RoiConfigEntry[] = (result.rois ?? []).map((box) => ({
        cau_key: "",
        page,
        x: box.x,
        y: box.y,
        w: box.w,
        h: box.h,
        task_type: "short_text",
      }));
      // Replace only this page's boxes; other pages keep their assignments.
      onChange([...rois.filter((roi) => (roi.page ?? 1) !== page), ...detected]);
      setSelected(null);
    } catch (err) {
      setScanError((err as Error).message);
    } finally {
      setScanning(false);
    }
  }

  function finishDrag() {
    if (!drag) return;
    const x = Math.min(drag.x0, drag.x1);
    const y = Math.min(drag.y0, drag.y1);
    const w = Math.abs(drag.x1 - drag.x0);
    const h = Math.abs(drag.y1 - drag.y0);
    setDrag(null);
    if (w < MIN_BOX || h < MIN_BOX) return;

    onChange([...rois, { cau_key: "", page, x, y, w, h, task_type: "short_text" }]);
    setSelected(rois.length);
  }

  const used = new Set(rois.map((roi) => roi.cau_key).filter(Boolean));
  const unassigned = rois.filter((roi) => !roi.cau_key.trim()).length;
  const selectedRoi = selected !== null ? rois[selected] : null;

  return (
    <div className={styles.wrapper}>
      <div className={styles.toolbar}>
        <div className={styles.pages}>
          {pages.map((p) => {
            const count = rois.filter((roi) => (roi.page ?? 1) === p.page).length;
            return (
              <button
                key={p.page}
                type="button"
                className={`${styles.pageTab} ${p.page === page ? styles.pageTabActive : ""}`}
                onClick={() => setPage(p.page)}
                title={p.filename}
              >
                Trang {p.page}
                {count > 0 && <span className={styles.pageCount}>{count}</span>}
              </button>
            );
          })}
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleScan}
          loading={scanning}
          icon={<IconScan size={14} />}
        >
          Quét trang {page} bằng Module 1
        </Button>
      </div>

      {scanError && (
        <div className={styles.error}>
          <IconAlert size={15} />
          <span>{scanError}</span>
        </div>
      )}

      <p className={styles.hint}>
        Kéo chuột trên ảnh để vẽ vùng mới, bấm vào một khung để gán câu. Module 1 chỉ tìm được
        hình dạng vùng — nó không biết vùng nào là câu nào, nên phần gán vẫn do bạn quyết định.
      </p>

      <div className={styles.split}>
        <div
          ref={canvasRef}
          className={styles.canvas}
          onPointerDown={(e) => {
            if (e.button !== 0) return;
            const point = toImagePoint(e.clientX, e.clientY);
            if (!point) return;
            (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
            setDrag({ x0: point.x, y0: point.y, x1: point.x, y1: point.y });
          }}
          onPointerMove={(e) => {
            if (!drag) return;
            const point = toImagePoint(e.clientX, e.clientY);
            if (point) setDrag({ ...drag, x1: point.x, y1: point.y });
          }}
          onPointerUp={finishDrag}
          onPointerCancel={() => setDrag(null)}
        >
          <img
            className={styles.image}
            src={templatePageUrl(uploadId, page)}
            alt={`Trang ${page}`}
            draggable={false}
            onLoad={(e) =>
              setNatural({
                w: e.currentTarget.naturalWidth,
                h: e.currentTarget.naturalHeight,
              })
            }
          />

          {natural &&
            pageIndices.map(({ roi, index }) => (
              <span
                key={index}
                className={[
                  styles.box,
                  roi.cau_key ? styles.boxAssigned : styles.boxUnassigned,
                  index === selected ? styles.boxSelected : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                style={{
                  left: `${(roi.x / natural.w) * 100}%`,
                  top: `${(roi.y / natural.h) * 100}%`,
                  width: `${(roi.w / natural.w) * 100}%`,
                  height: `${(roi.h / natural.h) * 100}%`,
                }}
                onPointerDown={(e) => {
                  e.stopPropagation();
                  setSelected(index);
                }}
              >
                <span className={styles.boxTag}>{roi.cau_key || "chưa gán"}</span>
              </span>
            ))}

          {natural && drag && (
            <span
              className={styles.dragBox}
              style={{
                left: `${(Math.min(drag.x0, drag.x1) / natural.w) * 100}%`,
                top: `${(Math.min(drag.y0, drag.y1) / natural.h) * 100}%`,
                width: `${(Math.abs(drag.x1 - drag.x0) / natural.w) * 100}%`,
                height: `${(Math.abs(drag.y1 - drag.y0) / natural.h) * 100}%`,
              }}
            />
          )}
        </div>

        <aside className={styles.side}>
          <div className={styles.sideHeader}>
            <span>
              {rois.length} vùng · trang này {pageIndices.length}
            </span>
            {unassigned > 0 ? (
              <Badge tone="warning">{unassigned} chưa gán</Badge>
            ) : rois.length > 0 ? (
              <Badge tone="success">Đã gán hết</Badge>
            ) : null}
          </div>

          {selectedRoi ? (
            <div className={styles.form}>
              <label className={styles.field}>
                <span className={styles.label}>Câu (cau_key)</span>
                <input
                  className={styles.input}
                  list="cau-key-options"
                  value={selectedRoi.cau_key}
                  placeholder="VD: Cau_08a_1"
                  onChange={(e) => patch(selected as number, { cau_key: e.target.value.trim() })}
                />
              </label>

              <label className={styles.field}>
                <span className={styles.label}>Loại nội dung</span>
                <select
                  className={styles.input}
                  value={selectedRoi.task_type}
                  onChange={(e) =>
                    patch(selected as number, { task_type: e.target.value as RoiTaskType })
                  }
                >
                  {TASK_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {TASK_TYPE_LABEL[type]}
                    </option>
                  ))}
                </select>
              </label>

              {selectedRoi.task_type === "table" && (
                <div className={styles.pair}>
                  <label className={styles.field}>
                    <span className={styles.label}>Số hàng</span>
                    <input
                      className={styles.input}
                      type="number"
                      min={1}
                      value={selectedRoi.n_rows ?? ""}
                      onChange={(e) =>
                        patch(selected as number, { n_rows: Number(e.target.value) || undefined })
                      }
                    />
                  </label>
                  <label className={styles.field}>
                    <span className={styles.label}>Số cột</span>
                    <input
                      className={styles.input}
                      type="number"
                      min={1}
                      value={selectedRoi.n_cols ?? ""}
                      onChange={(e) =>
                        patch(selected as number, { n_cols: Number(e.target.value) || undefined })
                      }
                    />
                  </label>
                </div>
              )}

              <div className={styles.coords}>
                x {selectedRoi.x} · y {selectedRoi.y} · {selectedRoi.w}×{selectedRoi.h}
              </div>

              <Button
                variant="danger"
                size="sm"
                icon={<IconClose size={13} />}
                onClick={() => remove(selected as number)}
              >
                Xoá vùng này
              </Button>
            </div>
          ) : (
            <p className={styles.placeholder}>Chọn một khung trên ảnh để gán câu cho nó.</p>
          )}

          <div className={styles.listHeader}>Câu trong barem</div>
          <ul className={styles.suggestions}>
            {suggestions.length === 0 && (
              <li className={styles.suggestionEmpty}>Chọn barem để thấy danh sách câu.</li>
            )}
            {suggestions.map((s) => (
              <li key={s.cau_key} className={styles.suggestion}>
                <button
                  type="button"
                  className={styles.suggestionButton}
                  disabled={selected === null}
                  onClick={() =>
                    patch(selected as number, { cau_key: s.cau_key, task_type: s.task_type })
                  }
                  title={selected === null ? "Chọn một khung trước" : `Gán ${s.cau_key}`}
                >
                  <span className={styles.suggestionKey}>{s.cau_key}</span>
                  <span className={styles.suggestionLabel}>{s.label}</span>
                </button>
                {used.has(s.cau_key) && (
                  <span className={styles.usedMark} title="Đã có vùng">
                    <IconCheck size={13} />
                  </span>
                )}
              </li>
            ))}
          </ul>
        </aside>
      </div>

      <datalist id="cau-key-options">
        {suggestions.map((s) => (
          <option key={s.cau_key} value={s.cau_key}>
            {s.label}
          </option>
        ))}
      </datalist>

      {scanning && (
        <div className={styles.scanning}>
          <Spinner size={14} /> Đang quét vùng trên trang {page}…
        </div>
      )}
    </div>
  );
}
