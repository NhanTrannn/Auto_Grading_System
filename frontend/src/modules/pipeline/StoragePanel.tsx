/**
 * Disk usage of pipeline data, with a one-click cleanup.
 *
 * What the cleanup removes is decided server-side (`POST /pipeline/storage/
 * cleanup`): uploads no run uses and that are over a day old — younger ones
 * may belong to a teacher still mapping regions — and ZIP archives that were
 * already unpacked. Runs themselves are only ever deleted one at a time, from
 * their own page, because that throws away results.
 */
import { useEffect, useState } from "react";

import Card from "@/components/core/Card";
import ConfirmDelete from "@/components/core/ConfirmDelete";
import { cleanupStorage, getStorage } from "@/services/pipelineApi";
import type { StorageSummary } from "@/types/pipeline";

import styles from "./StoragePanel.module.css";

function mb(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  return `${(bytes / 1024 ** 2).toFixed(bytes >= 10 * 1024 ** 2 ? 0 : 1)} MB`;
}

export default function StoragePanel() {
  const [storage, setStorage] = useState<StorageSummary | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getStorage()
      .then(setStorage)
      .catch((err) => setError((err as Error).message));
  }, []);

  async function handleCleanup() {
    setError(null);
    setMessage(null);
    try {
      const result = await cleanupStorage();
      setStorage(result.storage);
      setMessage(
        `Đã giải phóng ${mb(result.freed_bytes)} — xoá ${result.removed_uploads} lần tải lên bỏ dở và ${result.removed_zips} file zip thừa.`,
      );
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (!storage) {
    return error ? <p className={styles.error}>Không đọc được dung lượng: {error}</p> : null;
  }

  const reclaimable = storage.orphan_uploads_bytes + storage.leftover_zip_bytes;

  return (
    <Card
      title="Dung lượng lưu trữ"
      subtitle="Ảnh bài làm, ảnh cắt và kết quả của các phiên chấm trên máy chủ"
      actions={
        reclaimable > 0 ? (
          <ConfirmDelete
            label={`Dọn dẹp (${mb(reclaimable)})`}
            armedLabel="Bấm lần nữa để dọn"
            variant="secondary"
            onConfirm={handleCleanup}
          />
        ) : undefined
      }
    >
      <div className={styles.grid}>
        <div className={styles.stat}>
          <span className={styles.label}>Phiên chấm</span>
          <span className={styles.value}>{storage.jobs_count}</span>
          <span className={styles.sub}>{mb(storage.jobs_bytes)}</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.label}>Lần tải lên</span>
          <span className={styles.value}>{storage.uploads_count}</span>
          <span className={styles.sub}>{mb(storage.uploads_bytes)}</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.label}>Tải lên bỏ dở</span>
          <span className={styles.value}>{storage.orphan_uploads_count}</span>
          <span className={styles.sub}>{mb(storage.orphan_uploads_bytes)} · quá 1 ngày, không phiên nào dùng</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.label}>File zip thừa</span>
          <span className={styles.value}>{mb(storage.leftover_zip_bytes)}</span>
          <span className={styles.sub}>đã giải nén, không còn cần</span>
        </div>
      </div>
      {message && <p className={styles.message}>{message}</p>}
      {error && <p className={styles.error}>{error}</p>}
      <p className={styles.note}>
        Muốn xoá hẳn một phiên chấm (kết quả + ảnh cắt), mở phiên đó và bấm “Xoá phiên”.
      </p>
    </Card>
  );
}
