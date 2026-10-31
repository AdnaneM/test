import type {
  GridResponse,
  Health,
  MarkBody,
  Recommendation,
  RecommendationQuery,
  RecommendationsResponse,
  RunsResponse,
  Stats,
} from "./types";

/** Interface commune au client HTTP et au client démo. */
export interface ApiClient {
  health(): Promise<Health>;
  grid(date: string): Promise<GridResponse>;
  recommendations(query: RecommendationQuery): Promise<RecommendationsResponse>;
  mark(id: number, body: MarkBody): Promise<Recommendation>;
  stats(): Promise<Stats>;
  runs(limit?: number): Promise<RunsResponse>;
}

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Message d'erreur lisible pour l'utilisateur. */
export function humanError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return "Impossible de joindre l'API. Vérifiez l'URL dans les réglages.";
    if (e.status === 401 || e.status === 403) return "Clé API manquante ou invalide (voir Réglages).";
    if (e.status === 404) return "Ressource introuvable (404).";
    if (e.status >= 500) return `Erreur serveur (${e.status}) : ${e.message}`;
    return e.message;
  }
  if (e instanceof Error) return e.message;
  return "Erreur inconnue";
}

export interface HttpClientOptions {
  baseUrl: string;
  apiKey: string;
}

type Query = Record<string, string | number | undefined>;

interface RequestOptions {
  method?: "GET" | "POST";
  query?: Query;
  body?: unknown;
}

export function createHttpClient(opts: HttpClientOptions): ApiClient {
  const base = opts.baseUrl.trim().replace(/\/+$/, "");

  function buildUrl(path: string, query?: Query): string {
    const url = new URL(base + path, window.location.origin);
    if (query) {
      for (const [k, v] of Object.entries(query)) {
        if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
      }
    }
    return url.toString();
  }

  async function request<T>(path: string, { method = "GET", query, body }: RequestOptions = {}): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (method !== "GET" && opts.apiKey) headers["X-API-Key"] = opts.apiKey;

    let res: Response;
    try {
      res = await fetch(buildUrl(path, query), {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(0, "Réseau indisponible");
    }

    if (!res.ok) {
      let detail = res.statusText || `Erreur HTTP ${res.status}`;
      try {
        const payload = (await res.json()) as { detail?: unknown };
        if (typeof payload.detail === "string") detail = payload.detail;
        else if (payload.detail !== undefined) detail = JSON.stringify(payload.detail);
      } catch {
        /* corps non JSON */
      }
      throw new ApiError(res.status, detail);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  return {
    health: () => request<Health>("/api/health"),
    grid: (date) => request<GridResponse>("/api/grid", { query: { date } }),
    recommendations: (q) =>
      request<RecommendationsResponse>("/api/recommendations", {
        query: { from: q.from, to: q.to, decision: q.decision, outcome: q.outcome, limit: q.limit ?? 500 },
      }),
    mark: (id, body) => request<Recommendation>(`/api/recommendations/${id}/mark`, { method: "POST", body }),
    stats: () => request<Stats>("/api/stats"),
    runs: (limit = 20) => request<RunsResponse>("/api/runs", { query: { limit } }),
  };
}
