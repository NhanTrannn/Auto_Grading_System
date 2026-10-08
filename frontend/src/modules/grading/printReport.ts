/**
 * Printable class report — the "PDF" export of a grading run.
 *
 * Built as a standalone HTML document opened in a new window and handed to the
 * browser's print dialog ("Lưu dưới dạng PDF"), not generated as a PDF here.
 * Client-side PDF libraries (jsPDF & co.) only ship Latin fonts, so Vietnamese
 * diacritics come out broken unless a full Unicode font is embedded — several
 * hundred KB for every user, for a button pressed once per exam. The browser
 * already renders Vietnamese and SVG perfectly and its PDF output is vector,
 * so the text stays selectable and sharp.
 *
 * Everything the teacher needs to audit a grade is on paper: what OCR read
 * from the sheet, the score per criterion, and the grader's reasoning — the
 * same fields StudentDetailPanel shows on screen.
 */
import type { CriterionResult, GradingJobResult, GradingResultSample, StudentSummary } from "@/types/grading";

export interface ReportMeta {
  /** Shown as the report's heading line, e.g. "Phiên ae86784eb52f". */
  title: string;
  maDe?: string | null;
  baremName?: string | null;
  createdAt?: string | null;
}

const STATUS_LABEL: Record<string, string> = {
  correct: "Đúng",
  partially_correct: "Đúng một phần",
  wrong: "Sai",
  needs_teacher_review: "Cần GV xem lại",
  needs_vision_teacher_review: "Cần GV xem lại",
  error: "Lỗi chấm",
  ungraded: "Chưa chấm",
};

const STATUS_CLASS: Record<string, string> = {
  correct: "ok",
  partially_correct: "part",
  wrong: "bad",
  error: "bad",
};

function esc(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmt(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "—";
}

function str(cr: CriterionResult, key: string): string | null {
  const value = cr[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function answerOf(cr: CriterionResult): string | null {
  const evidence = cr.evidence as { student_answer?: unknown } | undefined;
  const answer = evidence?.student_answer;
  return typeof answer === "string" && answer.trim() ? answer : null;
}

function statusPill(status: string): string {
  return `<span class="pill ${STATUS_CLASS[status] ?? "info"}">${esc(STATUS_LABEL[status] ?? status)}</span>`;
}

function hsNumber(hs: string): number {
  const match = hs.match(/\d+/);
  return match ? Number(match[0]) : 0;
}

/** `cau_1_001__HS_14` → `HS_14`, matching how ResultsView pairs samples with students. */
function studentOf(sample: GradingResultSample): string {
  const index = sample.sample_id.lastIndexOf("__");
  return index >= 0 ? sample.sample_id.slice(index + 2) : sample.sample_id;
}

// ── charts ──────────────────────────────────────────────────────────────────

interface Bin {
  label: string;
  count: number;
}

/**
 * One bar per whole point on a typical 10-point scale (what a teacher reads a
 * "phổ điểm" as), falling back to ten equal-width bins for other scales so a
 * 100-point paper doesn't get 100 hair-thin bars.
 */
function scoreBins(summary: StudentSummary[], maxScore: number): Bin[] {
  if (!maxScore) return [];
  const integral = Number.isInteger(maxScore) && maxScore <= 20;
  const binCount = integral ? maxScore : 10;
  const width = maxScore / binCount;
  const bins: Bin[] = Array.from({ length: binCount }, (_, i) => {
    const from = i * width;
    const to = (i + 1) * width;
    const label = integral ? `${from}–${to}` : `${from.toFixed(1)}–${to.toFixed(1)}`;
    return { label, count: 0 };
  });
  for (const s of summary) {
    const index = Math.min(binCount - 1, Math.max(0, Math.floor(s.score / width)));
    bins[index].count += 1;
  }
  return bins;
}

function histogramSvg(bins: Bin[]): string {
  if (bins.length === 0) return `<p class="muted">Chưa có dữ liệu.</p>`;
  const W = 640;
  const H = 170;
  const pad = { top: 18, right: 8, bottom: 36, left: 34 };
  const innerW = W - pad.left - pad.right;
  const innerH = H - pad.top - pad.bottom;
  // Whole-number ticks at an even step, with the axis topped at a multiple of
  // that step — dividing the raw peak into four labelled 6 as 0/2/3/5/6.
  const maxCount = Math.max(1, ...bins.map((b) => b.count));
  const tickStep = Math.max(1, Math.ceil(maxCount / 4));
  const peak = tickStep * Math.ceil(maxCount / tickStep);
  const ticks = peak / tickStep;
  const step = innerW / bins.length;
  const barW = Math.min(46, step * 0.72);

  const grid = Array.from({ length: ticks + 1 }, (_, i) => {
    const value = tickStep * i;
    const y = pad.top + innerH - (value / peak) * innerH;
    return `<line x1="${pad.left}" x2="${W - pad.right}" y1="${y}" y2="${y}" class="grid"/>
      <text x="${pad.left - 6}" y="${y + 4}" class="axis" text-anchor="end">${value}</text>`;
  }).join("");

  const bars = bins
    .map((bin, i) => {
      const h = (bin.count / peak) * innerH;
      const x = pad.left + step * i + (step - barW) / 2;
      const y = pad.top + innerH - h;
      const cx = x + barW / 2;
      return `${bin.count ? `<rect x="${x}" y="${y}" width="${barW}" height="${h}" rx="3" class="bar"/>` : ""}
        ${bin.count ? `<text x="${cx}" y="${y - 5}" class="value" text-anchor="middle">${bin.count}</text>` : ""}
        <text x="${cx}" y="${H - pad.bottom + 16}" class="axis" text-anchor="middle">${esc(bin.label)}</text>`;
    })
    .join("");

  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Phổ điểm">
    ${grid}${bars}
    <text x="${pad.left + innerW / 2}" y="${H - 4}" class="axis" text-anchor="middle">Khoảng điểm</text>
  </svg>`;
}

interface QuestionStat {
  question: number;
  avgRatio: number;
  avg: number;
  max: number;
  count: number;
}

function questionStats(samples: GradingResultSample[]): QuestionStat[] {
  const byQuestion = new Map<number, GradingResultSample[]>();
  for (const s of samples) {
    const list = byQuestion.get(s.question_number) ?? [];
    list.push(s);
    byQuestion.set(s.question_number, list);
  }
  return [...byQuestion.entries()]
    .sort(([a], [b]) => a - b)
    .map(([question, list]) => {
      const avg = list.reduce((sum, s) => sum + (s.score ?? 0), 0) / list.length;
      const max = list[0]?.max_score ?? 0;
      return { question, avg, max, avgRatio: max ? avg / max : 0, count: list.length };
    });
}

/** Horizontal bars: average % per question — shows at a glance which items the class found hard. */
function questionBarsSvg(stats: QuestionStat[]): string {
  if (stats.length === 0) return `<p class="muted">Chưa có dữ liệu.</p>`;
  const rowH = 22;
  const W = 640;
  const labelW = 64;
  const valueW = 96;
  const barMax = W - labelW - valueW - 8;
  const H = stats.length * rowH + 8;
  const rows = stats
    .map((s, i) => {
      const y = 4 + i * rowH;
      const w = Math.max(2, s.avgRatio * barMax);
      const tone = s.avgRatio >= 0.65 ? "good" : s.avgRatio >= 0.4 ? "mid" : "low";
      return `<text x="0" y="${y + 15}" class="axis">Câu ${s.question}</text>
        <rect x="${labelW}" y="${y + 3}" width="${barMax}" height="14" rx="3" class="track"/>
        <rect x="${labelW}" y="${y + 3}" width="${w}" height="14" rx="3" class="hbar ${tone}"/>
        <text x="${W}" y="${y + 15}" class="axis" text-anchor="end">${fmt(s.avg)} / ${fmt(s.max)} (${Math.round(
          s.avgRatio * 100,
        )}%)</text>`;
    })
    .join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Điểm trung bình từng câu">${rows}</svg>`;
}

// ── sections ────────────────────────────────────────────────────────────────

/**
 * pipeline.py used to write its blank-answer verdict in English; results graded
 * before that was changed still carry it, and a teacher-facing Vietnamese
 * report shouldn't switch language for exactly the most common case.
 */
const LEGACY_REASONS: Record<string, string> = {
  "Student left this part blank.": "Học sinh bỏ trống phần này.",
};

function criterionBlock(cr: CriterionResult, showAnswer: boolean): string {
  const answer = answerOf(cr);
  const content = str(cr, "criterion_content") ?? str(cr, "content");
  const rawReasoning = str(cr, "llm_reasoning") ?? str(cr, "reason");
  const reasoning = rawReasoning ? (LEGACY_REASONS[rawReasoning] ?? rawReasoning) : null;
  const suggestion = str(cr, "suggestion");
  const groupReason = str(cr, "group_score_reasoning");
  const review = cr.teacher_review_required === true;

  return `<div class="criterion">
    <div class="crit-head">
      <span class="crit-id">${esc(cr.criterion_id)}</span>
      <span class="crit-content">${esc(content ?? "")}</span>
      <span class="crit-score">${fmt(cr.score)} / ${fmt(cr.max_score)}</span>
      ${statusPill(cr.status)}
      ${review ? `<span class="pill info">GV nên xem lại</span>` : ""}
    </div>
    ${
      showAnswer
        ? `<div class="field"><span class="field-label">Bài làm (OCR đọc được)</span>${
            answer ? `<pre class="answer">${esc(answer)}</pre>` : `<p class="muted">— Bỏ trống / OCR không đọc được —</p>`
          }</div>`
        : ""
    }
    ${reasoning ? `<div class="field"><span class="field-label">Lý do chấm</span><p>${esc(reasoning)}</p></div>` : ""}
    ${suggestion ? `<div class="field hint"><span class="field-label">Gợi ý cho học sinh</span><p>${esc(suggestion)}</p></div>` : ""}
    ${groupReason ? `<div class="field"><span class="field-label">Điểm nhóm</span><p>${esc(groupReason)}</p></div>` : ""}
  </div>`;
}

function questionBlock(sample: GradingResultSample): string {
  const criteria = sample.criterion_results ?? [];
  let previousAnswer: string | null | undefined;
  const blocks = criteria
    .map((cr) => {
      // Criteria reading the same slot share one answer — print it once.
      const answer = answerOf(cr);
      const show = answer !== previousAnswer;
      previousAnswer = answer;
      return criterionBlock(cr, show);
    })
    .join("");

  const groups = (sample.group_overrides ?? [])
    .map(
      (g) => `<p class="group-note">Nhóm <b>${esc(g.group_id)}</b> (${esc(g.members.join(", "))}) tính chung:
        <b>${fmt(g.group_score)} / ${fmt(g.group_max_score)}</b>${
          g.group_score_reasoning ? ` — ${esc(g.group_score_reasoning)}` : ""
        }</p>`,
    )
    .join("");

  return `<section class="question">
    <div class="q-head">
      <span class="q-title">Câu ${esc(sample.question_number)}</span>
      <span class="q-score">${fmt(sample.score)} / ${fmt(sample.max_score)}</span>
      ${statusPill(sample.status)}
    </div>
    ${groups}
    ${blocks || `<p class="muted">Không có tiêu chí nào được chấm cho câu này.</p>`}
  </section>`;
}

function studentPage(s: StudentSummary, samples: GradingResultSample[], rank: number, total: number): string {
  const sorted = [...samples].sort((a, b) => a.question_number - b.question_number);
  const percent = s.max_score ? Math.round((s.score / s.max_score) * 100) : 0;
  const reviewCount = sorted.filter((x) => x.teacher_review_required === true).length;

  const overview = sorted
    .map(
      (x) => `<tr><td>Câu ${esc(x.question_number)}</td><td class="num">${fmt(x.score)} / ${fmt(x.max_score)}</td>
        <td>${statusPill(x.status)}</td></tr>`,
    )
    .join("");

  return `<article class="student">
    <header class="student-head">
      <div>
        <h2>${esc(s.hs)}</h2>
        <p class="muted">Xếp hạng ${rank}/${total} trong lớp${
          reviewCount ? ` · <b class="warn">${reviewCount} câu cần giáo viên xem lại</b>` : ""
        }</p>
      </div>
      <div class="big-score">${fmt(s.score)}<span> / ${fmt(s.max_score)}</span><small>${percent}%</small></div>
    </header>
    <table class="mini">
      <thead><tr><th>Câu</th><th class="num">Điểm</th><th>Kết quả</th></tr></thead>
      <tbody>${overview}</tbody>
    </table>
    ${sorted.map(questionBlock).join("")}
  </article>`;
}

// ── document ────────────────────────────────────────────────────────────────

export function buildReportHtml(result: GradingJobResult, meta: ReportMeta): string {
  const summary = [...result.student_summary].sort((a, b) => hsNumber(a.hs) - hsNumber(b.hs));
  const maxScore = summary[0]?.max_score ?? 0;
  const scores = summary.map((s) => s.score);
  const count = summary.length;
  const avg = count ? scores.reduce((a, b) => a + b, 0) / count : 0;
  const sortedScores = [...scores].sort((a, b) => a - b);
  const median = count
    ? count % 2
      ? sortedScores[(count - 1) / 2]
      : (sortedScores[count / 2 - 1] + sortedScores[count / 2]) / 2
    : 0;
  const passing = summary.filter((s) => s.max_score && s.score / s.max_score >= 0.5).length;
  const passRate = count ? Math.round((passing / count) * 100) : 0;

  const ranking = [...summary].sort((a, b) => b.score - a.score);
  const rankOf = new Map(ranking.map((s, i) => [s.hs, i + 1]));

  const samplesByStudent = new Map<string, GradingResultSample[]>();
  for (const sample of result.grading_results) {
    const hs = studentOf(sample);
    const list = samplesByStudent.get(hs) ?? [];
    list.push(sample);
    samplesByStudent.set(hs, list);
  }

  const printedAt = new Date().toLocaleString("vi-VN");
  const gradedAt = meta.createdAt ? new Date(meta.createdAt).toLocaleString("vi-VN") : null;
  const metaLine = [
    meta.maDe ? `Mã đề <b>${esc(meta.maDe)}</b>` : null,
    meta.baremName ? `Barem <b>${esc(meta.baremName)}</b>` : null,
    gradedAt ? `Chấm lúc ${esc(gradedAt)}` : null,
    `In lúc ${esc(printedAt)}`,
  ]
    .filter(Boolean)
    .join(" · ");

  const classRows = summary
    .map((s) => {
      const percent = s.max_score ? Math.round((s.score / s.max_score) * 100) : 0;
      return `<tr>
        <td>${esc(s.hs)}</td>
        <td class="num"><b>${fmt(s.score)}</b> / ${fmt(s.max_score)}</td>
        <td class="num">${percent}%</td>
        <td class="num">${rankOf.get(s.hs)}</td>
        <td>${s.wrong.length ? esc(s.wrong.map((q) => `Câu ${q}`).join(", ")) : `<span class="muted">Không có</span>`}</td>
      </tr>`;
    })
    .join("");

  const stat = (label: string, value: string, sub = "") =>
    `<div class="stat"><span class="stat-label">${label}</span><span class="stat-value">${value}</span>${
      sub ? `<span class="stat-sub">${sub}</span>` : ""
    }</div>`;

  return `<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>Báo cáo kết quả chấm — ${esc(meta.title)}</title>
<style>
  @page { size: A4; margin: 14mm 13mm 16mm; }
  * { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body { margin: 0; font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; font-size: 11pt;
         line-height: 1.45; color: #1d2433; background: #fff; }
  .page { max-width: 186mm; margin: 0 auto; padding: 8mm 0; }
  h1 { margin: 0 0 4px; font-size: 20pt; letter-spacing: -0.01em; }
  h2 { margin: 0; font-size: 15pt; }
  h3 { margin: 18px 0 8px; font-size: 12pt; color: #3b3fbf; text-transform: uppercase; letter-spacing: 0.04em; }
  .muted { color: #6b7385; margin: 0; }
  .warn { color: #b45309; }
  .meta { margin: 0 0 14px; color: #4b5366; font-size: 10pt; }
  .brand { font-size: 9pt; font-weight: 700; letter-spacing: 0.08em; color: #5b50e6; text-transform: uppercase; }
  .stats { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin: 10px 0 4px; }
  .stat { border: 1px solid #e3e6ee; border-radius: 8px; padding: 8px 10px; background: #f8f9fc; }
  .stat-label { display: block; font-size: 8.5pt; color: #6b7385; }
  .stat-value { display: block; font-size: 15pt; font-weight: 700; }
  .stat-sub { display: block; font-size: 8pt; color: #6b7385; }
  .chart { width: 100%; height: auto; display: block; }
  .chart .grid { stroke: #e6e8ef; stroke-width: 1; }
  .chart .axis { font-size: 10px; fill: #6b7385; }
  .chart .value { font-size: 11px; font-weight: 700; fill: #1d2433; }
  .chart .bar { fill: #6157e8; }
  .chart .track { fill: #eef0f5; }
  .chart .hbar.good { fill: #16a06a; } .chart .hbar.mid { fill: #e0a21b; } .chart .hbar.low { fill: #d9443f; }
  .charts { display: grid; grid-template-columns: 1fr; gap: 6px; }
  table { width: 100%; border-collapse: collapse; font-size: 10pt; }
  th { text-align: left; font-size: 8.5pt; text-transform: uppercase; letter-spacing: 0.04em; color: #6b7385;
       border-bottom: 1.5px solid #cfd4e0; padding: 5px 6px; }
  td { border-bottom: 1px solid #edf0f5; padding: 5px 6px; vertical-align: top; }
  tr { break-inside: avoid; }
  .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 8.5pt; font-weight: 600;
          white-space: nowrap; background: #e8f0fe; color: #2453b3; }
  .pill.ok { background: #dcf5e8; color: #0f7a4d; }
  .pill.part { background: #fdf0d5; color: #9a5b06; }
  .pill.bad { background: #fde5e5; color: #b42323; }
  .student { break-before: page; }
  .student-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px;
                  border-bottom: 2px solid #1d2433; padding-bottom: 8px; margin-bottom: 10px; }
  .big-score { font-size: 24pt; font-weight: 800; text-align: right; line-height: 1; }
  .big-score span { font-size: 12pt; font-weight: 600; color: #6b7385; }
  .big-score small { display: block; font-size: 10pt; font-weight: 600; color: #6b7385; margin-top: 4px; }
  .mini { margin-bottom: 8px; }
  .question { margin-top: 12px; }
  .q-head { display: flex; align-items: center; gap: 10px; background: #f1f2f8; border-radius: 6px;
            padding: 6px 10px; break-after: avoid; }
  .q-title { font-weight: 700; font-size: 12pt; }
  .q-score { margin-left: auto; font-weight: 700; font-variant-numeric: tabular-nums; }
  .criterion { border-left: 3px solid #d5d9e5; margin: 8px 0 0 4px; padding: 2px 0 2px 10px; break-inside: avoid; }
  .crit-head { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
  .crit-id { font-family: Consolas, "Courier New", monospace; font-size: 9pt; font-weight: 700; color: #5b50e6; }
  .crit-content { flex: 1 1 260px; font-size: 10pt; color: #2d3445; }
  .crit-score { font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .field { margin-top: 5px; }
  .field p { margin: 0; font-size: 10pt; }
  .field-label { display: block; font-size: 8pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
                 color: #6b7385; margin-bottom: 2px; }
  .field.hint p { color: #0f6a44; }
  .answer { margin: 0; padding: 6px 8px; font-family: Consolas, "Courier New", monospace; font-size: 9pt;
            white-space: pre-wrap; word-break: break-word; background: #f6f7fa; border: 1px solid #e3e6ee;
            border-radius: 4px; }
  .group-note { margin: 6px 0 0; padding: 6px 10px; font-size: 9.5pt; background: #eeecfd; border-radius: 6px; }
  .toolbar { position: sticky; top: 0; display: flex; gap: 8px; justify-content: center; padding: 10px;
             background: #1d2433; color: #fff; font-size: 10pt; }
  .toolbar button { font: inherit; font-weight: 600; padding: 6px 14px; border-radius: 6px; border: 0;
                    background: #6157e8; color: #fff; cursor: pointer; }
  @media print { .toolbar { display: none; } .page { padding: 0; } }
</style>
</head>
<body>
<div class="toolbar">Chọn máy in <b>&nbsp;“Lưu dưới dạng PDF”&nbsp;</b> để xuất file.
  <button onclick="window.print()">In / Lưu PDF</button></div>
<div class="page">
  <div class="brand">Autograding 2026 · Báo cáo kết quả chấm</div>
  <h1>${esc(meta.title)}</h1>
  <p class="meta">${metaLine}</p>

  <div class="stats">
    ${stat("Số học sinh", String(count))}
    ${stat("Điểm trung bình", fmt(avg), `/ ${fmt(maxScore)}`)}
    ${stat("Trung vị", fmt(median))}
    ${stat("Cao nhất", fmt(count ? Math.max(...scores) : 0))}
    ${stat("Thấp nhất", fmt(count ? Math.min(...scores) : 0))}
    ${stat("Tỉ lệ đạt", `${passRate}%`, "≥ 50% thang điểm")}
  </div>

  <h3>Phổ điểm</h3>
  <div class="charts">${histogramSvg(scoreBins(summary, maxScore))}</div>

  <h3>Điểm trung bình từng câu</h3>
  <div class="charts">${questionBarsSvg(questionStats(result.grading_results))}</div>

  <h3>Bảng điểm cả lớp</h3>
  <table>
    <thead><tr><th>Học sinh</th><th class="num">Điểm</th><th class="num">Tỉ lệ</th><th class="num">Hạng</th><th>Câu chưa trọn điểm</th></tr></thead>
    <tbody>${classRows}</tbody>
  </table>

  ${summary.map((s) => studentPage(s, samplesByStudent.get(s.hs) ?? [], rankOf.get(s.hs) ?? 0, count)).join("")}
</div>
<script>
  // Fonts and SVG must be laid out before the dialog snapshots the page.
  window.addEventListener("load", function () { setTimeout(function () { window.print(); }, 300); });
</script>
</body>
</html>`;
}

/**
 * Open the report in a new tab and hand it to the print dialog.
 *
 * Returns false when a popup blocker refused the window, so the caller can say
 * so instead of the click appearing to do nothing.
 */
export function openPrintableReport(result: GradingJobResult, meta: ReportMeta): boolean {
  const html = buildReportHtml(result, meta);
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank");
  if (!win) {
    URL.revokeObjectURL(url);
    return false;
  }
  // The new tab has loaded the blob by the time a minute passes; keeping the
  // URL alive until then lets "reload" in that tab still work for a while.
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return true;
}
