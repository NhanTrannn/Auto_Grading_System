import styles from "./OcrContent.module.css";

/**
 * Renders Module 3's `content` payload. Text tasks return `{lines: [...]}`,
 * table tasks return `{table_extracted: [{col_1, col_2, ...}, ...]}`; anything
 * else (including the `{error: ...}` shape when both passes fail to parse)
 * falls back to raw JSON.
 */
export default function OcrContent({ content }: { content: unknown }) {
  if (content === null || content === undefined) {
    return <p className={styles.empty}>Không có nội dung.</p>;
  }

  const obj = content as Record<string, unknown>;

  if (typeof obj.error === "string") {
    return <div className={styles.error}>{obj.error}</div>;
  }

  if (Array.isArray(obj.lines)) {
    const lines = obj.lines as unknown[];
    if (lines.length === 0) return <p className={styles.empty}>Không đọc được chữ viết tay nào.</p>;
    return (
      <ol className={styles.lines}>
        {lines.map((line, index) => (
          <li key={index} className={styles.line}>
            <span className={styles.lineNo}>{index + 1}</span>
            <span className={styles.lineText}>{String(line)}</span>
          </li>
        ))}
      </ol>
    );
  }

  if (Array.isArray(obj.table_extracted)) {
    const rows = obj.table_extracted as Record<string, unknown>[];
    if (rows.length === 0) return <p className={styles.empty}>Bảng rỗng.</p>;
    const columns = Object.keys(rows[0] ?? {});
    return (
      <div className={styles.tableWrapper}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th />
              {columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                <td className={styles.rowNo}>{index + 1}</td>
                {columns.map((col) => (
                  <td key={col} className={String(row[col] ?? "") ? "" : styles.blankCell}>
                    {String(row[col] ?? "") || "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return <pre className={styles.raw}>{JSON.stringify(content, null, 2)}</pre>;
}
