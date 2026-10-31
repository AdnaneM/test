/** Formatage français (nombres, monnaie, dates) et helpers de dates. */

const LOCALE = "fr-FR";

const eur = new Intl.NumberFormat(LOCALE, { style: "currency", currency: "EUR", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const eurSigned = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});
const pct1 = new Intl.NumberFormat(LOCALE, { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
const pct1Signed = new Intl.NumberFormat(LOCALE, {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: "exceptZero",
});
const pct0 = new Intl.NumberFormat(LOCALE, { style: "percent", maximumFractionDigits: 0 });
const num2 = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const int = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });

export const fmtEur = (v: number): string => eur.format(v);
export const fmtEurSigned = (v: number): string => eurSigned.format(v);
export const fmtPct = (v: number): string => pct1.format(v);
export const fmtPctSigned = (v: number): string => pct1Signed.format(v);
export const fmtPct0 = (v: number): string => pct0.format(v);
export const fmtOdds = (v: number): string => num2.format(v);
export const fmtInt = (v: number): string => int.format(v);

export function fmtMaybe<T>(v: T | null | undefined, f: (x: T) => string, fallback = "—"): string {
  return v === null || v === undefined ? fallback : f(v);
}

/** Classe CSS de signe : pos / neg / neu. */
export function signClass(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return "neu";
  return v > 0 ? "pos" : "neg";
}

// ---------------------------------------------------------------- dates

const HAS_TZ = /(?:Z|[+-]\d{2}:?\d{2})$/;
const NAIVE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/;

/**
 * Parse une date de l'API. Les datetimes sont naïfs (heure de Paris) : on les
 * reconstruit tels quels, sans conversion de fuseau, pour afficher l'heure
 * "mur" fournie par le backend.
 */
export function parseApiDate(iso: string): Date {
  if (HAS_TZ.test(iso)) return new Date(iso);
  const m = NAIVE.exec(iso);
  if (!m) return new Date(iso);
  return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] ?? 0), +(m[5] ?? 0), +(m[6] ?? 0));
}

/** "YYYY-MM-DD" d'un ISO naïf. */
export const dateKey = (iso: string): string => iso.slice(0, 10);

const dayMonth = new Intl.DateTimeFormat(LOCALE, { weekday: "short", day: "numeric", month: "short" });
const ddmm = new Intl.DateTimeFormat(LOCALE, { day: "2-digit", month: "2-digit" });
const hhmm = new Intl.DateTimeFormat(LOCALE, { hour: "2-digit", minute: "2-digit" });
const longDate = new Intl.DateTimeFormat(LOCALE, { weekday: "long", day: "numeric", month: "long" });
const dMonth = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short" });

/** "dim. 1 nov." */
export const fmtKickoffDate = (iso: string): string => dayMonth.format(parseApiDate(iso));
/** "20:45" */
export const fmtTime = (iso: string): string => hhmm.format(parseApiDate(iso));
/** "01/11" */
export const fmtDDMM = (iso: string): string => ddmm.format(parseApiDate(iso));
/** "samedi 31 octobre" */
export const fmtLongDate = (ymd: string): string => longDate.format(parseApiDate(ymd));
/** "31 oct." */
export const fmtDayMonth = (ymd: string): string => dMonth.format(parseApiDate(ymd));

const pad = (n: number): string => String(n).padStart(2, "0");

export function localYmd(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Date du jour (YYYY-MM-DD) en Europe/Paris, quel que soit le fuseau du téléphone. */
export function todayParis(): string {
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Europe/Paris",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const get = (t: string): string => parts.find((p) => p.type === t)?.value ?? "";
    const y = get("year");
    const m = get("month");
    const d = get("day");
    if (y && m && d) return `${y}-${m}-${d}`;
  } catch {
    /* Intl indisponible : repli local */
  }
  return localYmd(new Date());
}

/** Heure courante à Paris sous forme ISO naïf ("2026-10-31T09:00:00"). */
export function nowParisIso(): string {
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Europe/Paris",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date());
    const get = (t: string): string => parts.find((p) => p.type === t)?.value ?? "00";
    return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}:${get("second")}`;
  } catch {
    const n = new Date();
    return `${localYmd(n)}T${pad(n.getHours())}:${pad(n.getMinutes())}:${pad(n.getSeconds())}`;
  }
}

/** Décale une date YYYY-MM-DD de N jours. */
export function shiftYmd(ymd: string, days: number): string {
  const d = parseApiDate(ymd);
  d.setDate(d.getDate() + days);
  return localYmd(d);
}

/** Libellé relatif court : "Aujourd'hui", "Hier", "Demain" ou la date longue. */
export function relativeDayLabel(ymd: string, today: string): string {
  if (ymd === today) return "Aujourd'hui";
  if (ymd === shiftYmd(today, -1)) return "Hier";
  if (ymd === shiftYmd(today, 1)) return "Demain";
  return fmtLongDate(ymd);
}
