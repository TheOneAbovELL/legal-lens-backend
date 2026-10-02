import { ArrowRight } from "lucide-react";
import { MappingBadge } from "@/components/ui/Badge";
import type { BnsAlert } from "@/types/api";

/** Old-code → new-code correspondence, rendered only from backend mapping data. */
export function MappingComparison({ alerts }: { alerts: BnsAlert[] }) {
  if (alerts.length === 0) return null;
  return (
    <section className="map" aria-label="Provision mapping" data-testid="mapping-card">
      <p className="map__kicker">Provision mapping</p>
      <div className="stack" style={{ gap: 14 }}>
        {alerts.map((alert) => {
          const unavailable = alert.mapping_type === "no_mapping" || alert.mapping_type === "unknown";
          return (
            <div key={`${alert.old}-${alert.new ?? ""}`}>
              <div className="map__row">
                <div className="map__prov">
                  <div className="map__code">{alert.old}</div>
                  <div className="map__label">source provision</div>
                </div>
                <div className="map__arrow" aria-hidden="true"><ArrowRight /></div>
                <div className="map__prov">
                  <div className="map__code">{alert.new ?? (alert.mapping_type === "no_mapping" ? "No equivalent" : "Not in dataset")}</div>
                  <div className="map__label">{alert.new ? "target provision" : unavailable ? "mapping unavailable" : ""}</div>
                </div>
              </div>
              <div className="map__foot">
                <MappingBadge type={alert.mapping_type} />
                {alert.subject ? <span>{alert.subject}</span> : null}
                {alert.effective ? <span>effective {alert.effective}</span> : null}
                <span>{alert.verification_status.replace(/_/g, " ")}</span>
                {alert.mapping_type === "ambiguous" ? <span className="map__note">Sources disagree on this correspondence; verify before relying on it.</span> : null}
                {alert.notes ? <span className="map__note">{alert.notes}</span> : null}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
