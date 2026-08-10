import styles from "./Spinner.module.css";

export default function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span
      className={styles.spinner}
      style={{ width: size, height: size, borderWidth: Math.max(2, Math.round(size / 8)) }}
      aria-hidden
    />
  );
}
