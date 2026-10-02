import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Spinner } from "./Spinner";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "primary" | "ghost" | "danger";
  size?: "md" | "sm";
  icon?: boolean;
  block?: boolean;
  loading?: boolean;
  children?: ReactNode;
}

export function Button({ variant = "default", size = "md", icon, block, loading, className, children, disabled, type = "button", ...rest }: ButtonProps) {
  const classes = ["btn"];
  if (variant !== "default") classes.push(`btn--${variant}`);
  if (size === "sm") classes.push("btn--sm");
  if (icon) classes.push("btn--icon");
  if (block) classes.push("btn--block");
  if (className) classes.push(className);
  return (
    <button type={type} className={classes.join(" ")} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <Spinner /> : null}
      {children}
    </button>
  );
}
