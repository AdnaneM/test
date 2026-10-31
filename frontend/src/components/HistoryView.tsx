import { useMemo, useState } from "react";
import { humanError, type ApiClient } from "../api";
import { fmtDDMM, fmtEur, fmtEurSigned, fmtInt, fmtMaybe, fmtOdds, fmtPct, fmtPctSigned, fmtTime, shiftYmd, signClass, todayParis } from "../format";
import { useAsync } from "../hooks";
import type { Recommendation, RecommendationQuery } from "../types";
import { DECISION_LABEL, OutcomeBadge } from "./Badges";
import { EmptyState, ErrorBanner, LoadingBar, Skeleton } from "./Feedback";

interface Props {
  client: ApiClient;
  demo: boolean;
  onEnableDemo: () => void;
}

type Period = "7" | "30" | "season" | "all";
type DecisionFilter = "all" | "played" | "skipped";
type OutcomeFilter = "all" | "won" | "lost";

interface Option<T extends string> {
  id: T;
  label: string;
}

const PERIODS: Option<Period>[] = [
  { id: "7", label: "7 j" },
  { id: "30", label: "30 j" },
  { id: "season", label: "Saison" },
  { id: "all", label: "Tout" },
];
const DECISIONS: Option<DecisionFilter>[] = [
  { id: "all", label: "Tous" },
  { id: "played", label: "Joués" },
  { id: "skipped", label: "Passés" },
];
const OUTCOMES: Option<OutcomeFilter>[] = [
  { id: "all", label: "Tous" },
  { id: "won", label: "Gagnés" },
  { id: "lost", label: "Perdus" },
];

/** Début de saison : 1er juillet de l'année sportive en cours. */
function seasonStart(today: string): string {
  const y = Number(today.slice(0, 4));
  const m = Number(today.slice(5, 7));
  return `${m >= 7 ? y : y - 1}-07-01`;
}

function fromFor(period: Period, today: string): string | undefined {
  switch (period) {
    case "7":
      return shiftYmd(today, -7);
    case "30":
      return shiftYmd(today, -30);
    case "season":
      return seasonStart(today);
    default:
      return undefined;
  }
}

function Chips<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: Option<T>[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="chips-row">
      <span className="chips-label">{label}</span>
      <div className="chips" role="group" aria-label={label}>
        {options.map((o) => (
          <button key={o.id} type="button" className="chip" aria-pressed={value === o.id} onClick={() => onChange(o.id)}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

interface Totals {
  n: number;
  nPlayed: number;
  staked: number;
  pnl: number;
  roi: number | null;
  hitRate: number | null;
  won: number;
  lost: number;
}

/** Totaux sur l'ensemble filtré : seuls les paris joués et réglés comptent. */
function computeTotals(items: Recommendation[]): Totals {
  let staked = 0;
  let pnl = 0;
  let won = 0;
  let lost = 0;
  let nPlayed = 0;
  for (const r of items) {
    if (r.decision !== "played") continue;
    nPlayed++;
    if (r.outcome === "open") continue;
    staked += r.stake_taken ?? r.stake;
    pnl += r.pnl ?? 0;
    if (r.outcome === "won") won++;
    else if (r.outcome === "lost") lost++;
  }
  return {
    n: items.length,
    nPlayed,
    staked,
    pnl,
    roi: staked > 0 ? pnl / staked : null,
    hitRate: won + lost > 0 ? won / (won + lost) : null,
    won,
    lost,
  };
}

export function HistoryView({ client, demo, onEnableDemo }: Props) {
  const today = todayParis();
  const [period, setPeriod] = useState<Period>("30");
  const [decision, setDecision] = useState<DecisionFilter>("all");
  const [outcome, setOutcome] = useState<OutcomeFilter>("all");

  const query = useMemo<RecommendationQuery>(
    () => ({
      from: fromFor(period, today),
      decision: decision === "all" ? undefined : decision,
      outcome: outcome === "all" ? undefined : outcome,
      limit: 500,
    }),
    [period, decision, outcome, today],
  );

  const res = useAsync(() => client.recommendations(query), [client, query]);
  const items = useMemo(
    () => (res.data?.items ?? []).slice().sort((a, b) => b.kickoff.localeCompare(a.kickoff)),
    [res.data],
  );
  const totals = useMemo(() => computeTotals(items), [items]);

  return (
    <section className="view" aria-labelledby="history-title">
      <h2 id="history-title" className="view-title">
        Historique
      </h2>

      <div className="filters card">
        <Chips label="Période" options={PERIODS} value={period} onChange={setPeriod} />
        <Chips label="Décision" options={DECISIONS} value={decision} onChange={setDecision} />
        <Chips label="Résultat" options={OUTCOMES} value={outcome} onChange={setOutcome} />
      </div>

      <LoadingBar active={res.loading} />

      {res.error ? (
        <ErrorBanner message={humanError(res.error)} onRetry={res.reload} onDemo={demo ? undefined : onEnableDemo} />
      ) : !res.data ? (
        <Skeleton rows={6} height={64} />
      ) : items.length === 0 ? (
        <EmptyState title="Aucune recommandation sur cette période" hint="Élargissez la période ou retirez un filtre." />
      ) : (
        <>
          <ul className={`hist card${res.loading ? " is-stale" : ""}`}>
            {items.map((r) => {
              const played = r.decision === "played";
              return (
                <li key={r.id} className={`hist-row${played ? "" : " is-skipped"}`}>
                  <div className="hist-date num">
                    <span>{fmtDDMM(r.kickoff)}</span>
                    <small>{fmtTime(r.kickoff)}</small>
                  </div>
                  <div className="hist-body">
                    <div className="hist-l1">
                      <span className="hist-match">
                        {r.home} – {r.away}
                      </span>
                      {r.score && <span className="hist-score num">{r.score}</span>}
                    </div>
                    <div className="hist-l2">
                      <span className="hist-league">{r.league_name}</span>
                      <span className="hist-pick">
                        {r.pick_label} <span className="num">@ {fmtOdds(r.odds_taken ?? r.odds)}</span>
                      </span>
                      <span className="num">{fmtEur(r.stake_taken ?? r.stake)}</span>
                      {!played && <span className="hist-dec">{DECISION_LABEL[r.decision]}</span>}
                    </div>
                  </div>
                  <div className="hist-right">
                    <OutcomeBadge outcome={r.outcome} muted={!played} />
                    <span className={`hist-pnl num ${signClass(r.pnl)}`}>{fmtMaybe(r.pnl, fmtEurSigned)}</span>
                    <span className={`hist-clv num ${signClass(r.clv)}`}>{r.clv === null ? "" : `CLV ${fmtPctSigned(r.clv)}`}</span>
                  </div>
                </li>
              );
            })}
          </ul>

          <div className="totals card">
            <div className="totals-head">
              <strong>{fmtInt(totals.n)} paris</strong>
              <span className="muted"> · {fmtInt(totals.nPlayed)} joués</span>
            </div>
            <dl className="metrics">
              <div>
                <dt>Misé</dt>
                <dd className="num">{fmtEur(totals.staked)}</dd>
              </div>
              <div>
                <dt>P&amp;L</dt>
                <dd className={`num ${signClass(totals.pnl)}`}>{fmtEurSigned(totals.pnl)}</dd>
              </div>
              <div>
                <dt>ROI</dt>
                <dd className={`num ${signClass(totals.roi)}`}>{fmtMaybe(totals.roi, fmtPctSigned)}</dd>
              </div>
              <div>
                <dt>Réussite</dt>
                <dd className="num">
                  {fmtMaybe(totals.hitRate, fmtPct)}
                  {totals.hitRate !== null && (
                    <small>
                      {" "}
                      {totals.won}/{totals.won + totals.lost}
                    </small>
                  )}
                </dd>
              </div>
            </dl>
          </div>
        </>
      )}
    </section>
  );
}
