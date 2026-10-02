import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "accent" | "ok" | "warn" | "danger";

export function Badge({ tone = "neutral", dot, children, title }: { tone?: BadgeTone; dot?: boolean; children: ReactNode; title?: string }) {
  const classes = ["badge"];
  if (tone !== "neutral") classes.push(`badge--${tone}`);
  if (dot) classes.push("badge--dot");
  return <span className={classes.join(" ")} title={title}>{children}</span>;
}

/** Routing verdict, shown only where it informs the user (metadata rows). */
export function ComplexityBadge({ complexity }: { complexity: string | null | undefined }) {
  if (!complexity) return null;
  return <Badge title={`Question complexity: ${complexity.toLowerCase()}`}>{complexity}</Badge>;
}

export function MappingBadge({ type }: { type: string }) {
  const tone: BadgeTone = type === "exact" ? "ok" : type === "approximate" ? "accent" : type === "ambiguous" ? "warn" : type === "no_mapping" ? "danger" : "neutral";
  const label: Record<string, string> = { exact: "exact mapping", approximate: "approximate", ambiguous: "ambiguous", no_mapping: "no equivalent", unknown: "not in dataset" };
  return <Badge tone={tone}>{label[type] ?? type.replace(/_/g, " ")}</Badge>;
}

export type Health = "healthy" | "degraded" | "unavailable" | "unknown";

/** Plain status word with a dot: healthy / degraded / unavailable (diagnostics, settings). */
export function StatusText({ health, children }: { health: Health; children?: ReactNode }) {
  return <span className={`status${health === "unknown" ? "" : ` status--${health}`}`}>{children ?? health}</span>;
}
