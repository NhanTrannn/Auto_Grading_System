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
  /** Which exam code's blank pages to draw on; omitted when the set is shared. */
  maDe?: string;
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

/** Which edge(s) a resize grip moves. Letters are read off the string below. */
type Handle = "nw" | "n" | "ne" | "w" | "e" | "sw" | "s" | "se";

const HANDLES: Handle[] = ["nw", "n", "ne", "w", "e", "sw", "s", "se"];

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * A move or resize in progress on an existing box.
 *
 * The box is captured as it was when the gesture started and every frame is
 * computed from that snapshot plus the total pointer offset — never from the
 * previous frame. Accumulating deltas would let the clamping below (min size,
 * image bounds) bleed into the next frame, so a box dragged past an edge and
 * back would not return to where the pointer says it should be.
 */
interface Gesture {
  index: number;
  mode: "move" | Handle;
  originX: number;
  originY: number;
  box: Box;
}

const COORD_FIELDS: { key: "x" | "y" | "w" | "h"; label: string }[] = [
  { key: "x", label: "x" },
  { key: "y", label: "y" },
  { key: "w", label: "Rộng" },
  { key: "h", label: "Cao" },
];

/**
 * Clamp one hand-typed coordinate so the box stays on the page.
 *
 * `natural` is null until the template image has loaded, and the numbers are
 * in that image's pixel space — without its size there is nothing to clamp
 * against, so the value is taken as typed rather than clamped against a
 * guessed page size.
 */
function clampCoord(
  roi: Box,
  key: "x" | "y" | "w" | "h",
  value: number,
  natural: { w: number; h: number } | null,
): Partial<Box> {
  const rounded = Math.round(value);
  if (!natural) return { [key]: Math.max(0, rounded) };

  if (key === "x") return { x: Math.max(0, Math.min(natural.w - roi.w, rounded)) };
  if (key === "y") return { y: Math.max(0, Math.min(natural.h - roi.h, rounded)) };
  if (key === "w") return { w: Math.max(MIN_BOX, Math.min(natural.w - roi.x, rounded)) };
  return { h: Math.max(MIN_BOX, Math.min(natural.h - roi.y, rounded)) };
}

/** Apply a gesture's pointer offset to its starting box, clamped to the page. */
function resizeBox(
  gesture: Gesture,
  point: { x: number; y: number },
  bounds: { w: number; h: number },
): Box {
  const dx = point.x - gesture.originX;
  const dy = point.y - gesture.originY;
  const start = gesture.box;
  let { x, y, w, h } = start;

  if (gesture.mode === "move") {
    x += dx;
    y += dy;
  } else {
    if (gesture.mode.includes("w")) {
      x += dx;
      w -= dx;
    }
    if (gesture.mode.includes("e")) w += dx;
    if (gesture.mode.includes("n")) {
      y += dy;
      h -= dy;
    }
    if (gesture.mode.includes("s")) h += dy;
  }

  // Dragging an edge past its opposite one collapses the box to MIN_BOX
  // rather than inverting it; the edge being dragged is the one that stops.
  if (w < MIN_BOX) {
    if (gesture.mode !== "move" && gesture.mode.includes("w")) x = start.x + start.w - MIN_BOX;
    w = MIN_BOX;
  }
  if (h < MIN_BOX) {
    if (gesture.mode !== "move" && gesture.mode.includes("n")) y = start.y + start.h - MIN_BOX;
    h = MIN_BOX;
  }

  x = Math.max(0, Math.min(bounds.w - MIN_BOX, x));
  y = Math.max(0, Math.min(bounds.h - MIN_BOX, y));
  w = Math.min(w, bounds.w - x);
  h = Math.min(h, bounds.h - y);

  return { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) };
}

export default function RoiMapper({
  uploadId,
  maDe,
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
  const [gesture, setGesture] = useState<Gesture | null>(null);
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
      const response = await fetch(templatePageUrl(uploadId, page, maDe));
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
        Kéo chuột trên nền ảnh để vẽ vùng mới. Bấm vào một khung để chọn, rồi kéo thân khung để
        dịch chuyển hoặc kéo các nút vuông ở viền để co giãn — hoặc gõ thẳng số vào ô x/y/rộng/cao
        bên phải. Module 1 chỉ tìm được hình dạng vùng, không biết vùng nào là câu nào, nên phần
        gán vẫn do bạn quyết định.
      </p>

      <div className={styles.split}>
        <div
          ref={canvasRef}
          className={styles.canvas}
          onPointerDown={(e) => {
            if (e.button !== 0) return;
            const point = toImagePoint(e.clientX, e.clientY);
            if (!point) return;
            canvasRef.current?.setPointerCapture?.(e.pointerId);
            setDrag({ x0: point.x, y0: point.y, x1: point.x, y1: point.y });
          }}
          onPointerMove={(e) => {
            const point = toImagePoint(e.clientX, e.clientY);
            if (!point) return;
            // A move/resize of an existing box wins over drawing a new one:
            // both start with a pointerdown inside the canvas, and the box
            // handlers below only stopPropagation, they don't own the drag.
            if (gesture && natural) {
              patch(gesture.index, resizeBox(gesture, point, natural));
              return;
            }
            if (drag) setDrag({ ...drag, x1: point.x, y1: point.y });
          }}
          onPointerUp={(e) => {
            canvasRef.current?.releasePointerCapture?.(e.pointerId);
            if (gesture) {
              setGesture(null);
              return;
            }
            finishDrag();
          }}
          onPointerCancel={() => {
            setDrag(null);
            setGesture(null);
          }}
        >
          <img
            className={styles.image}
            src={templatePageUrl(uploadId, page, maDe)}
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
                  if (e.button !== 0) return;
                  e.stopPropagation();
                  setSelected(index);
                  const point = toImagePoint(e.clientX, e.clientY);
                  if (!point) return;
                  canvasRef.current?.setPointerCapture?.(e.pointerId);
                  setGesture({
                    index,
                    mode: "move",
                    originX: point.x,
                    originY: point.y,
                    box: { x: roi.x, y: roi.y, w: roi.w, h: roi.h },
                  });
                }}
              >
                <span className={styles.boxTag}>{roi.cau_key || "chưa gán"}</span>

                {index === selected &&
                  HANDLES.map((handle) => (
                    <span
                      key={handle}
                      className={`${styles.handle} ${styles[`handle_${handle}`]}`}
                      onPointerDown={(e) => {
                        if (e.button !== 0) return;
                        // Stops the box's own handler from starting a move.
                        e.stopPropagation();
                        const point = toImagePoint(e.clientX, e.clientY);
                        if (!point) return;
                        canvasRef.current?.setPointerCapture?.(e.pointerId);
                        setGesture({
                          index,
                          mode: handle,
                          originX: point.x,
                          originY: point.y,
                          box: { x: roi.x, y: roi.y, w: roi.w, h: roi.h },
                        });
                      }}
                    />
                  ))}
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
                  // The exam code is printed text, not a handwritten answer, so
                  // ocr_main.py always reads it with module3's "printed" prompt
                  // and ignores whatever is chosen here. Disabled rather than
                  // hidden so the field does not appear to have been forgotten.
                  disabled={selectedRoi.cau_key === "MA_DE"}
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
                {selectedRoi.cau_key === "MA_DE" && (
                  <span className={styles.fieldNote}>
                    Vùng mã đề luôn được đọc bằng chế độ chữ in — không phụ thuộc ô này.
                  </span>
                )}
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

              {/* The same four numbers the handles on the image edit, for when
                  a box needs to land on an exact pixel — nudging by 2px with a
                  mouse is fiddly, and two regions meant to be the same width
                  are far easier to match by typing than by eye. */}
              <div className={styles.coordsGrid}>
                {COORD_FIELDS.map(({ key, label }) => (
                  <label key={key} className={styles.field}>
                    <span className={styles.label}>{label}</span>
                    <input
                      className={styles.input}
                      type="number"
                      min={key === "w" || key === "h" ? MIN_BOX : 0}
                      value={selectedRoi[key]}
                      onChange={(e) => {
                        const next = Number(e.target.value);
                        if (!Number.isFinite(next)) return;
                        patch(selected as number, clampCoord(selectedRoi, key, next, natural));
                      }}
                    />
                  </label>
                ))}
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
