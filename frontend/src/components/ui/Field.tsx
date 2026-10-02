import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface FieldBase {
  label: string;
  error?: string | null;
  hint?: string;
  /** Visually hide the label (it stays available to assistive technology). */
  hideLabel?: boolean;
}

function Wrap({ id, label, hideLabel, error, hint, children }: FieldBase & { id: string; children: ReactNode }) {
  return (
    <div className="field">
      <label className={hideLabel ? "sr-only" : "field__label"} htmlFor={id}>{label}</label>
      {children}
      {error ? <span id={`${id}-error`} className="field__error" role="alert">{error}</span>
        : hint ? <span id={`${id}-hint`} className="field__hint">{hint}</span> : null}
    </div>
  );
}

export function Input({ label, error, hint, hideLabel, id, className, ...rest }: FieldBase & InputHTMLAttributes<HTMLInputElement>) {
  const auto = useId();
  const inputId = id ?? auto;
  return (
    <Wrap id={inputId} label={label} hideLabel={hideLabel} error={error} hint={hint}>
      <input id={inputId} className={["input", className].filter(Boolean).join(" ")} aria-invalid={error ? "true" : undefined}
        aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined} {...rest} />
    </Wrap>
  );
}

export function Textarea({ label, error, hint, hideLabel, id, className, ...rest }: FieldBase & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const auto = useId();
  const inputId = id ?? auto;
  return (
    <Wrap id={inputId} label={label} hideLabel={hideLabel} error={error} hint={hint}>
      <textarea id={inputId} className={["textarea", className].filter(Boolean).join(" ")} aria-invalid={error ? "true" : undefined}
        aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined} {...rest} />
    </Wrap>
  );
}

export function Select({ label, error, hint, hideLabel, id, className, children, ...rest }: FieldBase & SelectHTMLAttributes<HTMLSelectElement>) {
  const auto = useId();
  const inputId = id ?? auto;
  return (
    <Wrap id={inputId} label={label} hideLabel={hideLabel} error={error} hint={hint}>
      <select id={inputId} className={["select", className].filter(Boolean).join(" ")} {...rest}>{children}</select>
    </Wrap>
  );
}
