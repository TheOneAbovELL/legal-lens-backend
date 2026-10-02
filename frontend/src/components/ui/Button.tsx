import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Spinner } from "./Spinner";

export type ButtonVariant = "primary" | "accent" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  loading?: boolean;
  icon?: ReactNode;
  children?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "ghost", size = "md", block, loading, icon, className, children, disabled, type = "button", ...rest },
  ref,
) {
  const classes = ["btn", `btn--${variant}`];
  if (size !== "md") classes.push(`btn--${size}`);
  if (block) classes.push("btn--block");
  if (className) classes.push(className);
  return (
    <button ref={ref} type={type} className={classes.join(" ")} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
});

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  size?: ButtonSize;
  variant?: ButtonVariant;
  children: ReactNode;
}

/** Icon-only button: the accessible name comes from `label` (also used as the tooltip). */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, size = "md", variant = "ghost", className, children, type = "button", ...rest },
  ref,
) {
  const classes = ["btn", "btn--icon", `btn--${variant}`];
  if (size !== "md") classes.push(`btn--${size}`);
  if (className) classes.push(className);
  return (
    <button ref={ref} type={type} className={classes.join(" ")} aria-label={label} title={label} {...rest}>
      {children}
    </button>
  );
});
