function triggerDownload(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function csvEscape(value: unknown): string {
  const s = String(value ?? "");
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function downloadStudentSummaryCsv(
  rows: { hs: string; score: number; max_score: number; wrong: string[] }[],
  filename = "ket_qua_tong_hop.csv",
) {
  const header = ["Học sinh", "Điểm", "Điểm tối đa", "Câu sai"];
  const lines = [
    header.join(","),
    ...rows.map((r) =>
      [csvEscape(r.hs), csvEscape(r.score), csvEscape(r.max_score), csvEscape(r.wrong.join("; "))].join(","),
    ),
  ];
  // Leading BOM so Excel (which guesses ANSI otherwise) renders Vietnamese
  // diacritics correctly instead of mojibake.
  triggerDownload("﻿" + lines.join("\n"), filename, "text/csv;charset=utf-8");
}

export function downloadJson(data: unknown, filename: string) {
  triggerDownload(JSON.stringify(data, null, 2), filename, "application/json");
}
