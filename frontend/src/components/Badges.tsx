import type { Decision, Outcome } from "../types";

export const OUTCOME_LABEL: Record<Outcome, string> = {
  won: "Gagné",
  lost: "Perdu",
  open: "En cours",
  void: "Annulé",
};

export const DECISION_LABEL: Record<Decision, string> = {
  played: "Joué",
  skipped: "Passé",
  pending: "En attente",
};

export function OutcomeBadge({ outcome, muted = false }: { outcome: Outcome; muted?: boolean }) {
  return <span className={`badge badge-${outcome}${muted ? " is-muted" : ""}`}>{OUTCOME_LABEL[outcome]}</span>;
}

export function DecisionBadge({ decision }: { decision: Decision }) {
  return <span className={`badge badge-${decision}`}>{DECISION_LABEL[decision]}</span>;
}
