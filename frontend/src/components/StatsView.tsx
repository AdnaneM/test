import type { ReactNode } from "react";
import { humanError, type ApiClient } from "../api";
import { fmtEur, fmtEurSigned, fmtInt, fmtMaybe, fmtOdds, fmtPct, fmtPctSigned, signClass } from "../format";
import { useAsync } from "../hooks";
import { BankrollChart, CalibrationChart, LeagueBars, RiskTable } from "./charts";
import { ErrorBanner, Skeleton } from "./Feedback";

interface Props {
  client: ApiClient;
  demo: boolean;
  onEnableDemo: () => void;
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="kpi card">
      <span className="kpi-label">{label}</span>
      <strong className={`kpi-value num ${tone ?? ""}`}>{value}</strong>
      {sub && <span className="kpi-sub num">{sub}</span>}
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="card section">
      <header className="section-head">
        <h3>{title}</h3>
        {hint && <p className="hint">{hint}</p>}
      </header>
      {children}
    </section>
  );
}

export function StatsView({ client, demo, onEnableDemo }: Props) {
  const st = useAsync(() => client.stats(), [client]);

  if (st.error) {
    return (
      <section className="view">
        <h2 className="view-title">Stats</h2>
        <ErrorBanner message={humanError(st.error)} onRetry={st.reload} onDemo={demo ? undefined : onEnableDemo} />
      </section>
    );
  }
  const s = st.data;
  if (!s) {
    return (
      <section className="view">
        <h2 className="view-title">Stats</h2>
        <Skeleton rows={4} height={120} />
      </section>
    );
  }

  const delta = s.bankroll_current - s.bankroll_start;

  return (
    <section className="view stack" aria-labelledby="stats-title">
      <h2 id="stats-title" className="view-title">
        Stats
      </h2>

      <div className="kpis">
        <Kpi label="Bankroll actuelle" value={fmtEur(s.bankroll_current)} tone={signClass(delta)} sub={`${fmtEurSigned(delta)} depuis ${fmtEur(s.bankroll_start)}`} />
        <Kpi label="P&L" value={fmtEurSigned(s.pnl)} tone={signClass(s.pnl)} sub={`${fmtEur(s.staked)} misés`} />
        <Kpi label="ROI" value={fmtPctSigned(s.roi)} tone={signClass(s.roi)} sub={`cote moyenne ${fmtOdds(s.avg_odds)}`} />
        <Kpi label="Taux de réussite" value={fmtPct(s.hit_rate)} sub={`${fmtInt(s.n_won)} gagnés`} />
        <Kpi label="CLV moyen" value={fmtMaybe(s.clv_mean, fmtPctSigned)} tone={signClass(s.clv_mean)} sub="vs cote de clôture" />
        <Kpi label="Paris joués" value={fmtInt(s.n_played)} sub={`sur ${fmtInt(s.n_recommended)} recommandés`} />
      </div>

      <Section title="Bankroll">
        <BankrollChart points={s.bankroll_curve} start={s.bankroll_start} />
      </Section>

      <Section title="Par ligue" hint="P&L des paris joués et réglés, par championnat.">
        {s.by_league.length ? <LeagueBars rows={s.by_league} /> : <p className="muted">Aucun pari réglé pour l'instant.</p>}
      </Section>

      <Section title="Calibration" hint="Probabilité prédite par le modèle contre fréquence observée. Sur la diagonale, le modèle est parfaitement calibré ; au-dessus, il est trop prudent.">
        <CalibrationChart bins={s.calibration} />
      </Section>

      <Section title="Par niveau de risque">
        <RiskTable rows={s.by_risk} />
      </Section>
    </section>
  );
}
