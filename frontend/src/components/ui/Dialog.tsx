import { useEffect, useRef, type ReactNode } from "react";

interface DialogProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  actions?: ReactNode;
}

/** Minimal accessible modal: focus moves in, Escape/backdrop close, focus returns on close. */
export function Dialog({ open, title, onClose, children, actions }: DialogProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("button, input, textarea, [tabindex]")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="dialog-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={ref} className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
        <h2 id="dialog-title" className="dialog__title">{title}</h2>
        <div>{children}</div>
        {actions ? <div className="dialog__actions">{actions}</div> : null}
      </div>
    </div>
  );
}

/** Side sheet used for evidence (right) and conversations (left) on narrow screens. */
export function Drawer({ open, side = "right", title, onClose, children }: { open: boolean; side?: "left" | "right"; title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <aside className={`drawer${side === "left" ? " drawer--left" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="evidence__head">
          <span>{title}</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onClose} aria-label={`Close ${title}`}>✕</button>
        </div>
        {children}
      </aside>
    </>
  );
}
