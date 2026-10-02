import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { IconButton } from "./Button";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Shared behaviour: Escape closes, focus moves in and is trapped, focus returns on close. */
function useOverlay(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const node = ref.current;
    const first = node?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? node)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key === "Tab" && node) {
        const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE));
        if (items.length === 0) return;
        const firstItem = items[0]!;
        const lastItem = items[items.length - 1]!;
        if (e.shiftKey && document.activeElement === firstItem) {
          e.preventDefault();
          lastItem.focus();
        } else if (!e.shiftKey && document.activeElement === lastItem) {
          e.preventDefault();
          firstItem.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, [open, onClose]);
  return ref;
}

interface DialogProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  actions?: ReactNode;
}

export function Dialog({ open, title, onClose, children, actions }: DialogProps) {
  const ref = useOverlay(open, onClose);
  if (!open) return null;
  return (
    <>
      <div className="scrim" aria-hidden="true" onClick={onClose} />
      <div className="dialog-wrap" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
        <div ref={ref} className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title" tabIndex={-1}>
          <h2 id="dialog-title" className="dialog__title">{title}</h2>
          <div className="dialog__body">{children}</div>
          {actions ? <div className="dialog__actions">{actions}</div> : null}
        </div>
      </div>
    </>
  );
}

interface PanelProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Extra controls rendered in the header (e.g. next/previous). */
  tools?: ReactNode;
}

/** Side drawer (left: navigation, right: evidence on tablets). */
export function Drawer({ open, title, onClose, children, tools, side = "left" }: PanelProps & { side?: "left" | "right" }) {
  const ref = useOverlay(open, onClose);
  if (!open) return null;
  return (
    <>
      <div className="scrim" aria-hidden="true" onClick={onClose} />
      <aside ref={ref} className={`drawer${side === "right" ? " drawer--right" : ""}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1}>
        <div className="overlay__head">
          <span className="overlay__title">{title}</span>
          {tools}
          <IconButton label={`Close ${title}`} size="sm" onClick={onClose}><X /></IconButton>
        </div>
        <div className="overlay__body">{children}</div>
      </aside>
    </>
  );
}

/** Bottom sheet for phones (evidence, options). */
export function Sheet({ open, title, onClose, children, tools }: PanelProps) {
  const ref = useOverlay(open, onClose);
  if (!open) return null;
  return (
    <>
      <div className="scrim" aria-hidden="true" onClick={onClose} />
      <section ref={ref} className="sheet" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1}>
        <div className="sheet__grip" aria-hidden="true" />
        <div className="overlay__head">
          <span className="overlay__title">{title}</span>
          {tools}
          <IconButton label={`Close ${title}`} size="sm" onClick={onClose}><X /></IconButton>
        </div>
        <div className="overlay__body">{children}</div>
      </section>
    </>
  );
}
