import { useTheme } from "@/hooks/useTheme";

import { IconMoon, IconSun } from "./Icon";
import styles from "./ThemeToggle.module.css";

export default function ThemeToggle() {
  const { toggle, isDark } = useTheme();

  return (
    <button
      type="button"
      className={styles.toggle}
      onClick={toggle}
      title={isDark ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}
      aria-label={isDark ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}
    >
      {isDark ? <IconSun size={15} /> : <IconMoon size={15} />}
      <span className={styles.label}>{isDark ? "Sáng" : "Tối"}</span>
    </button>
  );
}
