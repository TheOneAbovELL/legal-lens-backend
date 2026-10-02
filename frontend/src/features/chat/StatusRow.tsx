import { Spinner } from "@/components/ui/Spinner";
import { ComplexityBadge } from "@/components/ui/Badge";
import { phaseLabel, type Phase, type StageInfo } from "./chatReducer";

/** Backend-driven progress line (never invented progress). */
export function StatusRow({ phase, stage }: { phase: Phase; stage: StageInfo }) {
  const label = phaseLabel(phase, stage);
  if (!label) return null;
  return (
    <div className="status-row" role="status" aria-live="polite" data-testid="status-row">
      <Spinner label={label} />
      <span>{label}</span>
      <ComplexityBadge complexity={stage.complexity} />
      {stage.profile ? <span className="badge" title="Retrieval profile">{stage.profile}</span> : null}
    </div>
  );
}
