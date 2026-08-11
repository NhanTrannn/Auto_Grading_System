/**
 * Try a criterion's answer spec against a sample student answer, in the browser.
 *
 * Mirrors the two heuristic steps in pipeline.py for `matching` criteria:
 * `_check_exact_output_match` (byte-exact `student_text in expected_outputs`)
 * and, only when that fails, `_grade_by_tokens` (each token found with
 * `str.find` from where the previous one ended — order fixed, position free).
 *
 * It exists because those two rules are impossible to guess from the field
 * names. In particular the token list has no separator: entries are matched as
 * whole literal substrings, so a space inside one is part of the token, and
 * writing "3, 5" as a single entry looks for that comma in the answer.
 *
 * Heuristic only. Every criterion also goes to the LLM afterwards and the final
 * score is a blend, so what this shows is the advisory half, not the grade.
 */
import { useState } from "react";

import type { PartialCreditRule } from "@/types/barem";

import styles from "./MatchingPreview.module.css";

interface MatchingPreviewProps {
  expectedOutputs: string[];
  tokens: string[];
  maxScore: number;
  partialCreditRule?: PartialCreditRule | PartialCreditRule[];
}

interface TokenHit {
  token: string;
  at: number;
}

function matchTokens(text: string, tokens: string[]): TokenHit[] {
  let pos = 0;
  return tokens.map((token) => {
    if (token === "") return { token, at: -1 };
    const at = text.indexOf(token, pos);
    if (at !== -1) pos = at + token.length;
    return { token, at };
  });
}

/** Make trailing spaces and newlines visible — they decide an exact match. */
function reveal(value: string): string {
  return value.replace(/ /g, "·").replace(/\t/g, "→").replace(/\n/g, "¶\n");
}

export default function MatchingPreview({
  expectedOutputs,
  tokens,
  maxScore,
  partialCreditRule,
}: MatchingPreviewProps) {
  const [sample, setSample] = useState("");
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button type="button" className={styles.opener} onClick={() => setOpen(true)}>
        Thử một bài mẫu
      </button>
    );
  }

  const exact = expectedOutputs.includes(sample);
  const hits = matchTokens(sample, tokens);
  const correct = hits.filter((hit) => hit.at !== -1).length;
  const ratio = tokens.length ? correct / tokens.length : 0;
  const ratioScore = maxScore * ratio;
  const hasRule = Array.isArray(partialCreditRule)
    ? partialCreditRule.length > 0
    : Boolean(partialCreditRule);

  return (
    <div className={styles.wrapper}>
      <div className={styles.head}>
        <span className={styles.title}>Thử một bài mẫu</span>
        <button type="button" className={styles.close} onClick={() => setOpen(false)}>
          Đóng
        </button>
      </div>

      <textarea
        className={styles.sample}
        rows={3}
        value={sample}
        placeholder="Dán đúng những gì học sinh viết, kể cả xuống dòng…"
        onChange={(event) => setSample(event.target.value)}
      />

      <div className={styles.result}>
        <div className={`${styles.verdict} ${exact ? styles.ok : styles.no}`}>
          {exact ? "Khớp tuyệt đối" : "Không khớp tuyệt đối"}
          <span className={styles.verdictNote}>
            {exact
              ? `→ correct, ${maxScore} điểm, không cần tới token.`
              : expectedOutputs.length === 0
                ? "→ chưa khai expected_outputs nào."
                : "→ so từng ký tự với từng đáp án; xuống dòng và khoảng trắng đều tính."}
          </span>
        </div>

        {!exact && tokens.length > 0 && (
          <>
            <ul className={styles.tokens}>
              {hits.map((hit, index) => (
                <li key={index} className={hit.at === -1 ? styles.tokenMiss : styles.tokenHit}>
                  <span className={styles.tokenIndex}>{index + 1}</span>
                  <code className={styles.tokenText}>{reveal(hit.token) || "(rỗng)"}</code>
                  <span className={styles.tokenAt}>
                    {hit.at === -1 ? "không tìm thấy (sau token trước đó)" : `tại vị trí ${hit.at}`}
                  </span>
                </li>
              ))}
            </ul>
            <p className={styles.score}>
              {correct}/{tokens.length} token → {ratioScore.toFixed(2)}/{maxScore.toFixed(2)} điểm,{" "}
              {correct > 0 ? "partially_correct" : "wrong"}
              {correct === tokens.length && (
                <em className={styles.scoreNote}>
                  {" "}
                  Đủ 100% token vẫn không bao giờ thành "correct" — chỉ đường khớp tuyệt đối mới đạt.
                </em>
              )}
            </p>
            {hasRule && (
              <p className={styles.ruleWarn}>
                Tiêu chí này có <code>partial_credit_rule</code>: điểm theo tỉ lệ ở trên sẽ bị{" "}
                <strong>thay thế hoàn toàn</strong> bằng <code>partial_score</code> của quy tắc khớp cao nhất — không
                khớp quy tắc nào thì về 0, kể cả khi đúng gần hết token. Ô thử này không chạy quy tắc đó.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
