/**
 * Browse the saved rubrics.
 *
 * The library already backed two pickers (`/pipeline` step 3 and the dashboard)
 * but had no screen of its own, so a rubric could be saved and then only ever
 * seen again as one line in a dropdown — no way to check what was in it, fix a
 * name typed in a hurry, or delete a duplicate. Everything here is the same
 * `/api/v1/barems` CRUD those pickers use.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import Badge from "@/components/core/Badge";
import Button from "@/components/core/Button";
import Card from "@/components/core/Card";
import EmptyState from "@/components/core/EmptyState";
import { IconAlert, IconFile, IconUpload } from "@/components/core/Icon";
import PageHeader from "@/components/core/PageHeader";
import Spinner from "@/components/core/Spinner";
import { downloadExam } from "@/modules/barem/migrate";
import { storedDraftQuestionCount } from "@/modules/barem/useBaremDraft";
import { deleteBarem, getBarem, listBarems, updateBarem, uploadBarem } from "@/services/baremApi";
import type { BaremSummary } from "@/types/baremLibrary";

import styles from "./BaremLibraryPage.module.css";

const dateFormatter = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export default function BaremLibraryPage() {
  const navigate = useNavigate();
  const [barems, setBarems] = useState<BaremSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function refresh() {
    try {
      setBarems(await listBarems());
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function run(baremId: string, action: () => Promise<void>) {
    setBusyId(baremId);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  /**
   * Open a rubric in the builder, warning first if that would bury a draft.
   *
   * The builder autosaves whatever is on screen, so opening replaces it.
   * "Hoàn tác" gets it back — but only until the page reloads, because the undo
   * stack lives in memory while the autosave has already overwritten the stored
   * draft. Cheap confirmation beats losing an afternoon's authoring.
   */
  async function openInBuilder(barem: BaremSummary) {
    const pending = storedDraftQuestionCount();
    if (pending > 0) {
      const ok = window.confirm(
        `Trình soạn đang có bản nháp ${pending} câu.\n\n` +
          `Mở "${barem.name}" sẽ thay chỗ bản nháp đó. Trong phiên làm việc này bạn vẫn bấm "Hoàn tác" để lấy lại được, ` +
          `nhưng tải lại trang thì mất hẳn.\n\nMuốn giữ thì bấm Huỷ, quay lại trình soạn và Xuất file hoặc Lưu vào kho trước.`,
      );
      if (!ok) return;
    }

    setBusyId(barem.barem_id);
    setError(null);
    try {
      const detail = await getBarem(barem.barem_id);
      navigate("/barem", { state: { exam: detail.content, baremId: detail.barem_id, name: detail.name } });
    } catch (err) {
      setError((err as Error).message);
      setBusyId(null);
    }
  }

  async function handleRename(barem: BaremSummary) {
    const name = window.prompt("Tên mới cho barem:", barem.name);
    if (!name || name === barem.name) return;
    await run(barem.barem_id, async () => {
      await updateBarem(barem.barem_id, { name });
    });
  }

  async function handleDelete(barem: BaremSummary) {
    const ok = window.confirm(
      `Xoá barem "${barem.name}"?\n\nPhiên chấm đã chạy vẫn giữ bản sao riêng nên không bị ảnh hưởng, nhưng barem này sẽ biến mất khỏi mọi ô chọn.`,
    );
    if (!ok) return;
    await run(barem.barem_id, () => deleteBarem(barem.barem_id));
  }

  async function handleDownload(barem: BaremSummary) {
    await run(barem.barem_id, async () => {
      const detail = await getBarem(barem.barem_id);
      downloadExam(detail.content, `${barem.name}.json`);
    });
  }

  async function handleUpload(file: File) {
    setError(null);
    try {
      await uploadBarem(file);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <IconFile size={13} />
            Chuẩn bị
          </>
        }
        title="Kho barem"
        description="Các barem đã lưu trên máy chủ. Mọi ô chọn barem — ở trang chấm cả lớp và trang chấm từ file — đều lấy từ đây."
        actions={
          <label className={styles.uploadButton}>
            <IconUpload size={15} />
            Tải barem lên
            <input
              type="file"
              accept="application/json,.json"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleUpload(file);
                event.target.value = "";
              }}
            />
          </label>
        }
      />

      {error && (
        <div className={styles.error}>
          <IconAlert size={15} />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className={styles.loading}>
          <Spinner /> Đang tải kho barem…
        </div>
      ) : barems.length === 0 ? (
        <Card>
          <EmptyState
            icon={<IconFile size={20} />}
            title="Kho barem đang trống"
            description="Soạn một barem rồi bấm “Lưu vào thư viện”, hoặc tải lên một file .json có sẵn."
            action={<Button onClick={() => navigate("/barem")}>Soạn barem mới</Button>}
          />
        </Card>
      ) : (
        <Card padded={false}>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Tên</th>
                  <th>Mã đề</th>
                  <th>Môn</th>
                  <th className={styles.num}>Số câu</th>
                  <th className={styles.num}>Tổng điểm</th>
                  <th>Sửa lần cuối</th>
                  <th aria-label="Thao tác" />
                </tr>
              </thead>
              <tbody>
                {barems.map((barem) => (
                  <tr key={barem.barem_id} className={busyId === barem.barem_id ? styles.busy : undefined}>
                    <td>
                      <button type="button" className={styles.name} onClick={() => void openInBuilder(barem)}>
                        {barem.name}
                      </button>
                      <code className={styles.id}>{barem.barem_id.slice(0, 8)}</code>
                    </td>
                    <td>{barem.ma_de ? <Badge tone="accent" dot={false}>{barem.ma_de}</Badge> : "—"}</td>
                    <td className={styles.subject}>{barem.subject ?? "—"}</td>
                    <td className={styles.num}>{barem.question_count}</td>
                    <td className={styles.num}>{barem.total_score?.toFixed(2) ?? "—"}</td>
                    <td className={styles.time}>{dateFormatter.format(new Date(barem.updated_at))}</td>
                    <td>
                      <div className={styles.actions}>
                        <button type="button" onClick={() => void openInBuilder(barem)}>
                          Mở
                        </button>
                        <button type="button" onClick={() => void handleRename(barem)}>
                          Đổi tên
                        </button>
                        <button type="button" onClick={() => void handleDownload(barem)}>
                          Tải file
                        </button>
                        <button
                          type="button"
                          className={styles.danger}
                          onClick={() => void handleDelete(barem)}
                        >
                          Xoá
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
