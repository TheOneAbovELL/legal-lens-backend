import type { HTMLAttributes, ReactNode } from "react";

export function Card({ selected, className, children, ...rest }: { selected?: boolean; children: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  const classes = ["card"];
  if (selected) classes.push("card--selected");
  if (className) classes.push(className);
  return <div className={classes.join(" ")} {...rest}>{children}</div>;
}

export function Skeleton({ width = "100%", lines = 1 }: { width?: string; lines?: number }) {
  return (
    <div className="stack" aria-hidden="true" style={{ gap: 8 }}>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="skeleton" style={{ width: i === lines - 1 && lines > 1 ? "60%" : width }} />
      ))}
    </div>
  );
}

export function Alert({ tone = "info", title, children, action }: { tone?: "info" | "warning" | "danger"; title?: string; children: ReactNode; action?: ReactNode }) {
  const icon = tone === "danger" ? "⚠" : tone === "warning" ? "!" : "i";
  return (
    <div className={`alert alert--${tone}`} role={tone === "danger" ? "alert" : "status"}>
      <span aria-hidden="true" style={{ fontWeight: 700 }}>{icon}</span>
      <div className="alert__body">
        {title ? <p className="alert__title">{title}</p> : null}
        <div>{children}</div>
      </div>
      {action}
    </div>
  );
}
