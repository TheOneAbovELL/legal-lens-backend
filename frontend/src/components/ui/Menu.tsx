import { useEffect, useId, useRef, useState, type ReactNode } from "react";

interface MenuItem {
  label: string;
  onSelect: () => void;
  danger?: boolean;
}

/** Small dropdown with click-outside and Escape handling (used by account and conversation menus). */
export function Menu({ trigger, items, header, label }: { trigger: ReactNode; items: MenuItem[]; header?: ReactNode; label: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button type="button" className="btn btn--ghost btn--sm" aria-haspopup="menu" aria-expanded={open} aria-controls={id}
        aria-label={label} onClick={() => setOpen((o) => !o)}>
        {trigger}
      </button>
      {open ? (
        <div id={id} className="menu" role="menu">
          {header ? <div className="menu__meta">{header}</div> : null}
          {items.map((item) => (
            <button key={item.label} type="button" role="menuitem" className="menu__item"
              style={item.danger ? { color: "var(--danger)" } : undefined}
              onClick={() => { setOpen(false); item.onSelect(); }}>
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
