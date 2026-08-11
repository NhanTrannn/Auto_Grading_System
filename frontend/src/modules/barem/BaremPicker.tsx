import { useEffect, useRef, useState } from "react";

import Badge from "@/components/core/Badge";
import Button from "@/components/core/Button";
import { IconAlert, IconFile, IconUpload } from "@/components/core/Icon";
import Spinner from "@/components/core/Spinner";
import { listBarems, uploadBarem } from "@/services/baremApi";
import type { BaremSummary } from "@/types/baremLibrary";

import styles from "./BaremPicker.module.css";

interface BaremPickerProps {
  value: string | null;
  onChange: (baremId: string, summary: BaremSummary) => void;
}

export default function BaremPicker({ value, onChange }: BaremPickerProps) {
  const [barems, setBarems] = useState<BaremSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

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

  async function handleUpload(file: File) {
    setError(null);
    try {
      const created = await uploadBarem(file);
      await refresh();
      onChange(created.barem_id, created);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (loading) {
    return (
      <div className={styles.loading}>
        <Spinner /> Đang tải thư viện barem…
      </div>
    );
  }

  return (
    <div className={styles.wrapper}>
      {error && (
        <div className={styles.error}>
          <IconAlert size={15} />
          <span>{error}</span>
        </div>
      )}

      {barems.length === 0 ? (
        <p className={styles.empty}>
          Thư viện chưa có barem nào. Soạn ở mục <strong>Chuẩn bị → Soạn barem</strong> rồi bấm
          “Lưu vào thư viện”, hoặc tải lên một file barem có sẵn ngay dưới đây.
        </p>
      ) : (
        <ul className={styles.list}>
          {barems.map((barem) => (
            <li key={barem.barem_id}>
              <button
                type="button"
                className={`${styles.item} ${value === barem.barem_id ? styles.itemActive : ""}`}
                onClick={() => onChange(barem.barem_id, barem)}
              >
                <span className={styles.itemIcon}>
                  <IconFile size={15} />
                </span>
                <span className={styles.itemText}>
                  <span className={styles.itemName}>{barem.name}</span>
                  <span className={styles.itemMeta}>
                    {barem.question_count} câu
                    {barem.total_score != null && ` · thang ${barem.total_score}`}
                    {barem.subject && ` · ${barem.subject}`}
                  </span>
                </span>
                {barem.ma_de && <Badge tone="neutral">Mã đề {barem.ma_de}</Badge>}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className={styles.footer}>
        <input
          ref={fileInput}
          type="file"
          accept=".json,application/json"
          className={styles.hiddenInput}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleUpload(file);
            e.target.value = "";
          }}
        />
        <Button
          variant="secondary"
          size="sm"
          icon={<IconUpload size={14} />}
          onClick={() => fileInput.current?.click()}
        >
          Tải barem từ file
        </Button>
      </div>
    </div>
  );
}
