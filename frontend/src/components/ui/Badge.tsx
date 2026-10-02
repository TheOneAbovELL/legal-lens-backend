import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "accent" | "success" | "warning" | "danger";

export function Badge({ tone = "neutral", children, title, className }: { tone?: BadgeTone; children: ReactNode; title?: string; className?: string }) {
  const classes = ["badge"];
  if (tone !== "neutral") classes.push(`badge--${tone}`);
  if (className) classes.push(className);
  return <span className={classes.join(" ")} title={title}>{children}</span>;
}

export function ComplexityBadge({ complexity }: { complexity: string | null | undefined }) {
  if (!complexity) return null;
  const tone: BadgeTone = complexity === "COMPLEX" ? "warning" : complexity === "MODERATE" ? "accent" : "success";
  return <Badge tone={tone} title={`Query complexity: ${complexity}`}>{complexity}</Badge>;
}

export function MappingBadge({ type }: { type: string }) {
  const tone: BadgeTone = type === "exact" ? "success" : type === "approximate" ? "accent" : type === "ambiguous" ? "warning" : type === "no_mapping" ? "danger" : "neutral";
  const label = type.replace("_", " ");
  return <Badge tone={tone} title={`Mapping status: ${label}`}>{label}</Badge>;
}
