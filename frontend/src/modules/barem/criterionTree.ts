/**
 * Identity handling for the criterion tree.
 *
 * The editor addresses criteria by `criterion_id`, which only works while ids
 * are unique — and two things conspired to break that:
 *
 *   - New ids were numbered by sibling count (`T1_${criteria.length + 1}`), so
 *     adding two criteria, deleting the first, then adding another produced a
 *     second `T1_2`.
 *   - `replaceCriterion` mapped over the whole tree and swapped in the *same*
 *     object at every id match, so those two entries stopped being separate
 *     data at all. Editing one changed both, which on screen looked like two
 *     criteria sharing a single partial_credit_rule.
 *
 * Numbering now skips ids already in use, and replacement stops after the first
 * hit so a duplicate typed by hand degrades to "the wrong one got edited"
 * rather than "both silently became one" — validate_barem() flags the duplicate
 * either way.
 */
import type { Criterion } from "@/types/barem";

export function collectCriterionIds(criteria: Criterion[], into = new Set<string>()): Set<string> {
  for (const criterion of criteria) {
    if (criterion.criterion_id) into.add(criterion.criterion_id);
    if (criterion.sub_criteria?.length) collectCriterionIds(criterion.sub_criteria, into);
  }
  return into;
}

/** `base` itself when free, else `base` with the lowest free numeric suffix. */
export function uniqueCriterionId(base: string, taken: Set<string>): string {
  if (!taken.has(base)) return base;

  const match = base.match(/^(.*?)(\d+)$/);
  const stem = match ? match[1] : `${base}_`;
  let n = match ? Number(match[2]) : 2;
  let candidate = `${stem}${n}`;
  while (taken.has(candidate)) {
    n += 1;
    candidate = `${stem}${n}`;
  }
  return candidate;
}

/** Replace (or delete, with `null`) the first criterion carrying `id`. */
export function replaceCriterion(criteria: Criterion[], id: string, next: Criterion | null): Criterion[] {
  let done = false;

  const walk = (items: Criterion[]): Criterion[] =>
    items
      .map((criterion) => {
        if (done) return criterion;
        if (criterion.criterion_id === id) {
          done = true;
          return next;
        }
        if (criterion.sub_criteria?.length) {
          return { ...criterion, sub_criteria: walk(criterion.sub_criteria) };
        }
        return criterion;
      })
      .filter((criterion): criterion is Criterion => criterion !== null);

  return walk(criteria);
}
