import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export interface MenuItem {
  label: string;
  icon?: ReactNode;
  onSelect: () => void;
  danger?: boolean;
}

interface Props {
  trigger: (props: { open: boolean; toggle: () => void; id: string }) => ReactNode;
  items: MenuItem[];
  header?: ReactNode;
  align?: "left" | "right";
}

/** Dropdown with click-outside, Escape and arrow-key navigation. The trigger is render-prop so any
 * button (icon or avatar) can open it. */
export function Menu({ trigger, items, header, align = "right" }: Props) {
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
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        const nodes = Array.from(ref.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
        if (!nodes.length) return;
        e.preventDefault();
        const idx = nodes.indexOf(document.activeElement as HTMLElement);
        const next = e.key === "ArrowDown" ? (idx + 1) % nodes.length : (idx - 1 + nodes.length) % nodes.length;
        nodes[next]?.focus();
      }
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    ref.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div ref={ref} className="menu-anchor">
      {trigger({ open, toggle: () => setOpen((o) => !o), id })}
      {open ? (
        <div id={id} className={`menu${align === "left" ? " menu--left" : ""}`} role="menu">
          {header ? <div className="menu__head">{header}</div> : null}
          {items.map((item) => (
            <button key={item.label} type="button" role="menuitem" className={`menu__item${item.danger ? " menu__item--danger" : ""}`}
              onClick={() => { setOpen(false); item.onSelect(); }}>
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
