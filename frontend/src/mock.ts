/**
 * Mode démo : jeu de données fictif mais réaliste (championnats, équipes et
 * bookmakers français), généré de façon déterministe, avec état en mémoire
 * pour que « Joué / Passé / Annuler » fonctionnent sans backend.
 */
import { ApiError, type ApiClient } from "./api";
import { dateKey, nowParisIso, shiftYmd, todayParis } from "./format";
import type {
  BankrollPoint,
  CalibrationBin,
  Decision,
  GridResponse,
  LeagueStats,
  MarkBody,
  Outcome,
  PipelineRun,
  Recommendation,
  RecommendationQuery,
  RiskStats,
  Selection,
  Stats,
} from "./types";

// ------------------------------------------------------------- référentiels

const LEAGUES: Record<string, { name: string; teams: string[] }> = {
  F1: {
    name: "Ligue 1",
    teams: ["Paris SG", "Marseille", "Lyon", "Monaco", "Lille", "Lens", "Nice", "Rennes", "Strasbourg", "Toulouse", "Nantes", "Brest"],
  },
  E0: {
    name: "Premier League",
    teams: ["Arsenal", "Liverpool", "Manchester City", "Chelsea", "Tottenham", "Newcastle", "Aston Villa", "Brighton", "Everton", "West Ham"],
  },
  SP1: {
    name: "La Liga",
    teams: ["Real Madrid", "FC Barcelone", "Atlético Madrid", "Athletic Bilbao", "Villarreal", "Betis Séville", "FC Séville", "Real Sociedad", "Valence", "Girona"],
  },
  D1: {
    name: "Bundesliga",
    teams: ["Bayern Munich", "Dortmund", "Leverkusen", "RB Leipzig", "Stuttgart", "Francfort", "Fribourg", "Wolfsburg", "Mönchengladbach", "Mayence"],
  },
  I1: {
    name: "Serie A",
    teams: ["Inter Milan", "AC Milan", "Juventus", "Naples", "AS Rome", "Lazio", "Atalanta", "Fiorentina", "Bologne", "Torino"],
  },
};

const BOOKMAKERS = [
  { key: "winamax_fr", label: "Winamax", url: "https://www.winamax.fr/paris-sportifs/sports/1" },
  { key: "unibet_fr", label: "Unibet", url: "https://www.unibet.fr/sport/football" },
  { key: "betclic", label: "Betclic", url: "https://www.betclic.fr/football-s1" },
];

const SELECTION_LABEL: Record<Selection, string> = {
  H: "Victoire domicile",
  D: "Match nul",
  A: "Victoire extérieur",
};

const KICKOFF_TIMES = ["13:00:00", "15:00:00", "17:05:00", "18:30:00", "20:45:00", "21:00:00"];
const SEASON_START = "2026-08-15";
const BANKROLL_START = 100;

// ------------------------------------------------------------------ utils

type Rng = () => number;

function mulberry32(seed: number): Rng {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashStr(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

const r2 = (x: number): number => Math.round(x * 100) / 100;
const r3 = (x: number): number => Math.round(x * 1000) / 1000;
const sum = (xs: number[]): number => xs.reduce((a, b) => a + b, 0);
const avg = (xs: number[]): number => (xs.length ? sum(xs) / xs.length : 0);
const pick = <T>(rnd: Rng, xs: readonly T[]): T => xs[Math.floor(rnd() * xs.length)];
const slug = (s: string): string =>
  s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

const delay = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

// -------------------------------------------------------------- génération

function riskOf(odds: number, pModel: number): number {
  let r = odds < 1.8 ? 1 : odds < 2.2 ? 2 : odds < 2.8 ? 3 : odds < 3.6 ? 4 : 5;
  if (pModel < 0.3) r += 1;
  return Math.min(5, r);
}

function otherResult(sel: Selection, rnd: Rng): Selection {
  const others = (["H", "D", "A"] as Selection[]).filter((s) => s !== sel);
  return pick(rnd, others);
}

function scoreFor(result: Selection, rnd: Rng): string {
  const base = Math.floor(rnd() * 3);
  if (result === "D") return `${base}-${base}`;
  const winner = base + 1 + Math.floor(rnd() * 2);
  const loser = Math.floor(rnd() * winner);
  return result === "H" ? `${winner}-${loser}` : `${loser}-${winner}`;
}

function makeRec(id: number, date: string, rnd: Rng, today: string, usedTeams: Set<string>): Recommendation | null {
  const code = pick(rnd, Object.keys(LEAGUES));
  const lg = LEAGUES[code];
  let home = pick(rnd, lg.teams);
  let away = pick(rnd, lg.teams);
  for (let guard = 0; (home === away || usedTeams.has(home) || usedTeams.has(away)) && guard < 20; guard++) {
    home = pick(rnd, lg.teams);
    away = pick(rnd, lg.teams);
  }
  if (home === away) return null;
  usedTeams.add(home);
  usedTeams.add(away);

  const u = rnd();
  const selection: Selection = u < 0.5 ? "H" : u < 0.8 ? "A" : "D";
  const pSharp = selection === "H" ? 0.36 + rnd() * 0.24 : selection === "A" ? 0.25 + rnd() * 0.2 : 0.24 + rnd() * 0.08;
  const pModel = Math.min(0.85, pSharp + 0.005 + rnd() * 0.03);
  const fair = r2(1 / pSharp);
  const odds = r2(fair * (1.0 + rnd() * 0.05));
  const edge = r3(pModel * odds - 1);
  const edgeVsSharp = r3(odds / fair - 1);
  const kelly = r3(Math.max(0, (pModel * odds - 1) / (odds - 1)));
  const stake = Math.min(5, Math.max(1, Math.round(BANKROLL_START * kelly * 0.25 * 2) / 2));
  const bm = pick(rnd, BOOKMAKERS);
  const kickoff = `${date}T${pick(rnd, KICKOFF_TIMES)}`;

  let decision: Decision = "pending";
  let outcome: Outcome = "open";
  let result: Selection | null = null;
  let score: string | null = null;
  let pnl: number | null = null;
  let closing: number | null = null;
  let clv: number | null = null;
  let oddsTaken: number | null = null;
  let stakeTaken: number | null = null;

  if (date < today) {
    decision = rnd() < 0.68 ? "played" : "skipped";
    const pTrue = pSharp * 0.8 + pModel * 0.2;
    if (rnd() < 0.02) {
      outcome = "void";
    } else {
      const won = rnd() < pTrue;
      result = won ? selection : otherResult(selection, rnd);
      score = scoreFor(result, rnd);
      outcome = won ? "won" : "lost";
    }
    closing = r2(fair * (0.97 + rnd() * 0.07));
    clv = r3(odds / closing - 1);
    if (decision === "played") {
      oddsTaken = odds;
      stakeTaken = stake;
      pnl = outcome === "void" ? 0 : outcome === "won" ? r2(stake * (odds - 1)) : -stake;
    }
  }

  return {
    id,
    created_at: `${date}T09:00:12`,
    match_id: `${code}:${date}:${slug(home)}:${slug(away)}`,
    league: code,
    league_name: lg.name,
    home,
    away,
    kickoff,
    market: "1X2",
    selection,
    selection_label: SELECTION_LABEL[selection],
    pick_label: selection === "H" ? home : selection === "A" ? away : "Match nul",
    p_model: r3(pModel),
    p_sharp: r3(pSharp),
    odds,
    bookmaker: bm.key,
    bookmaker_label: bm.label,
    bookmaker_url: bm.url,
    fair_odds_sharp: fair,
    edge,
    edge_vs_sharp: edgeVsSharp,
    kelly,
    stake,
    risk: riskOf(odds, pModel),
    components: {
      gbm: r3(Math.min(0.95, pModel + (rnd() - 0.5) * 0.04)),
      dc: r3(Math.min(0.95, pModel + (rnd() - 0.5) * 0.04)),
      market: r3(pSharp),
    },
    decision,
    outcome,
    odds_taken: oddsTaken,
    stake_taken: stakeTaken,
    result,
    score,
    pnl,
    closing_odds: closing,
    clv,
  };
}

function buildRecommendations(today: string): Recommendation[] {
  const recs: Recommendation[] = [];
  const end = shiftYmd(today, 1);
  let id = 1;
  for (let d = SEASON_START; d <= end; d = shiftYmd(d, 1)) {
    const rnd = mulberry32(hashStr(`edgebet:${d}`));
    const dow = new Date(`${d}T12:00:00`).getDay();
    const weekend = dow === 0 || dow === 5 || dow === 6;
    let n = rnd() < (weekend ? 0.15 : 0.55) ? 0 : 1 + Math.floor(rnd() * (weekend ? 3 : 2));
    if (d === today) n = 4;
    if (d === end) n = Math.max(n, 2);
    const used = new Set<string>();
    for (let i = 0; i < n; i++) {
      const rec = makeRec(id, d, rnd, today, used);
      if (rec) {
        recs.push(rec);
        id++;
      }
    }
  }
  return recs;
}

// ---------------------------------------------------------------- agrégats

function settledPnl(rec: Recommendation): number | null {
  if (rec.decision !== "played") return null;
  const stake = rec.stake_taken ?? rec.stake;
  const odds = rec.odds_taken ?? rec.odds;
  switch (rec.outcome) {
    case "won":
      return r2(stake * (odds - 1));
    case "lost":
      return -stake;
    case "void":
      return 0;
    default:
      return null;
  }
}

function groupStats<K extends string | number>(
  recs: Recommendation[],
  key: (r: Recommendation) => K,
): Map<K, { n: number; staked: number; pnl: number }> {
  const m = new Map<K, { n: number; staked: number; pnl: number }>();
  for (const r of recs) {
    const k = key(r);
    const g = m.get(k) ?? { n: 0, staked: 0, pnl: 0 };
    g.n += 1;
    g.staked += r.stake_taken ?? r.stake;
    g.pnl += r.pnl ?? 0;
    m.set(k, g);
  }
  return m;
}

function computeStats(recs: Recommendation[], today: string): Stats {
  const played = recs.filter((r) => r.decision === "played");
  const settledPlayed = played.filter((r) => r.outcome !== "open");
  const decided = settledPlayed.filter((r) => r.outcome !== "void");
  const nWon = decided.filter((r) => r.outcome === "won").length;
  const staked = r2(sum(settledPlayed.map((r) => r.stake_taken ?? r.stake)));
  const pnl = r2(sum(settledPlayed.map((r) => r.pnl ?? 0)));
  const clvs = played.map((r) => r.clv).filter((x): x is number => x !== null);

  const byLeague: LeagueStats[] = [...groupStats(settledPlayed, (r) => r.league).entries()]
    .map(([league, g]) => ({
      league,
      league_name: LEAGUES[league]?.name ?? league,
      n: g.n,
      staked: r2(g.staked),
      pnl: r2(g.pnl),
      roi: g.staked > 0 ? r3(g.pnl / g.staked) : 0,
    }))
    .sort((a, b) => b.pnl - a.pnl);

  const riskGroups = groupStats(settledPlayed, (r) => r.risk);
  const byRisk: RiskStats[] = [1, 2, 3, 4, 5].map((risk) => {
    const g = riskGroups.get(risk) ?? { n: 0, staked: 0, pnl: 0 };
    return { risk, n: g.n, staked: r2(g.staked), pnl: r2(g.pnl), roi: g.staked > 0 ? r3(g.pnl / g.staked) : 0 };
  });

  const curve: BankrollPoint[] = [{ date: SEASON_START, balance: BANKROLL_START }];
  let balance = BANKROLL_START;
  const perDay = new Map<string, number>();
  for (const r of [...settledPlayed].sort((a, b) => a.kickoff.localeCompare(b.kickoff))) {
    const d = dateKey(r.kickoff);
    perDay.set(d, (perDay.get(d) ?? 0) + (r.pnl ?? 0));
  }
  for (const [date, delta] of perDay) {
    balance = r2(balance + delta);
    curve.push({ date, balance });
  }
  if (curve[curve.length - 1].date !== today) curve.push({ date: today, balance });

  const settledAll = recs.filter((r) => r.outcome === "won" || r.outcome === "lost");
  const calibration: CalibrationBin[] = [];
  for (let lo = 0.2; lo < 0.75; lo += 0.1) {
    const hi = r2(lo + 0.1);
    const inBin = settledAll.filter((r) => r.p_model >= lo && r.p_model < hi);
    if (!inBin.length) continue;
    calibration.push({
      bin_low: r2(lo),
      bin_high: hi,
      n: inBin.length,
      p_mean: r3(avg(inBin.map((r) => r.p_model))),
      observed: r3(inBin.filter((r) => r.outcome === "won").length / inBin.length),
    });
  }

  return {
    bankroll_start: BANKROLL_START,
    bankroll_current: r2(BANKROLL_START + pnl),
    n_recommended: recs.filter((r) => dateKey(r.kickoff) <= today).length,
    n_played: played.length,
    n_won: nWon,
    hit_rate: decided.length ? r3(nWon / decided.length) : 0,
    staked,
    pnl,
    roi: staked > 0 ? r3(pnl / staked) : 0,
    clv_mean: clvs.length ? r3(avg(clvs)) : null,
    avg_odds: played.length ? r2(avg(played.map((r) => r.odds_taken ?? r.odds))) : 0,
    by_league: byLeague,
    by_risk: byRisk,
    bankroll_curve: curve,
    calibration,
  };
}

// ------------------------------------------------------------------ client

interface Db {
  today: string;
  recs: Recommendation[];
}

let db: Db | null = null;

function getDb(): Db {
  if (!db) {
    const today = todayParis();
    db = { today, recs: buildRecommendations(today) };
  }
  return db;
}

export function createMockClient(): ApiClient {
  const latency = () => delay(180 + Math.random() * 220);

  return {
    async health() {
      await latency();
      return { status: "ok", version: "0.1.0-demo", time: nowParisIso() };
    },

    async grid(date) {
      await latency();
      const { recs } = getDb();
      const items = recs.filter((r) => dateKey(r.kickoff) === date).sort((a, b) => a.kickoff.localeCompare(b.kickoff));
      const stats = computeStats(recs, getDb().today);
      return {
        date,
        generated_at: items.length ? `${date}T09:00:12` : null,
        bankroll: stats.bankroll_current,
        currency: "EUR",
        summary: {
          n_bets: items.length,
          total_stake: r2(sum(items.map((r) => r.stake))),
          avg_edge: items.length ? r3(avg(items.map((r) => r.edge))) : 0,
        },
        items: items.map((r) => ({ ...r })),
      } satisfies GridResponse;
    },

    async recommendations(q: RecommendationQuery) {
      await latency();
      const { recs } = getDb();
      let items = recs.filter((r) => {
        const d = dateKey(r.kickoff);
        if (q.from && d < q.from) return false;
        if (q.to && d > q.to) return false;
        if (q.decision && r.decision !== q.decision) return false;
        if (q.outcome && r.outcome !== q.outcome) return false;
        return true;
      });
      items = items.sort((a, b) => b.kickoff.localeCompare(a.kickoff)).slice(0, q.limit ?? 500);
      return { items: items.map((r) => ({ ...r })), count: items.length };
    },

    async mark(id, body: MarkBody) {
      await latency();
      const rec = getDb().recs.find((r) => r.id === id);
      if (!rec) throw new ApiError(404, "Recommandation introuvable");
      rec.decision = body.decision;
      if (body.decision === "played") {
        rec.odds_taken = body.odds ?? rec.odds;
        rec.stake_taken = body.stake ?? rec.stake;
      } else {
        rec.odds_taken = null;
        rec.stake_taken = null;
      }
      rec.pnl = settledPnl(rec);
      return { ...rec };
    },

    async stats() {
      await latency();
      const { recs, today } = getDb();
      return computeStats(recs, today);
    },

    async runs(limit = 20) {
      await latency();
      const { recs, today } = getDb();
      const nToday = recs.filter((r) => dateKey(r.kickoff) === today).length;
      const items: PipelineRun[] = [
        {
          id: 142,
          kind: "daily",
          started_at: `${today}T09:00:00`,
          finished_at: `${today}T09:00:12`,
          status: "ok",
          n_matches: 14,
          n_recommendations: nToday,
          credits_remaining: 480,
          message: "",
        },
        {
          id: 141,
          kind: "settle",
          started_at: `${today}T07:00:00`,
          finished_at: `${today}T07:00:04`,
          status: "ok",
          n_matches: 6,
          n_recommendations: 0,
          credits_remaining: 482,
          message: "",
        },
      ];
      return { items: items.slice(0, limit) };
    },
  };
}
