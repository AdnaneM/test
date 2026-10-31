/** Types du contrat API EdgeBet (FastAPI, préfixe /api). */

export type Selection = "H" | "D" | "A";
export type Decision = "pending" | "played" | "skipped";
export type Outcome = "open" | "won" | "lost" | "void";

export interface Recommendation {
  id: number;
  created_at: string;
  match_id: string;
  league: string;
  league_name: string;
  home: string;
  away: string;
  /** ISO naïf, heure locale Europe/Paris (ex. "2026-11-01T20:45:00"). */
  kickoff: string;
  market: string;
  selection: Selection;
  selection_label: string;
  pick_label: string;
  p_model: number;
  p_sharp: number | null;
  odds: number;
  bookmaker: string;
  bookmaker_label: string;
  bookmaker_url: string | null;
  fair_odds_sharp: number | null;
  edge: number;
  edge_vs_sharp: number | null;
  kelly: number;
  stake: number;
  /** 1 (sûr) … 5 (spéculatif) */
  risk: number;
  components: Record<string, number>;
  decision: Decision;
  outcome: Outcome;
  odds_taken: number | null;
  stake_taken: number | null;
  result: Selection | null;
  score: string | null;
  pnl: number | null;
  closing_odds: number | null;
  clv: number | null;
}

export interface GridSummary {
  n_bets: number;
  total_stake: number;
  avg_edge: number;
}

export interface GridResponse {
  date: string;
  generated_at: string | null;
  bankroll: number;
  currency: string;
  summary: GridSummary;
  items: Recommendation[];
}

export interface RecommendationQuery {
  from?: string;
  to?: string;
  decision?: Decision;
  outcome?: Outcome;
  limit?: number;
}

export interface RecommendationsResponse {
  items: Recommendation[];
  count: number;
}

export interface MarkBody {
  decision: Decision;
  stake?: number;
  odds?: number;
}

export interface LeagueStats {
  league: string;
  league_name: string;
  n: number;
  staked: number;
  pnl: number;
  roi: number;
}

export interface RiskStats {
  risk: number;
  n: number;
  staked: number;
  pnl: number;
  roi: number;
}

export interface BankrollPoint {
  date: string;
  balance: number;
}

export interface CalibrationBin {
  bin_low: number;
  bin_high: number;
  n: number;
  p_mean: number;
  observed: number;
}

export interface Stats {
  bankroll_start: number;
  bankroll_current: number;
  n_recommended: number;
  n_played: number;
  n_won: number;
  hit_rate: number;
  staked: number;
  pnl: number;
  roi: number;
  clv_mean: number | null;
  avg_odds: number;
  by_league: LeagueStats[];
  by_risk: RiskStats[];
  bankroll_curve: BankrollPoint[];
  calibration: CalibrationBin[];
}

export interface PipelineRun {
  id: number;
  kind: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  n_matches: number;
  n_recommendations: number;
  credits_remaining: number | null;
  message: string;
}

export interface RunsResponse {
  items: PipelineRun[];
}

export interface Health {
  status: string;
  version: string;
  time: string;
}
