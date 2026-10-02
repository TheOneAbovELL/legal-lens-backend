import { useId, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface FieldBase {
  label: string;
  error?: string | null;
  hint?: string;
}

export function Input({ label, error, hint, id, className, ...rest }: FieldBase & InputHTMLAttributes<HTMLInputElement>) {
  const auto = useId();
  const inputId = id ?? auto;
  const errorId = `${inputId}-error`;
  return (
    <div className="field">
      <label className="field__label" htmlFor={inputId}>{label}</label>
      <input id={inputId} className={["input", className].filter(Boolean).join(" ")} aria-invalid={error ? "true" : undefined}
        aria-describedby={error ? errorId : undefined} {...rest} />
      {error ? <span id={errorId} className="field__error" role="alert">{error}</span> : hint ? <span className="field__hint">{hint}</span> : null}
    </div>
  );
}

export function Textarea({ label, error, hint, id, className, ...rest }: FieldBase & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const auto = useId();
  const inputId = id ?? auto;
  const errorId = `${inputId}-error`;
  return (
    <div className="field">
      <label className="field__label" htmlFor={inputId}>{label}</label>
      <textarea id={inputId} className={["textarea", className].filter(Boolean).join(" ")} aria-invalid={error ? "true" : undefined}
        aria-describedby={error ? errorId : undefined} {...rest} />
      {error ? <span id={errorId} className="field__error" role="alert">{error}</span> : hint ? <span className="field__hint">{hint}</span> : null}
    </div>
  );
}
