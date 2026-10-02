import { cloneElement, useId, useRef, useState, type ReactElement, type ReactNode } from "react";

interface Props {
  content: ReactNode;
  children: ReactElement<Record<string, unknown>>;
  /** Delay before showing on hover (ms). */
  delay?: number;
  align?: "left" | "right";
}

/**
 * Hover/focus tooltip for rich previews (citation chips). The trigger keeps its own semantics;
 * the bubble is referenced through aria-describedby while visible and closes on Escape/blur.
 */
export function Tooltip({ content, children, delay = 160, align = "left" }: Props) {
  const [open, setOpen] = useState(false);
  const timer = useRef<number | null>(null);
  const id = useId();
  const show = () => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), delay);
  };
  const hide = () => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = null;
    setOpen(false);
  };
  const trigger = cloneElement(children, {
    onMouseEnter: show,
    onMouseLeave: hide,
    onFocus: show,
    onBlur: hide,
    onKeyDown: (e: KeyboardEvent) => {
      if (e.key === "Escape") hide();
      const original = children.props.onKeyDown;
      if (typeof original === "function") original(e);
    },
    "aria-describedby": open ? id : undefined,
  });
  return (
    <span className="tip">
      {trigger}
      {open ? <span role="tooltip" id={id} className={`tip__bubble${align === "right" ? " tip__bubble--right" : ""}`}>{content}</span> : null}
    </span>
  );
}
