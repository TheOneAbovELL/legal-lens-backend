import { Check, Circle, CircleDot } from "lucide-react";
import { PHASES, phaseLabel, type Phase, type StageInfo } from "./chatReducer";

/**
 * Backend-driven progress: a one-line status, the four coarse steps, and — for decomposed
 * questions — the research aspects (sub-queries) with their completion. Never invents progress and
 * never shows reasoning.
 */
export function ResearchProgress({ phase, stage }: { phase: Phase; stage: StageInfo }) {
  const label = phaseLabel(phase, stage);
  if (!label) return null;
  const current = PHASES.findIndex((p) => p.key === phase);
  return (
    <div className="progress" role="status" aria-live="polite" data-testid="status-row">
      <div className="progress__line">
        <span className="pulse-dot" aria-hidden="true" />
        <span>{label}…</span>
        {stage.complexity ? <span className="t-meta">{stage.complexity.toLowerCase()} question{stage.profile ? ` · ${stage.profile.toLowerCase()} retrieval` : ""}</span> : null}
      </div>
      <div className="progress__steps" aria-hidden="true">
        {PHASES.map((p, i) => {
          const state = i < current ? "done" : i === current ? "active" : "todo";
          const Icon = state === "done" ? Check : state === "active" ? CircleDot : Circle;
          return (
            <span key={p.key} className={`progress__step progress__step--${state}`}>
              <Icon />
              {p.label}
            </span>
          );
        })}
      </div>
      {stage.aspects && stage.aspects.length > 1 ? (
        <div className="research" data-testid="research-aspects">
          <span className="research__title">Researching {stage.aspects.length} legal aspects</span>
          {stage.aspects.map((a) => (
            <span key={a.id} className={`research__item${a.done ? " research__item--done" : ""}`}>
              {a.done ? <Check aria-label="done" /> : <Circle aria-label="pending" />}
              {a.label}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
