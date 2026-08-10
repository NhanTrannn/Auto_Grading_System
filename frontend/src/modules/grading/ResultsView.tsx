import { useMemo, useState } from "react";

import Button from "@/components/core/Button";
import Card from "@/components/core/Card";
import EmptyState from "@/components/core/EmptyState";
import { IconDownload, IconSearch } from "@/components/core/Icon";
import StatCard from "@/components/core/StatCard";
import type { GradingJobResult, StudentSummary } from "@/types/grading";

import { downloadJson, downloadStudentSummaryCsv } from "./downloadUtils";
import ScoreDistribution from "./ScoreDistribution";
import styles from "./ResultsView.module.css";
import StudentDetailPanel from "./StudentDetailPanel";

interface ResultsViewProps {
  result: GradingJobResult;
}

type SortKey = "hs" | "score" | "ratio" | "wrong";
type SortDir = "asc" | "desc";
type Band = "all" | "high" | "mid" | "low";

const BANDS: { id: Band; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "high", label: "Khá – giỏi (≥ 65%)" },
  { id: "mid", label: "Trung bình (40–65%)" },
  { id: "low", label: "Yếu (< 40%)" },
];

function hsSortValue(hs: string): number {
  const match = hs.match(/\d+/);
  return match ? Number(match[0]) : 0;
}

function ratioOf(s: StudentSummary): number {
  return s.max_score ? s.score / s.max_score : 0;
}

function bandOf(s: StudentSummary): Exclude<Band, "all"> {
  const r = ratioOf(s);
  if (r >= 0.65) return "high";
  if (r >= 0.4) return "mid";
  return "low";
}

export default function ResultsView({ result }: ResultsViewProps) {
  const [search, setSearch] = useState("");
  const [band, setBand] = useState<Band>("all");
  const [sortKey, setSortKey] = useState<SortKey>("hs");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [selectedHs, setSelectedHs] = useState<string | null>(null);

  const summary = result.student_summary;

  const stats = useMemo(() => {
    if (summary.length === 0) {
      return { count: 0, avg: 0, best: 0, worst: 0, maxScore: 0, passRate: 0 };
    }
    const scores = summary.map((s) => s.score);
    const maxScore = summary[0].max_score;
    const passing = summary.filter((s) => ratioOf(s) >= 0.5).length;
    return {
      count: summary.length,
      avg: scores.reduce((a, b) => a + b, 0) / scores.length,
      best: Math.max(...scores),
      worst: Math.min(...scores),
      maxScore,
      passRate: Math.round((passing / summary.length) * 100),
    };
  }, [summary]);

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const filtered = summary.filter((s) => {
      if (needle && !s.hs.toLowerCase().includes(needle)) return false;
      if (band !== "all" && bandOf(s) !== band) return false;
      return true;
    });
    return [...filtered].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "hs") cmp = hsSortValue(a.hs) - hsSortValue(b.hs);
      else if (sortKey === "score") cmp = a.score - b.score;
      else if (sortKey === "ratio") cmp = ratioOf(a) - ratioOf(b);
      else cmp = a.wrong.length - b.wrong.length;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [summary, search, band, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir(key === "hs" ? "asc" : "desc");
    }
  }

  function sortIndicator(key: SortKey) {
    if (key !== sortKey) return <span className={styles.sortIdle}>↕</span>;
    return <span className={styles.sortActive}>{sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  const selectedSamples = selectedHs
    ? result.grading_results.filter((r) => r.sample_id.endsWith(`__${selectedHs}`))
    : [];

  return (
    <div className={styles.wrapper}>
      <div className={styles.stats}>
        <StatCard
          label="Số học sinh"
          value={stats.count}
          tone="accent"
          hint={`Thang điểm ${stats.maxScore.toFixed(2)}`}
        />
        <StatCard
          label="Điểm trung bình"
          value={stats.avg.toFixed(2)}
          unit={`/ ${stats.maxScore.toFixed(2)}`}
          tone="info"
        />
        <StatCard label="Cao nhất" value={stats.best.toFixed(2)} tone="success" />
        <StatCard label="Thấp nhất" value={stats.worst.toFixed(2)} tone="danger" />
        <StatCard
          label="Tỉ lệ đạt"
          value={stats.passRate}
          unit="%"
          tone="warning"
          hint="Từ 50% thang điểm trở lên"
        />
      </div>

      <div className={styles.mainGrid}>
        <Card
          title="Bảng điểm học sinh"
          subtitle={`${rows.length}/${summary.length} học sinh — bấm một dòng để xem chi tiết từng tiêu chí`}
          padded={false}
          actions={
            <>
              <Button
                variant="secondary"
                size="sm"
                icon={<IconDownload size={14} />}
                onClick={() => downloadStudentSummaryCsv(summary)}
              >
                CSV
              </Button>
              <Button
                variant="secondary"
                size="sm"
                icon={<IconDownload size={14} />}
                onClick={() => downloadJson(result.grading_results, "grading_results.json")}
              >
                JSON
              </Button>
            </>
          }
        >
          <div className={styles.toolbar}>
            <div className={styles.searchBox}>
              <IconSearch size={15} />
              <input
                className={styles.searchInput}
                type="text"
                placeholder="Tìm mã học sinh (VD: HS_2)…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className={styles.chips}>
              {BANDS.map((b) => (
                <button
                  key={b.id}
                  type="button"
                  className={`${styles.chip} ${band === b.id ? styles.chipActive : ""}`}
                  onClick={() => setBand(b.id)}
                >
                  {b.label}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.tableWrapper}>
            {rows.length === 0 ? (
              <EmptyState
                compact
                title="Không có học sinh nào khớp"
                description="Thử xoá từ khoá tìm kiếm hoặc chọn lại bộ lọc mức điểm."
              />
            ) : (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th className={styles.sortable} onClick={() => toggleSort("hs")}>
                      Học sinh {sortIndicator("hs")}
                    </th>
                    <th className={styles.sortable} onClick={() => toggleSort("score")}>
                      Điểm {sortIndicator("score")}
                    </th>
                    <th className={styles.sortable} onClick={() => toggleSort("ratio")}>
                      Tỉ lệ {sortIndicator("ratio")}
                    </th>
                    <th className={styles.sortable} onClick={() => toggleSort("wrong")}>
                      Câu sai {sortIndicator("wrong")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((s) => {
                    const percent = Math.round(ratioOf(s) * 100);
                    return (
                      <tr key={s.hs} className={styles.row} onClick={() => setSelectedHs(s.hs)}>
                        <td className={styles.hsCell}>{s.hs}</td>
                        <td className={styles.scoreCell}>
                          <strong>{s.score.toFixed(2)}</strong>
                          <span className={styles.scoreMax}>/ {s.max_score.toFixed(2)}</span>
                        </td>
                        <td>
                          <div className={styles.ratioCell}>
                            <span className={styles.barTrack}>
                              <span
                                className={`${styles.barFill} ${styles[bandOf(s)]}`}
                                style={{ width: `${Math.max(percent, 2)}%` }}
                              />
                            </span>
                            <span className={styles.percentLabel}>{percent}%</span>
                          </div>
                        </td>
                        <td className={styles.wrongCell}>
                          {s.wrong.length === 0 ? (
                            <span className={styles.noWrong}>Không có</span>
                          ) : (
                            <span className={styles.wrongList} title={s.wrong.join(", ")}>
                              <span className={styles.wrongCount}>{s.wrong.length}</span>
                              {s.wrong.join(", ")}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </Card>

        <Card title="Phổ điểm" subtitle="Số học sinh theo từng khoảng điểm">
          <ScoreDistribution summary={summary} />
        </Card>
      </div>

      {selectedHs && (
        <StudentDetailPanel
          hs={selectedHs}
          samples={selectedSamples}
          onClose={() => setSelectedHs(null)}
        />
      )}
    </div>
  );
}
