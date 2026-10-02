import { MappingBadge } from "@/components/ui/Badge";
import type { BnsAlert } from "@/types/api";

/** Structured old-code → new-code comparison, rendered only from backend mapping data. */
export function LegalMappingCard({ alert }: { alert: BnsAlert }) {
  const unavailable = alert.mapping_type === "no_mapping" || alert.mapping_type === "unknown";
  return (
    <section className="mapping" aria-label={`Provision mapping for ${alert.old}`} data-testid="mapping-card">
      <div className="mapping__prov">
        <div className="mapping__code">{alert.old}</div>
        <div className="mapping__label">source provision</div>
      </div>
      <div className="mapping__arrow" aria-hidden="true">→</div>
      <div className="mapping__prov">
        <div className="mapping__code">{alert.new ?? (alert.mapping_type === "no_mapping" ? "No equivalent" : "Unknown")}</div>
        <div className="mapping__label">{alert.new ? "target provision" : unavailable ? "mapping unavailable" : ""}</div>
      </div>
      <div className="mapping__foot">
        <MappingBadge type={alert.mapping_type} />
        {alert.subject ? <span>{alert.subject}</span> : null}
        {alert.effective ? <span>· effective {alert.effective}</span> : null}
        <span>· {alert.verification_status.replace(/_/g, " ")}</span>
        {alert.mapping_type === "ambiguous" ? <span>· sources disagree; verify before relying on it</span> : null}
        {alert.notes ? <span style={{ flexBasis: "100%" }}>{alert.notes}</span> : null}
      </div>
    </section>
  );
}
