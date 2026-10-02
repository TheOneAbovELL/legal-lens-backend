import { forwardRef, type ButtonHTMLAttributes } from "react";
import type { Citation } from "@/types/api";
import { Tooltip } from "./Tooltip";

/** "IPC §420", "Art. 21", or a case/document title — the short legal reference for a citation. */
export function citationLabel(c: Pick<Citation, "act" | "section" | "case_name" | "title">): string {
  if (c.act && c.section) {
    const isConstitution = c.act.toUpperCase() === "CONSTITUTION";
    return isConstitution ? `Art. ${c.section}` : `${c.act} §${c.section}`;
  }
  if (c.case_name) return c.case_name;
  return c.title;
}

interface ChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  citation: Citation;
  active?: boolean;
  /** Show only the id (inside dense answer text) or id + label (sources row). */
  compact?: boolean;
  preview?: boolean;
}

export const CitationChip = forwardRef<HTMLButtonElement, ChipProps>(function CitationChip(
  { citation, active, compact, preview = true, className, type = "button", ...rest },
  ref,
) {
  const label = citationLabel(citation);
  const classes = ["cite"];
  if (active) classes.push("cite--active");
  if (className) classes.push(className);
  const button = (
    <button ref={ref} type={type} className={classes.join(" ")} aria-label={`Citation ${citation.citation_id}: ${label}`}
      aria-pressed={active || undefined} {...rest}>
      <span className="cite__id">{citation.citation_id}</span>
      {compact ? null : <span>{label}</span>}
    </button>
  );
  if (!preview) return button;
  return (
    <Tooltip content={<SourcePreview citation={citation} />}>
      {button}
    </Tooltip>
  );
});

export function SourcePreview({ citation }: { citation: Citation }) {
  return (
    <>
      <p className="tip__title">{citationLabel(citation)}</p>
      <p className="tip__meta">{citation.title}{citation.section_heading ? ` · ${citation.section_heading}` : ""}{citation.page ? ` · p. ${citation.page}` : ""}</p>
      {citation.excerpt ? <p className="tip__excerpt">{citation.excerpt}</p> : <p className="tip__excerpt">No excerpt stored.</p>}
    </>
  );
}
