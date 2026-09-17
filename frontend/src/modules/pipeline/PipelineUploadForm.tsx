import { useEffect, useMemo, useState, type ReactNode } from "react";

import Badge from "@/components/core/Badge";
import Button from "@/components/core/Button";
import Card from "@/components/core/Card";
import FileDrop from "@/components/core/FileDrop";
import { IconAlert, IconCheck, IconClose, IconLayers, IconScan } from "@/components/core/Icon";
import StatCard from "@/components/core/StatCard";
import { getBarem, listBarems } from "@/services/baremApi";
import { createUpload } from "@/services/pipelineApi";
import type { ExamRubric } from "@/types/barem";
import type { BaremSummary } from "@/types/baremLibrary";
import type { RoiConfigEntry, UploadInventory, UploadMaDe } from "@/types/pipeline";

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
    groups: { maDe: string; rois: RoiConfigEntry[]; baremId?: string }[];
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

/**
 * Wizard for the image-to-score run, now covering several exam codes at once.
 *
 * Two things changed shape when a session stopped being one code:
 *
 *   - Rubrics are matched server-side by `ma_de` by default, so normally the
 *     only thing worth showing is whether the library actually has one for
 *     each selected code — checked here so a missing rubric surfaces before
 *     the ZIPs are processed rather than as a 404 on submit. `baremOverride`
 *     is the escape hatch from that: pick a specific library barem for a code
 *     directly (its own declared `ma_de`, if any, doesn't need to match — the
 *     server re-tags it), for a teacher who doesn't want to bother naming
 *     folders `Made_N` at all and just has one rubric for everyone.
 *   - Regions are held per code (`roisByCode`), because two codes rarely put
 *     their answers in the same place. When the template archive has no
 *     per-code folders, one page set serves every code and a single region set
 *     usually does too — hence the "dùng chung" toggle, which is on by default
 *     in exactly that case.
 */
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

  const [selected, setSelected] = useState<string[]>([]);
  const [library, setLibrary] = useState<BaremSummary[] | null>(null);
  // maDe -> barem_id chosen directly, bypassing the auto ma_de match for that
  // code. Absent (or "") means "keep matching by ma_de" (the default).
  const [baremOverride, setBaremOverride] = useState<Record<string, string>>({});

  const [roiSource, setRoiSource] = useState<RoiSource>("editor");
  const [shareRois, setShareRois] = useState(true);
  const [roisByCode, setRoisByCode] = useState<Record<string, RoiConfigEntry[]>>({});
  const [sharedRois, setSharedRois] = useState<RoiConfigEntry[]>([]);
  const [roiFileError, setRoiFileError] = useState<string | null>(null);
  const [mapperFor, setMapperFor] = useState<string | null>(null);
  const [rubric, setRubric] = useState<ExamRubric | null>(null);

  useEffect(() => {
    listBarems()
      .then(setLibrary)
      .catch(() => setLibrary([]));
  }, []);

  const baremFor = (maDe: string): BaremSummary | undefined =>
    library?.find((b) => String(b.ma_de) === String(maDe));

  /** The barem this code will actually be graded with: the manual pick if one
   * was made, else whatever auto-matches by ma_de. */
  const effectiveBaremFor = (maDe: string): BaremSummary | undefined => {
    const overrideId = baremOverride[maDe];
    if (overrideId) return library?.find((b) => b.barem_id === overrideId);
    return baremFor(maDe);
  };

  const groups = inventory?.ma_de_list ?? [];
  const selectedGroups = groups.filter((g) => selected.includes(g.ma_de));
  const missingBarem = selectedGroups.filter((g) => library && !effectiveBaremFor(g.ma_de));

  // One page set for everyone means one region set can serve everyone too.
  const templatesShared = selectedGroups.every((g) => g.template_shared);
  const effectiveShare = shareRois && templatesShared;

  const roisOf = (maDe: string): RoiConfigEntry[] =>
    effectiveShare ? sharedRois : (roisByCode[maDe] ?? []);

  const setRoisOf = (maDe: string, next: RoiConfigEntry[]) => {
    if (effectiveShare) setSharedRois(next);
    else setRoisByCode((prev) => ({ ...prev, [maDe]: next }));
  };

  const pagesOf = (maDe: string): UploadMaDe["template_pages"] =>
    groups.find((g) => g.ma_de === maDe)?.template_pages ?? [];

  // The cau_key picker is driven by the rubric of whichever code is open.
  useEffect(() => {
    const summary = mapperFor ? effectiveBaremFor(mapperFor) : undefined;
    if (!summary) {
      setRubric(null);
      return;
    }
    let cancelled = false;
    getBarem(summary.barem_id)
      .then((detail) => {
        if (!cancelled) setRubric(detail.content);
      })
      .catch(() => {
        if (!cancelled) setRubric(null);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapperFor, library, baremOverride]);

  const suggestions = useMemo(() => suggestCauKeys(rubric), [rubric]);

  const perCode = selectedGroups.map((group) => {
    const rois = roisOf(group.ma_de);
    return {
      group,
      rois,
      issues: rois.length ? validateRois(rois, group.template_pages.length) : [],
      ocrCalls: estimateOcrCalls(rois, group.student_count),
    };
  });

  const totalStudents = selectedGroups.reduce((sum, g) => sum + g.student_count, 0);
  const totalRois = perCode.reduce((sum, p) => sum + p.rois.length, 0);
  const totalOcr = perCode.reduce((sum, p) => sum + p.ocrCalls, 0);
  const allIssues = perCode.flatMap((p) => p.issues.map((i) => `[mã đề ${p.group.ma_de}] ${i}`));

  async function handleRead() {
    if (!templateZip[0] || !studentsZip[0]) return;
    setReading(true);
    setReadError(null);
    try {
      const result = await createUpload(templateZip[0], studentsZip[0]);
      setInventory(result);
      setSelected(result.ma_de_list.map((g) => g.ma_de));
      setRoisByCode({});
      setSharedRois([]);
      setBaremOverride({});
    } catch (err) {
      setReadError((err as Error).message);
    } finally {
      setReading(false);
    }
  }

  async function handleRoiFile(maDe: string, files: File[]) {
    setRoiFileError(null);
    const file = files[0];
    if (!file) {
      setRoisOf(maDe, []);
      return;
    }
    try {
      setRoisOf(maDe, parseRoiConfigFile(await file.text()));
    } catch (err) {
      setRoisOf(maDe, []);
      setRoiFileError((err as Error).message);
    }
  }

  const ready =
    inventory !== null &&
    selectedGroups.length > 0 &&
    missingBarem.length === 0 &&
    perCode.every((p) => p.rois.length > 0 && p.issues.length === 0) &&
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
            hint="Nhiều mã đề thì tách thư mục Made_1/, Made_2/ — để phẳng thì bộ ảnh đó dùng chung"
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
          subtitle="Chọn được nhiều mã đề trong cùng một phiên — barem tự lấy theo mã đề"
          done={selectedGroups.length > 0 && missingBarem.length === 0}
        >
          <div className={styles.maDeGrid}>
            {groups.map((group) => {
              const on = selected.includes(group.ma_de);
              const autoBarem = baremFor(group.ma_de);
              const overrideId = baremOverride[group.ma_de] ?? "";
              const effective = effectiveBaremFor(group.ma_de);
              return (
                <div key={group.ma_de} className={`${styles.maDeCard} ${on ? styles.maDeActive : ""}`}>
                  <button
                    type="button"
                    className={styles.maDeToggle}
                    onClick={() =>
                      setSelected((prev) =>
                        prev.includes(group.ma_de)
                          ? prev.filter((m) => m !== group.ma_de)
                          : [...prev, group.ma_de],
                      )
                    }
                  >
                    <span className={styles.maDeName}>
                      {on ? <IconCheck size={13} /> : null} Mã đề {group.ma_de}
                    </span>
                    <span className={styles.maDeMeta}>
                      {group.student_count} học sinh · {group.template_pages.length} trang đề
                      {group.template_shared ? " (dùng chung)" : ""}
                    </span>
                    {!overrideId && (
                      <span className={autoBarem ? styles.maDeBarem : styles.maDeBaremMissing}>
                        {library === null
                          ? "đang tra kho barem…"
                          : autoBarem
                            ? `barem: ${autoBarem.name}`
                            : "kho chưa có barem cho mã đề này"}
                      </span>
                    )}
                  </button>

                  {on && (
                    <div className={styles.baremPicker}>
                      <select
                        className={styles.baremSelect}
                        value={overrideId}
                        disabled={!library}
                        onChange={(e) =>
                          setBaremOverride((prev) => {
                            const next = { ...prev };
                            if (e.target.value) next[group.ma_de] = e.target.value;
                            else delete next[group.ma_de];
                            return next;
                          })
                        }
                      >
                        <option value="">
                          Tự động theo mã đề{autoBarem ? ` (${autoBarem.name})` : " — kho chưa có"}
                        </option>
                        {library?.map((b) => (
                          <option key={b.barem_id} value={b.barem_id}>
                            {b.name}
                            {b.ma_de ? ` — mã đề ${b.ma_de}` : ""}
                          </option>
                        ))}
                      </select>
                      {overrideId && (
                        <span className={effective ? styles.maDeBarem : styles.maDeBaremMissing}>
                          {effective ? `dùng: ${effective.name}` : "barem đã chọn không còn tồn tại"}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <p className={styles.renumberNote}>
            Không cần mã đề khớp thư viện — chọn thẳng 1 barem có sẵn ở ô trên nếu muốn dùng chung
            cho tất cả (bỏ qua việc tự khớp theo mã đề).
          </p>

          {missingBarem.length > 0 && (
            <div className={styles.error}>
              <IconAlert size={15} />
              <span>
                Thiếu barem cho mã đề {missingBarem.map((g) => g.ma_de).join(", ")}. Soạn hoặc tải
                lên ở mục Kho barem rồi đọc lại, hoặc chọn thẳng 1 barem có sẵn ở ô "Tự động theo
                mã đề" phía trên.
              </span>
            </div>
          )}

          {selectedGroups.map((group) => (
            <div key={group.ma_de} className={styles.studentTableWrapper}>
              <table className={styles.studentTable}>
                <thead>
                  <tr>
                    <th>Mã đề {group.ma_de} — mã khi chấm</th>
                    <th>Thư mục</th>
                    <th>Số trang</th>
                  </tr>
                </thead>
                <tbody>
                  {group.students.map((student) => (
                    <tr key={student.folder}>
                      <td className={styles.hsKey}>{student.hs_key}</td>
                      <td>{student.folder}</td>
                      <td
                        className={
                          student.page_count < group.template_pages.length
                            ? styles.pageWarn
                            : undefined
                        }
                      >
                        {student.page_count}
                        {student.page_count < group.template_pages.length &&
                          ` (đề có ${group.template_pages.length})`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          {selectedGroups.length > 1 && (
            <p className={styles.renumberNote}>
              Hai mã đề có thể cùng chứa thư mục <code>HS_1</code>. Khi chấm, mỗi học sinh được
              đánh số lại cho không trùng trên toàn phiên — bảng điểm và ảnh cắt vì thế không lẫn
              vào nhau.
            </p>
          )}
        </Step>
      )}

      {inventory && selectedGroups.length > 0 && (
        <Step
          index={3}
          title="Khai vùng trả lời"
          subtitle="Mỗi mã đề có bố cục riêng nên vùng khai riêng"
          done={perCode.length > 0 && perCode.every((p) => p.rois.length > 0 && p.issues.length === 0)}
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
                  setRoisByCode({});
                  setSharedRois([]);
                }}
              />
              <span>
                <strong>Dùng roi_config.json có sẵn</strong>
                <span className={styles.radioHint}>Tải lên file bạn đã khai từ trước</span>
              </span>
            </label>
          </div>

          {selectedGroups.length > 1 && (
            <label className={styles.shareToggle}>
              <input
                type="checkbox"
                checked={effectiveShare}
                disabled={!templatesShared}
                onChange={(e) => setShareRois(e.target.checked)}
              />
              <span>
                <strong>Dùng chung một bộ vùng cho mọi mã đề</strong>
                <span className={styles.radioHint}>
                  {templatesShared
                    ? "Các mã đề đang dùng chung một bộ ảnh đề nên nhiều khả năng bố cục giống nhau."
                    : "Không bật được: mỗi mã đề có bộ ảnh đề riêng, bố cục có thể khác nhau."}
                </span>
              </span>
            </label>
          )}

          {roiFileError && (
            <div className={styles.error}>
              <IconAlert size={15} />
              <span>{roiFileError}</span>
            </div>
          )}

          <div className={styles.codeRois}>
            {(effectiveShare ? selectedGroups.slice(0, 1) : selectedGroups).map((group) => {
              const entry = perCode.find((p) => p.group.ma_de === group.ma_de)!;
              return (
                <div key={group.ma_de} className={styles.codeRoiRow}>
                  <div className={styles.codeRoiHead}>
                    <span className={styles.codeRoiName}>
                      {effectiveShare ? "Dùng chung mọi mã đề" : `Mã đề ${group.ma_de}`}
                    </span>
                    <span className={styles.codeRoiMeta}>
                      {entry.rois.length} vùng · {group.template_pages.length} trang
                    </span>
                  </div>

                  {roiSource === "file" ? (
                    <FileDrop
                      label={`roi_config.json${effectiveShare ? "" : ` — mã đề ${group.ma_de}`}`}
                      hint="Chỉ cần mảng 'rois'; mỗi vùng nên có 'page'"
                      accept=".json,application/json"
                      disabled={disabled}
                      files={[]}
                      onChange={(files) => void handleRoiFile(group.ma_de, files)}
                    />
                  ) : (
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={<IconScan size={15} />}
                      onClick={() => setMapperFor(group.ma_de)}
                    >
                      {entry.rois.length > 0 ? "Mở lại trình gán vùng" : "Mở trình gán vùng"}
                    </Button>
                  )}

                  {entry.rois.length > 0 && (
                    <div className={styles.chips}>
                      {Object.entries(countByTaskType(entry.rois)).map(([type, count]) => (
                        <span key={type} className={styles.chip}>
                          {TASK_TYPE_LABEL[type as keyof typeof TASK_TYPE_LABEL] ?? type}
                          <strong>{count}</strong>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {allIssues.length > 0 ? (
            <ul className={styles.issueList}>
              {allIssues.map((issue, index) => (
                <li key={index} className={styles.error}>
                  <IconAlert size={15} />
                  <span>{issue}</span>
                </li>
              ))}
            </ul>
          ) : totalRois > 0 ? (
            <div className={styles.ok}>
              <IconCheck size={15} />
              <span>Khai báo vùng hợp lệ cho mọi mã đề đã chọn.</span>
            </div>
          ) : null}
        </Step>
      )}

      {inventory && selectedGroups.length > 0 && totalRois > 0 && (
        <div className={styles.summary}>
          <div className={styles.summaryStats}>
            <StatCard label="Mã đề" value={selectedGroups.length} tone="accent" />
            <StatCard label="Học sinh" value={totalStudents} tone="accent" />
            <StatCard label="Vùng / trang" value={totalRois} tone="info" />
            <StatCard label="Lượt OCR" value={totalOcr} tone="warning" hint="Mỗi lượt gọi LLM 2 lần" />
          </div>
          <div className={styles.summaryAction}>
            <p className={styles.notice}>
              Chấm mã đề <strong>{selectedGroups.map((g) => g.ma_de).join(", ")}</strong> theo barem{" "}
              <strong>{selectedGroups.map((g) => effectiveBaremFor(g.ma_de)?.name ?? "?").join(", ")}</strong>.{" "}
              <Badge tone="warning">Tốn chi phí API thật</Badge>
            </p>
            <Button
              size="lg"
              disabled={!ready}
              loading={disabled}
              icon={<IconLayers size={16} />}
              onClick={() =>
                ready &&
                onSubmit({
                  uploadId: inventory.upload_id,
                  groups: selectedGroups.map((g) => ({
                    maDe: g.ma_de,
                    rois: roisOf(g.ma_de),
                    baremId: baremOverride[g.ma_de] || undefined,
                  })),
                })
              }
            >
              {disabled ? "Đang gửi…" : "Chạy toàn bộ luồng"}
            </Button>
          </div>
        </div>
      )}

      {error && (
        <div className={styles.error}>
          <IconAlert size={15} />
          <span>{error}</span>
        </div>
      )}

      {mapperFor && inventory && (
        <div className={styles.modalOverlay} onClick={() => setMapperFor(null)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <header className={styles.modalHeader}>
              <div>
                <h2 className={styles.modalTitle}>
                  Gán vùng trả lời{effectiveShare ? "" : ` — mã đề ${mapperFor}`}
                </h2>
                <p className={styles.modalSubtitle}>
                  {pagesOf(mapperFor).length} trang đề · barem {effectiveBaremFor(mapperFor)?.name ?? "—"}
                </p>
              </div>
              <Button variant="ghost" size="sm" icon={<IconClose size={15} />} onClick={() => setMapperFor(null)}>
                Xong
              </Button>
            </header>
            <div className={styles.modalBody}>
              <RoiMapper
                uploadId={inventory.upload_id}
                maDe={mapperFor}
                pages={pagesOf(mapperFor)}
                suggestions={suggestions}
                rois={roisOf(mapperFor)}
                onChange={(next) => setRoisOf(mapperFor, next)}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
