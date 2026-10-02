import { Link } from "react-router-dom";

/** Abstract mark: a lens over a line of text — clarity applied to a document. Readable at 16px. */
export function BrandMark({ size = 22 }: { size?: number }) {
  return (
    <svg className="brand__mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="7" fill="var(--ink)" />
      <circle cx="15" cy="15" r="7.5" fill="none" stroke="var(--bg)" strokeWidth="2.2" />
      <path d="M20.5 20.5 L26 26" stroke="var(--bg)" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M11 15 H19" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
      <path d="M12.5 11.8 H17.5" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" opacity="0.75" />
    </svg>
  );
}

export function Brand({ to = "/app", large, asLink = true }: { to?: string; large?: boolean; asLink?: boolean }) {
  const inner = (
    <>
      <BrandMark size={large ? 30 : 22} />
      <span className="brand__word">Legal Lens</span>
    </>
  );
  const cls = `brand${large ? " brand--lg" : ""}`;
  return asLink ? <Link to={to} className={cls} aria-label="Legal Lens home">{inner}</Link> : <span className={cls}>{inner}</span>;
}
