import { useMemo, useState } from "react";
import { humanError, type ApiClient } from "../api";
import { fmtDDMM, fmtEur, fmtInt, fmtLongDate, fmtPct, fmtTime, relativeDayLabel, shiftYmd, todayParis } from "../format";
import { useAsync } from "../hooks";
import { toast } from "../toast";
import type { Decision, MarkBody, PipelineRun, Recommendation } from "../types";
import { BetCard } from "./BetCard";
import { EmptyState, ErrorBanner, LoadingBar, Skeleton } from "./Feedback";
import { IconChevronLeft, IconChevronRight, IconRefresh } from "./Icons";

interface Props {
  client: ApiClient;
  demo: boolean;
  onEnableDemo: () => void;
}

function latestRun(items: PipelineRun[] | undefined): PipelineRun | null {
  if (!items || items.length === 0) return null;
  const at = (r: PipelineRun): string => r.finished_at ?? r.started_at;
  return [...items].sort((a, b) => at(b).localeCompare(at(a)))[0] ?? null;
}

function runMeta(run: PipelineRun | null, today: string): string | null {
  if (!run) return null;
  const at = run.finished_at ?? run.started_at;
  const when = at.slice(0, 10) === today ? fmtTime(at) : `${fmtDDMM(at)} ${fmtTime(at)}`;
  const parts = [`Mis à jour ${when}`];
  if (run.credits_remaining !== null) parts.push(`${fmtInt(run.credits_remaining)} crédits API`);
  if (run.status && run.status !== "ok") parts.push(`statut : ${run.status}`);
  return parts.join(" · ");
}

export function GridView({ client, demo, onEnableDemo }: Props) {
  const today = todayParis();
  const [date, setDate] = useState(today);
  const grid = useAsync(() => client.grid(date), [client, date]);
  const runs = useAsync(() => client.runs(5), [client]);
  const [busy, setBusy] = useState<ReadonlySet<number>>(() => new Set());
  const run = useMemo(() => latestRun(runs.data?.items), [runs.data]);

  const isToday = date === today;
  const data = grid.data;
  const dayLabel = relativeDayLabel(date, today);

  function setBusyId(id: number, on: boolean): void {
    setBusy((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  function patch(id: number, fn: (r: Recommendation) => Recommendation): void {
    grid.setData((d) => (d ? { ...d, items: d.items.map((it) => (it.id === id ? fn(it) : it)) } : d));
  }

  async function mark(rec: Recommendation, decision: Decision): Promise<void> {
    const body: MarkBody = decision === "played" ? { decision, stake: rec.stake, odds: rec.odds } : { decision };
    const optimistic: Recommendation = {
      ...rec,
      decision,
      odds_taken: decision === "played" ? rec.odds : null,
      stake_taken: decision === "played" ? rec.stake : null,
    };
    setBusyId(rec.id, true);
    patch(rec.id, () => optimistic);
    try {
      const saved = await client.mark(rec.id, body);
      patch(rec.id, () => saved);
    } catch (e) {
      patch(rec.id, () => rec);
      toast(humanError(e), "error");
    } finally {
      setBusyId(rec.id, false);
    }
  }

  function refresh(): void {
    grid.reload();
    runs.reload();
  }

  const meta = runMeta(run, today);

  return (
    <section className="view" aria-labelledby="grid-title">
      <div className="date-nav">
        <button type="button" className="icon-btn" aria-label="Jour précédent" onClick={() => setDate(shiftYmd(date, -1))}>
          <IconChevronLeft width={22} height={22} />
        </button>
        <div className="date-current">
          <h2 id="grid-title" className="date-title">
            {dayLabel}
          </h2>
          <span className="date-sub">{dayLabel === fmtLongDate(date) ? "Changer de date" : fmtLongDate(date)}</span>
          <input
            className="date-input"
            type="date"
            value={date}
            aria-label="Choisir une date"
            onChange={(e) => {
              if (e.target.value) setDate(e.target.value);
            }}
            onClick={(e) => {
              try {
                e.currentTarget.showPicker();
              } catch {
                /* navigateur sans showPicker : le sélecteur natif prend le relais */
              }
            }}
          />
        </div>
        <button type="button" className="icon-btn" aria-label="Jour suivant" onClick={() => setDate(shiftYmd(date, 1))}>
          <IconChevronRight width={22} height={22} />
        </button>
      </div>

      {!isToday && (
        <div className="center">
          <button type="button" className="btn btn-text" onClick={() => setDate(today)}>
            Revenir à aujourd'hui
          </button>
        </div>
      )}

      {data && (
        <div className="summary card">
          <div>
            <span className="k">Paris</span>
            <strong className="num">{fmtInt(data.summary.n_bets)}</strong>
          </div>
          <div>
            <span className="k">Mise totale</span>
            <strong className="num">{fmtEur(data.summary.total_stake)}</strong>
          </div>
          <div>
            <span className="k">Edge moyen</span>
            <strong className="num accent">{data.summary.n_bets ? fmtPct(data.summary.avg_edge) : "—"}</strong>
          </div>
          <div>
            <span className="k">Bankroll</span>
            <strong className="num">{fmtEur(data.bankroll)}</strong>
          </div>
        </div>
      )}

      <p className="meta">
        <span>{meta ?? (runs.loading ? "Chargement…" : "Dernière exécution inconnue")}</span>
        <button type="button" className="meta-refresh" aria-label="Actualiser" onClick={refresh} disabled={grid.loading}>
          <IconRefresh width={14} height={14} />
        </button>
      </p>

      <LoadingBar active={grid.loading} />

      {grid.error ? (
        <ErrorBanner message={humanError(grid.error)} onRetry={grid.reload} onDemo={demo ? undefined : onEnableDemo} />
      ) : !data ? (
        <Skeleton rows={3} height={236} />
      ) : data.items.length === 0 ? (
        <EmptyState
          title={isToday ? "Aucun pari recommandé aujourd'hui" : `Aucun pari recommandé le ${fmtLongDate(date)}`}
          hint="Le moteur ne publie une recommandation que lorsqu'il détecte un avantage suffisant sur le marché."
        />
      ) : (
        <div className={`stack${grid.loading ? " is-stale" : ""}`}>
          {data.items.map((rec) => (
            <BetCard key={rec.id} rec={rec} busy={busy.has(rec.id)} onMark={mark} />
          ))}
        </div>
      )}
    </section>
  );
}
