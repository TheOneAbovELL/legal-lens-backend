export function BrandMark({ size = 26 }: { size?: number }) {
  return (
    <svg className="brand__mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="7" fill="var(--accent)" />
      <circle cx="14" cy="14" r="7" fill="none" stroke="var(--on-accent)" strokeWidth="2.5" />
      <line x1="19.5" y1="19.5" x2="26" y2="26" stroke="var(--on-accent)" strokeWidth="3" strokeLinecap="round" />
      <line x1="10" y1="14" x2="18" y2="14" stroke="#c9a227" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function AuthBrand() {
  return (
    <div className="auth__brand">
      <BrandMark size={32} />
      <span>Legal Lens</span>
    </div>
  );
}
