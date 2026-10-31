import { useState, type PointerEvent } from "react";
import { fmtDayMonth, fmtEur, fmtEurSigned, fmtInt, fmtPct, fmtPct0, fmtPctSigned, parseApiDate, signClass } from "../format";
import type { BankrollPoint, CalibrationBin, LeagueStats, RiskStats } from "../types";
import { RiskDots, RISK_LABELS, riskLevel } from "./RiskDots";

// ------------------------------------------------------------ bankroll

const W = 360;
const H = 170;
const PL = 8;
const PR = 8;
const PT = 14;
const PB = 24;

export function BankrollChart({ points, start }: { points: BankrollPoint[]; start: number }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length === 0) return <p className="muted">Pas encore de courbe : aucun pari réglé.</p>;

  const times = points.map((p) => parseApiDate(p.date).getTime());
  const t0 = times[0];
  const t1 = times[times.length - 1];
  const xs = times.map((t) => (t1 === t0 ? (PL + W - PR) / 2 : PL + ((t - t0) / (t1 - t0)) * (W - PL - PR)));
  const vals = points.map((p) => p.balance);
  const lo = Math.min(...vals, start);
  const hi = Math.max(...vals, start);
  const span = hi - lo || Math.max(1, start * 0.05);
  const pad = span * 0.12;
  const y = (v: number): number => PT + ((hi + pad - v) / (span + 2 * pad)) * (H - PT - PB);

  const line = points.map((p, i) => `${i ? "L" : "M"}${xs[i].toFixed(1)},${y(p.balance).toFixed(1)}`).join(" ");
  const area = `${line} L${xs[xs.length - 1].toFixed(1)},${H - PB} L${xs[0].toFixed(1)},${H - PB} Z`;
  const last = points[points.length - 1];
  const color = last.balance >= start ? "var(--pos)" : "var(--neg)";
  const idx = hover ?? points.length - 1;
  const cur = points[idx];

  function onMove(e: PointerEvent<SVGSVGElement>): void {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0;
    for (let i = 1; i < xs.length; i++) if (Math.abs(xs[i] - px) < Math.abs(xs[best] - px)) best = i;
    setHover(best);
  }

  return (
    <div className="chart">
      <div className="chart-readout">
        <span className="muted">{fmtDayMonth(cur.date)}</span>
        <strong className="num">{fmtEur(cur.balance)}</strong>
        <span className={`num ${signClass(cur.balance - start)}`}>{fmtEurSigned(cur.balance - start)}</span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="chart-svg"
        role="img"
        aria-label={`Évolution de la bankroll de ${fmtEur(start)} à ${fmtEur(last.balance)}`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id="bk-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor={color} stopOpacity="0.28" />
            <stop offset="1" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1={PL} x2={W - PR} y1={y(start)} y2={y(start)} className="chart-baseline" />
        <text x={W - PR} y={y(start) - 4} textAnchor="end" className="chart-tick">
          départ {fmtEur(start)}
        </text>
        <path d={area} fill="url(#bk-fill)" />
        <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {hover !== null && <line x1={xs[idx]} x2={xs[idx]} y1={PT} y2={H - PB} className="chart-cursor" />}
        <circle cx={xs[idx]} cy={y(cur.balance)} r="4" fill={color} stroke="var(--surface)" strokeWidth="2" />
        <text x={PL} y={H - 6} className="chart-tick">
          {fmtDayMonth(points[0].date)}
        </text>
        <text x={W - PR} y={H - 6} textAnchor="end" className="chart-tick">
          {fmtDayMonth(last.date)}
        </text>
      </svg>
    </div>
  );
}

// ----------------------------------------------------------- par ligue

export function LeagueBars({ rows }: { rows: LeagueStats[] }) {
  const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.pnl)));
  return (
    <ul className="bars">
      {rows.map((r) => {
        const w = (Math.abs(r.pnl) / maxAbs) * 50;
        const pos = r.pnl >= 0;
        return (
          <li key={r.league} className="bar-row">
            <div className="bar-head">
              <span className="bar-name">{r.league_name}</span>
              <span className={`bar-val num ${signClass(r.pnl)}`}>
                {fmtEurSigned(r.pnl)} <small>({fmtPctSigned(r.roi)})</small>
              </span>
            </div>
            <div className="bar-track" aria-hidden="true">
              <span className="bar-zero" />
              <span
                className={`bar-fill ${pos ? "pos" : "neg"}`}
                style={pos ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }}
              />
            </div>
            <div className="bar-meta muted num">
              {fmtInt(r.n)} {r.n > 1 ? "paris" : "pari"} · misé {fmtEur(r.staked)}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------- calibration

const S = 220;
const P = 28;

export function CalibrationChart({ bins }: { bins: CalibrationBin[] }) {
  if (bins.length === 0) return <p className="muted">Pas assez de paris réglés pour mesurer la calibration.</p>;
  const sx = (v: number): number => P + v * (S - 2 * P);
  const sy = (v: number): number => S - P - v * (S - 2 * P);
  const maxN = Math.max(1, ...bins.map((b) => b.n));
  return (
    <div className="calib">
      <svg viewBox={`0 0 ${S} ${S}`} className="chart-svg chart-square" role="img" aria-label="Calibration : probabilité prédite contre fréquence observée">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={sx(t)} x2={sx(t)} y1={sy(0)} y2={sy(1)} className="chart-grid" />
            <line x1={sx(0)} x2={sx(1)} y1={sy(t)} y2={sy(t)} className="chart-grid" />
          </g>
        ))}
        <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} className="chart-diag" />
        {bins.map((b) => {
          const r = 4 + 8 * Math.sqrt(b.n / maxN);
          return (
            <g key={b.bin_low}>
              <line x1={sx(b.p_mean)} x2={sx(b.p_mean)} y1={sy(b.p_mean)} y2={sy(b.observed)} className="chart-resid" />
              <circle cx={sx(b.p_mean)} cy={sy(b.observed)} r={r} className="chart-dot">
                <title>{`${fmtPct0(b.bin_low)} – ${fmtPct0(b.bin_high)} : prédit ${fmtPct(b.p_mean)}, observé ${fmtPct(b.observed)} (n = ${b.n})`}</title>
              </circle>
            </g>
          );
        })}
        {[0, 0.5, 1].map((t) => (
          <text key={`x${t}`} x={sx(t)} y={S - 8} textAnchor="middle" className="chart-tick">
            {fmtPct0(t)}
          </text>
        ))}
        {[0.5, 1].map((t) => (
          <text key={`y${t}`} x={P - 5} y={sy(t)} textAnchor="end" dominantBaseline="middle" className="chart-tick">
            {fmtPct0(t)}
          </text>
        ))}
        <text x={S / 2} y={S - 8 - 14} textAnchor="middle" className="chart-axis">
          prédit →
        </text>
        <text x={P + 6} y={P + 2} className="chart-axis">
          ↑ observé
        </text>
      </svg>
      <table className="table num calib-table">
        <thead>
          <tr>
            <th scope="col">Tranche</th>
            <th scope="col">n</th>
            <th scope="col">Prédit</th>
            <th scope="col">Observé</th>
            <th scope="col">Écart</th>
          </tr>
        </thead>
        <tbody>
          {bins.map((b) => (
            <tr key={b.bin_low}>
              <td>
                {fmtPct0(b.bin_low)} – {fmtPct0(b.bin_high)}
              </td>
              <td>{fmtInt(b.n)}</td>
              <td>{fmtPct(b.p_mean)}</td>
              <td>{fmtPct(b.observed)}</td>
              <td className={signClass(b.observed - b.p_mean)}>{fmtPctSigned(b.observed - b.p_mean)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// -------------------------------------------------------------- risque

export function RiskTable({ rows }: { rows: RiskStats[] }) {
  const sorted = [...rows].sort((a, b) => a.risk - b.risk);
  return (
    <table className="table num risk-table">
      <thead>
        <tr>
          <th scope="col">Risque</th>
          <th scope="col">Paris</th>
          <th scope="col">Misé</th>
          <th scope="col">P&amp;L</th>
          <th scope="col">ROI</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((r) => (
          <tr key={r.risk} className={r.n === 0 ? "is-muted" : undefined}>
            <td className="risk-cell">
              <RiskDots risk={r.risk} />
              <span className="risk-name">{RISK_LABELS[riskLevel(r.risk)]}</span>
            </td>
            <td>{fmtInt(r.n)}</td>
            <td>{fmtEur(r.staked)}</td>
            <td className={signClass(r.pnl)}>{r.n ? fmtEurSigned(r.pnl) : "—"}</td>
            <td className={signClass(r.roi)}>{r.n ? fmtPctSigned(r.roi) : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
