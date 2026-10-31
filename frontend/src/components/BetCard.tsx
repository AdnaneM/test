import type { Decision, Recommendation } from "../types";
import { fmtEur, fmtEurSigned, fmtKickoffDate, fmtMaybe, fmtOdds, fmtPct, fmtPctSigned, fmtTime, signClass } from "../format";
import { OutcomeBadge } from "./Badges";
import { IconExternal } from "./Icons";
import { RiskDots } from "./RiskDots";

interface Props {
  rec: Recommendation;
  busy: boolean;
  onMark: (rec: Recommendation, decision: Decision) => void;
}

export function BetCard({ rec, busy, onMark }: Props) {
  const decided = rec.decision !== "pending";
  const settled = rec.outcome !== "open";
  const stakeShown = rec.stake_taken ?? rec.stake;
  const oddsShown = rec.odds_taken ?? rec.odds;

  return (
    <article className={`card bet bet-${rec.decision}`} aria-busy={busy || undefined}>
      <header className="bet-head">
        <span className="bet-league">{rec.league_name}</span>
        <time className="bet-time num" dateTime={rec.kickoff}>
          {fmtKickoffDate(rec.kickoff)} · {fmtTime(rec.kickoff)}
        </time>
      </header>

      <h3 className="bet-match">
        {rec.home} <span className="vs">–</span> {rec.away}
      </h3>

      <div className="bet-pick">
        <div className="pick-main">
          <span className="pick-label">{rec.pick_label}</span>
          <span className="pick-sub">
            {rec.selection_label} · {rec.market}
          </span>
        </div>
        <div className="pick-odds num">
          <strong>@ {fmtOdds(oddsShown)}</strong>
          <span>{rec.bookmaker_label}</span>
        </div>
      </div>

      <dl className="metrics">
        <div>
          <dt>Mise</dt>
          <dd className="num">{fmtEur(stakeShown)}</dd>
        </div>
        <div>
          <dt>Edge</dt>
          <dd className={`num ${signClass(rec.edge)}`}>{fmtPctSigned(rec.edge)}</dd>
        </div>
        <div>
          <dt>Proba</dt>
          <dd className="num">{fmtPct(rec.p_model)}</dd>
        </div>
        <div>
          <dt>Cote juste</dt>
          <dd className="num">{fmtMaybe(rec.fair_odds_sharp, fmtOdds)}</dd>
        </div>
      </dl>

      <div className="bet-risk">
        <span className="label">Risque</span>
        <RiskDots risk={rec.risk} showLabel />
        {settled && (
          <span className="bet-result">
            {rec.score && <span className="score num">{rec.score}</span>}
            <OutcomeBadge outcome={rec.outcome} muted={rec.decision !== "played"} />
            {rec.pnl !== null && <span className={`num ${signClass(rec.pnl)}`}>{fmtEurSigned(rec.pnl)}</span>}
          </span>
        )}
      </div>

      <footer className="bet-actions">
        {decided ? (
          <div className={`bet-state state-${rec.decision}`}>
            <span className="state-label">{rec.decision === "played" ? "✅ Joué" : "⏭ Passé"}</span>
            {rec.decision === "played" && (
              <span className="state-detail num">
                {fmtEur(stakeShown)} @ {fmtOdds(oddsShown)}
              </span>
            )}
            <button type="button" className="btn btn-text" disabled={busy} onClick={() => onMark(rec, "pending")}>
              Annuler
            </button>
          </div>
        ) : (
          <>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => onMark(rec, "played")}>
              ✅ Joué
            </button>
            <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => onMark(rec, "skipped")}>
              ⏭ Passé
            </button>
          </>
        )}
        {rec.bookmaker_url && (
          <a className="btn btn-outline" href={rec.bookmaker_url} target="_blank" rel="noopener noreferrer">
            Ouvrir {rec.bookmaker_label}
            <IconExternal width={15} height={15} />
          </a>
        )}
      </footer>
    </article>
  );
}
