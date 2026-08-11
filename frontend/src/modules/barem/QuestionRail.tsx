/**
 * Narrow left rail listing the questions.
 *
 * Deliberately holds nothing but navigation: one row per question showing its
 * number, its real score and whether it has errors. Everything else that used
 * to share this column (exam fields, validation, JSON) moved out, because the
 * question editor below is dense — tables, criteria trees, conditional branches
 * — and needs the width far more than a sidebar does.
 *
 * The "add question" presets stay collapsed behind a button so four
 * two-line cards don't permanently occupy a 200px column.
 */
import { useState } from "react";

import { IconChevronRight, IconPlus } from "@/components/core/Icon";
import type { QuestionPreset, RubricQuestion } from "@/types/barem";

import { PRESET_INFO } from "./factory";
import { flattenCriteria, questionTotal } from "./flatten";
import styles from "./QuestionRail.module.css";

interface QuestionRailProps {
  questions: RubricQuestion[];
  selected: number | null;
  /** question_number values that currently have at least one error. */
  errorQuestions: Set<number>;
  onSelect: (questionNumber: number) => void;
  onAdd: (preset: QuestionPreset) => void;
}

export default function QuestionRail({
  questions,
  selected,
  errorQuestions,
  onSelect,
  onAdd,
}: QuestionRailProps) {
  const [addOpen, setAddOpen] = useState(false);

  return (
    <div className={styles.rail}>
      <div className={styles.head}>
        <span className={styles.headTitle}>Câu hỏi</span>
        <span className={styles.headCount}>{questions.length}</span>
      </div>

      <div className={styles.list}>
        {questions.length === 0 && <p className={styles.empty}>Chưa có câu nào.</p>}
        {questions.map((question) => {
          const total = questionTotal(flattenCriteria(question));
          const active = selected === question.question_number;
          const hasError = errorQuestions.has(question.question_number);
          return (
            <button
              key={question.question_number}
              type="button"
              className={`${styles.item} ${active ? styles.itemActive : ""}`}
              onClick={() => onSelect(question.question_number)}
            >
              <span className={styles.itemNumber}>
                Câu {question.question_number}
                {hasError && <span className={styles.errorDot} title="Câu này có lỗi" />}
              </span>
              <span className={styles.itemScore}>{total.toFixed(2)}đ</span>
            </button>
          );
        })}
      </div>

      <div className={styles.addBox}>
        <button
          type="button"
          className={`${styles.addToggle} ${addOpen ? styles.addToggleOpen : ""}`}
          onClick={() => setAddOpen((open) => !open)}
        >
          <IconPlus size={13} />
          Thêm câu
          <span className={styles.addChevron}>
            <IconChevronRight size={13} />
          </span>
        </button>

        {addOpen && (
          <div className={styles.presets}>
            {(Object.keys(PRESET_INFO) as QuestionPreset[]).map((preset) => (
              <button
                key={preset}
                type="button"
                className={styles.preset}
                onClick={() => {
                  onAdd(preset);
                  setAddOpen(false);
                }}
              >
                <span className={styles.presetLabel}>{PRESET_INFO[preset].label}</span>
                <span className={styles.presetHint}>{PRESET_INFO[preset].hint}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
