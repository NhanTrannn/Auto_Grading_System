import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";

import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "lg" | "md" | "sm";

interface BaseProps {
  variant?: Variant;
  size?: Size;
  block?: boolean;
  loading?: boolean;
  icon?: ReactNode;
}

interface ButtonProps extends BaseProps, ButtonHTMLAttributes<HTMLButtonElement> {
  to?: undefined;
}

interface LinkProps extends BaseProps {
  to: string;
  children?: ReactNode;
  onClick?: () => void;
}

function classNames(variant: Variant, size: Size, block?: boolean, loading?: boolean) {
  return [
    styles.button,
    styles[variant],
    styles[size],
    block ? styles.block : "",
    loading ? styles.loading : "",
  ]
    .filter(Boolean)
    .join(" ");
}

export default function Button({
  variant = "primary",
  size = "md",
  block,
  loading,
  icon,
  to,
  ...rest
}: ButtonProps | LinkProps) {
  const className = classNames(variant, size, block, loading);

  if (to !== undefined) {
    const { children, onClick } = rest as LinkProps;
    return (
      <Link to={to} className={className} onClick={onClick}>
        {icon && <span className={styles.icon}>{icon}</span>}
        {children}
      </Link>
    );
  }

  const { children, disabled, ...buttonRest } = rest as ButtonHTMLAttributes<HTMLButtonElement>;
  return (
    <button className={className} disabled={disabled || loading} {...buttonRest}>
      {loading && <span className={styles.spinner} aria-hidden />}
      {!loading && icon && <span className={styles.icon}>{icon}</span>}
      {children}
    </button>
  );
}
