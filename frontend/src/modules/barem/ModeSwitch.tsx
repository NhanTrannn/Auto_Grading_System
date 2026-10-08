/**
 * Cơ bản / Nâng cao switch for the barem builder.
 *
 * A segmented control rather than the checkbox it replaces: both modes are
 * named, so the author can see which one they're in without having to know
 * that an unticked "Nâng cao" means "basic". The line beside it says what the
 * current mode leaves out, because a field that silently disappears looks
 * like a field that was deleted.
 *
 * Exposed as a radiogroup (two exclusive options), with arrow keys moving the
 * selection the way a native radio group does.
 */
import type { KeyboardEvent } from "react";

import styles from "./ModeSwitch.module.css";

interface ModeSwitchProps {
  advanced: boolean;
  onChange: (advanced: boolean) => void;
}

const MODES = [
  {
    advanced: false,
    label: "Cơ bản",
    description:
      "Chỉ hiện những gì cần soạn: đề bài, tiêu chí, đáp án. Mã ô trả lời, mã định danh và tên trường JSON được tạo tự động và đang ẩn.",
  },
  {
    advanced: true,
    label: "Nâng cao",
    description:
      "Hiện đủ mọi trường: mã định danh câu, mã bảng, các ô trả lời (slot_id), tên phần và tên trường JSON cạnh từng nhãn.",
  },
] as const;

export default function ModeSwitch({ advanced, onChange }: ModeSwitchProps) {
  const current = MODES.find((mode) => mode.advanced === advanced) ?? MODES[0];

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (["ArrowLeft", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      onChange(false);
    } else if (["ArrowRight", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      onChange(true);
    }
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.switch} role="radiogroup" aria-label="Chế độ hiển thị" onKeyDown={handleKeyDown}>
        {MODES.map((mode) => {
          const active = mode.advanced === advanced;
          return (
            <button
              key={mode.label}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={active ? 0 : -1}
              className={`${styles.option} ${active ? styles.optionActive : ""}`}
              onClick={() => onChange(mode.advanced)}
            >
              {mode.label}
            </button>
          );
        })}
      </div>
      <p className={styles.description}>{current.description}</p>
    </div>
  );
}
