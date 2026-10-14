/**
 * Delete button that needs a second click within a few seconds.
 *
 * Deleting a question, part, table or criterion used to happen on the first
 * click, and the only way back was "Hoàn tác" at the top of the page — usually
 * scrolled out of sight by the time you are deep in a criterion tree. A native
 * confirm() would block the page and reads as an error dialog; arming the
 * button in place keeps the decision where the cursor already is.
 */
import { useEffect, useState } from "react";

import Button from "./Button";

import styles from "./ConfirmDelete.module.css";

const ARM_MS = 3000;

interface ConfirmDeleteProps {
  label: string;
  onConfirm: () => void;
  /** Render as the core Button (default) or as a compact inline text button. */
  compact?: boolean;
  /** Text while waiting for the second click. */
  armedLabel?: string;
  /** Core Button variant before arming; it always turns `danger` once armed. */
  variant?: "danger" | "secondary" | "ghost";
  size?: "sm" | "md";
}

export default function ConfirmDelete({
  label,
  onConfirm,
  compact,
  armedLabel = "Bấm lần nữa để xoá",
  variant = "danger",
  size = "sm",
}: ConfirmDeleteProps) {
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    if (!armed) return;
    const timer = window.setTimeout(() => setArmed(false), ARM_MS);
    return () => window.clearTimeout(timer);
  }, [armed]);

  function handleClick() {
    if (armed) {
      setArmed(false);
      onConfirm();
    } else {
      setArmed(true);
    }
  }

  const text = armed ? armedLabel : label;

  if (compact) {
    return (
      <button
        type="button"
        className={`${styles.compact} ${armed ? styles.compactArmed : ""}`}
        onClick={handleClick}
      >
        {text}
      </button>
    );
  }

  return (
    <Button size={size} variant={armed ? "danger" : variant} onClick={handleClick}>
      {text}
    </Button>
  );
}
