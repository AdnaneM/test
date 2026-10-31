export const RISK_LABELS = ["", "Sûr", "Modéré", "Équilibré", "Risqué", "Spéculatif"] as const;

export function riskLevel(risk: number): number {
  return Math.min(5, Math.max(1, Math.round(risk) || 1));
}

/** Indicateur de risque 1–5 : 5 pastilles, couleur du vert (1) au rouge (5). */
export function RiskDots({ risk, showLabel = false }: { risk: number; showLabel?: boolean }) {
  const level = riskLevel(risk);
  const color = `var(--risk-${level})`;
  return (
    <span className="risk" role="img" aria-label={`Risque ${level} sur 5 – ${RISK_LABELS[level]}`} title={`Risque ${level}/5`}>
      <span className="risk-dots" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((i) => (
          <i key={i} className={i <= level ? "on" : undefined} style={i <= level ? { background: color } : undefined} />
        ))}
      </span>
      {showLabel && (
        <span className="risk-label" style={{ color }}>
          {RISK_LABELS[level]}
        </span>
      )}
    </span>
  );
}
