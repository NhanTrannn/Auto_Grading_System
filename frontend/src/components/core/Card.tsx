import type { ReactNode } from "react";

import styles from "./Card.module.css";

interface CardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  padded?: boolean;
  className?: string;
  children: ReactNode;
}

export default function Card({
  title,
  subtitle,
  actions,
  padded = true,
  className = "",
  children,
}: CardProps) {
  return (
    <section className={`${styles.card} ${className}`}>
      {(title || actions) && (
        <header className={styles.header}>
          <div className={styles.titleGroup}>
            {title && <h2 className={styles.title}>{title}</h2>}
            {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          </div>
          {actions && <div className={styles.actions}>{actions}</div>}
        </header>
      )}
      <div className={padded ? styles.body : styles.bodyFlush}>{children}</div>
    </section>
  );
}
