import type { ReactNode } from "react";

import styles from "./Tabs.module.css";

export interface TabItem<T extends string> {
  id: T;
  label: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
}

interface TabsProps<T extends string> {
  items: TabItem<T>[];
  active: T;
  onChange: (id: T) => void;
}

export default function Tabs<T extends string>({ items, active, onChange }: TabsProps<T>) {
  return (
    <div className={styles.tabs} role="tablist">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={item.id === active}
          className={`${styles.tab} ${item.id === active ? styles.active : ""}`}
          onClick={() => onChange(item.id)}
        >
          {item.icon && <span className={styles.icon}>{item.icon}</span>}
          <span className={styles.labels}>
            <span className={styles.label}>{item.label}</span>
            {item.hint && <span className={styles.hint}>{item.hint}</span>}
          </span>
        </button>
      ))}
    </div>
  );
}
