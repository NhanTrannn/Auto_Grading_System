/**
 * Port of pipeline.py's `flatten_criteria()` — a barem entry's nested
 * grading_rule tree collapsed into the flat criterion list graders actually
 * see, with inheritance and group markers resolved.
 *
 * The builder needs this because validation happens on the FLATTENED list, not
 * the authored tree: a sub_criterion's effective score can be derived from its
 * parent's `score` and its own `weight`, wrapper criteria drop out entirely,
 * and group_max_score only exists post-flatten. Validating the tree directly
 * would report scores that pipeline.py never computes.
 *
 * Kept deliberately faithful to the Python, including the quirks:
 *   - `part_label` falls back to the parent's `sub_label` (that is how a
 *     wrapper labelled `sub_label: "a"` reaches its children as part "a").
 *   - grader_note is MERGED parent+child ("\n"), not overridden — both levels'
 *     instructions have to reach the LLM.
 *   - `group_llm_decided` is attached only when the parent has a grader_note
 *     AND the children are `table` (the only case where one batched LLM call
 *     can weigh an aggregate rule).
 */
import type { Criterion, FlatCriterion, RubricQuestion } from "@/types/barem";

export function flattenCriteria(entry: RubricQuestion): FlatCriterion[] {
  const items = entry.grading_rule ?? [];
  if (items.length === 0) return [];

  const flat: FlatCriterion[] = [];

  for (const item of items) {
    const subCriteria = item.sub_criteria ?? [];

    if (subCriteria.length === 0) {
      const criterion: FlatCriterion = { ...item };
      if (criterion.part_label === undefined) {
        criterion.part_label = item.sub_label ?? item.part_label;
      }
      delete criterion.sub_criteria;
      flat.push(criterion);
      continue;
    }

    const groupAllOrNothing = Boolean(item.all_or_nothing);
    const totalWeight = subCriteria.reduce((sum, sc) => sum + (sc.weight || 0), 0);
    const parentNote = item.grader_note;

    for (const sc of subCriteria) {
      const criterion: FlatCriterion = { ...sc };

      if (criterion.part_label === undefined) {
        criterion.part_label = item.part_label || item.sub_label;
      }
      if (criterion.question_type === undefined) {
        criterion.question_type = item.question_type;
      }
      if (!criterion.slot_ids?.length && item.slot_ids?.length) {
        criterion.slot_ids = item.slot_ids;
      }

      const childNote = criterion.grader_note;
      if (parentNote && childNote) {
        criterion.grader_note = `${parentNote}\n${childNote}`;
      } else if (parentNote) {
        criterion.grader_note = parentNote;
      }

      if (groupAllOrNothing) {
        criterion.group_id = item.criterion_id;
        criterion.group_all_or_nothing = true;
        criterion.group_max_score = item.score ?? 0;
      } else {
        // An explicit per-child `score` always wins; `weight` only fills in a
        // score the child never declared.
        if ((criterion.score === null || criterion.score === undefined) && criterion.weight && totalWeight) {
          criterion.score = (item.score ?? 0) * (criterion.weight / totalWeight);
        }
        const childType = criterion.question_type ?? item.question_type;
        if (parentNote && childType === "table") {
          criterion.group_id = item.criterion_id;
          criterion.group_llm_decided = true;
          criterion.group_max_score = item.score ?? 0;
        }
      }

      delete criterion.sub_criteria;
      flat.push(criterion);
    }
  }

  return flat;
}

/** Every leaf criterion of the whole exam, keyed by question_number. */
export function flattenExam(questions: RubricQuestion[]): Map<number, FlatCriterion[]> {
  const byQuestion = new Map<number, FlatCriterion[]>();
  for (const question of questions) {
    byQuestion.set(question.question_number, flattenCriteria(question));
  }
  return byQuestion;
}

/**
 * The score a question really contributes, computed the way validate_barem()
 * does it: all_or_nothing groups count their group_max_score exactly once,
 * everything else sums its own score.
 */
export function questionTotal(flat: FlatCriterion[]): number {
  const seenGroups = new Set<string>();
  let total = 0;
  for (const criterion of flat) {
    if (criterion.group_all_or_nothing) {
      const gid = criterion.group_id;
      if (!gid || seenGroups.has(gid)) continue;
      seenGroups.add(gid);
      total += criterion.group_max_score || 0;
    } else {
      total += criterion.score || 0;
    }
  }
  return total;
}

export function examTotal(questions: RubricQuestion[]): number {
  let total = 0;
  for (const flat of flattenExam(questions).values()) {
    total += questionTotal(flat);
  }
  return Math.round(total * 10000) / 10000;
}
