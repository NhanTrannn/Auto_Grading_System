/**
 * Set a question's total by rescaling the criteria underneath it.
 *
 * A question has no score field of its own — `questionTotal` adds up what the
 * flattened criteria carry, so "the score of câu 1" is a derived number and the
 * only way to change it is to change its parts. Every numeric `score` in the
 * tree is scaled by the same factor, which keeps the author's split intact
 * (câu 13's 1.0/0.5/0.5 stays 1.0/0.5/0.5 in shape when it becomes 2.5).
 *
 * Deliberately left alone: a child whose `score` is null. Those are either
 * all_or_nothing members, scored at the group level through their parent's
 * score, or weight-derived children that `flatten_criteria` computes from the
 * parent's score and the sibling weights. Both follow automatically once the
 * parent is scaled; writing a score onto them would override the very
 * mechanism that keeps them in sync.
 */
import type { Criterion, RubricQuestion } from "@/types/barem";

import { flattenCriteria, questionTotal } from "./flatten";

/** Two decimals matches the 0.05 granularity every barem here is authored at. */
function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

// `score` is the only number to touch. `group_max_score` is not stored in the
// tree at all — flattenCriteria derives it from the group parent's own `score`,
// so scaling that parent carries the group along. `weight` is a ratio and must
// stay put, or the split it encodes would change too.
function scaleCriteria(criteria: Criterion[], factor: number): Criterion[] {
  return criteria.map((criterion) => {
    const next: Criterion = { ...criterion };
    if (typeof next.score === "number") next.score = round2(next.score * factor);
    if (next.sub_criteria?.length) next.sub_criteria = scaleCriteria(next.sub_criteria, factor);
    return next;
  });
}

/** Nudge one leaf so the rounded parts add back up to exactly `target`. */
function absorbDrift(question: RubricQuestion, target: number): RubricQuestion {
  const drift = round2(target - questionTotal(flattenCriteria(question)));
  if (drift === 0) return question;

  // The largest scorer absorbs it: a 0.01 nudge is proportionally smallest
  // there, and it is never a null-score child (those have no score to nudge).
  let bestId: string | undefined;
  let bestScore = -Infinity;
  const visit = (criteria: Criterion[]) => {
    for (const criterion of criteria) {
      // An all_or_nothing parent counts as the scoring unit even though it has
      // children, because its own score is what the group contributes.
      const scoresItself = criterion.all_or_nothing || !criterion.sub_criteria?.length;
      if (scoresItself && typeof criterion.score === "number" && criterion.score > bestScore) {
        bestScore = criterion.score;
        bestId = criterion.criterion_id;
      }
      if (!criterion.all_or_nothing && criterion.sub_criteria?.length) visit(criterion.sub_criteria);
    }
  };
  visit(question.grading_rule);
  if (!bestId) return question;

  const apply = (criteria: Criterion[]): Criterion[] =>
    criteria.map((criterion) => {
      if (criterion.criterion_id === bestId && typeof criterion.score === "number") {
        return { ...criterion, score: round2(criterion.score + drift) };
      }
      if (criterion.sub_criteria?.length) return { ...criterion, sub_criteria: apply(criterion.sub_criteria) };
      return criterion;
    });

  return { ...question, grading_rule: apply(question.grading_rule) };
}

export interface RescoreResult {
  question: RubricQuestion;
  /** Set when nothing could be changed, for display next to the input. */
  blocked?: string;
}

export function rescoreQuestion(question: RubricQuestion, target: number): RescoreResult {
  const current = questionTotal(flattenCriteria(question));
  if (target < 0) return { question, blocked: "Điểm không được âm." };
  if (round2(current) === round2(target)) return { question };

  if (current === 0) {
    // Nothing to scale from — only unambiguous when there is a single leaf.
    const leaves = question.grading_rule.filter((c) => !c.sub_criteria?.length);
    if (leaves.length !== 1) {
      return {
        question,
        blocked: "Các tiêu chí đang là 0 điểm nên không có tỉ lệ để chia — nhập điểm cho từng tiêu chí bên dưới trước.",
      };
    }
    return {
      question: {
        ...question,
        grading_rule: question.grading_rule.map((c) => (c === leaves[0] ? { ...c, score: round2(target) } : c)),
      },
    };
  }

  const scaled: RubricQuestion = { ...question, grading_rule: scaleCriteria(question.grading_rule, target / current) };
  return { question: absorbDrift(scaled, target) };
}

const SCORE_IN_TEXT = /(\d+(?:[.,]\d+)?)(\s*điểm)/gi;

/**
 * Rewrite the "(0.5 điểm)" printed in the question text to match a new score.
 *
 * Only acts when the text contains exactly one such mention. Zero means there
 * is nothing to keep in sync; two or more means the extra ones are usually
 * per-part breakdowns ("câu a 1.0 điểm, câu b 0.5 điểm") that a single new
 * total cannot resolve — guessing there would quietly corrupt the prompt the
 * LLM grades from, so it is left to the author.
 *
 * The original number's formatting is preserved: `,` stays `,`, and a value
 * written as `2.0` keeps its trailing zero rather than collapsing to `2`.
 */
/** How many "… điểm" the wording carries — drives the hint next to the input. */
export function countScoreMentions(text: string): number {
  return [...text.matchAll(SCORE_IN_TEXT)].length;
}

export function rewriteScoreInText(text: string, score: number): string | null {
  const matches = [...text.matchAll(SCORE_IN_TEXT)];
  if (matches.length !== 1) return null;

  const [, original, suffix] = matches[0];
  const separator = original.includes(",") ? "," : ".";
  // Show as many decimals as the value genuinely needs, but never fewer than
  // the author wrote: "2.0 điểm" stays "3.0 điểm" rather than snapping to "3",
  // while "0.5 điểm" becomes "2.5", not "2.50".
  const authored = /[.,]/.test(original) ? original.split(/[.,]/)[1].length : 0;
  const needed = (round2(score).toString().split(".")[1] ?? "").length;
  const rendered = score.toFixed(Math.max(authored, needed)).replace(".", separator);

  return text.slice(0, matches[0].index) + rendered + suffix + text.slice(matches[0].index + matches[0][0].length);
}
