import type { ReactNode } from "react";
import { AlertTriangle, Info, OctagonAlert } from "lucide-react";

export type NoticeTone = "neutral" | "info" | "warn" | "danger";

/** Inline notice: used for insufficient evidence, failures, degraded search — never a card wall. */
export function Notice({ tone = "neutral", title, children, action }: { tone?: NoticeTone; title?: string; children: ReactNode; action?: ReactNode }) {
  const Icon = tone === "danger" ? OctagonAlert : tone === "warn" ? AlertTriangle : Info;
  return (
    <div className={`notice${tone !== "neutral" ? ` notice--${tone}` : ""}`} role={tone === "danger" ? "alert" : "status"}>
      <Icon aria-hidden="true" />
      <div className="notice__body">
        {title ? <p className="notice__title">{title}</p> : null}
        <div>{children}</div>
      </div>
      {action ? <div className="notice__action">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ lines = 1, width = "100%" }: { lines?: number; width?: string }) {
  return (
    <div className="stack" aria-hidden="true" style={{ gap: 8 }}>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="skeleton" style={{ width: i === lines - 1 && lines > 1 ? "62%" : width }} />
      ))}
    </div>
  );
}
