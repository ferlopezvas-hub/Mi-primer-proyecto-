import { ChevronDown, ShieldCheck, ThumbsDown, ThumbsUp, TrendingUp } from "lucide-react";
import { useState } from "react";
import { fmtDateTime, outcomeLabel, pct } from "../lib/format";
import type { Match, Prediction } from "../lib/types";
import { ProbabilityBar } from "./ProbabilityBar";
import { Badge, StatusBadge } from "./ui";

const LABEL: Record<string, string> = {
  expected_goals: "Goles esperados", attack_index: "Índice de ataque (1 = media)", goals_conceded_index: "Índice de goles encajados (1 = media)",
  home_advantage_goals_factor: "Factor de ventaja local", form_last5: "Forma (últimos 5)", avg_goals_last10: "Media de goles (últimos 10)",
  home_win_rate_at_home: "Victorias del local en casa", away_win_rate_away: "Victorias del visitante fuera", head_to_head: "Enfrentamientos directos",
  most_likely_scores: "Marcadores más probables", matches_in_model: "Partidos en el modelo", elo: "Rating Elo", home_court_elo: "Ventaja de campo (Elo)",
  expected_points: "Puntos esperados", expected_margin: "Margen esperado", margin_std_dev: "Desviación del margen", avg_points_last10: "Media de puntos (últimos 10)",
  surface_elo: "Elo en la superficie", p_overall: "Probabilidad (Elo global)", p_surface: "Probabilidad (Elo superficie)",
};

// PostgreSQL (JSONB) no conserva el orden de las claves: se fija aquí (local antes que visitante).
const KEY_ORDER = ["home", "away", "for", "against", "total"];

function renderValue(v: any): string {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) {
    if (v.length && typeof v[0] === "object") return v.map((x) => x.score && x.p !== undefined ? `${x.score} (${pct(x.p)})` : `${x.date ?? ""} ${x.score ?? ""}`).join(" · ");
    return v.join("-") || "—";
  }
  if (typeof v === "object") return Object.entries(v).sort(([a], [b]) => KEY_ORDER.indexOf(a) - KEY_ORDER.indexOf(b)).map(([k, x]) => `${{ home: "local", away: "visitante", for: "a favor", against: "en contra", total: "total" }[k] ?? k}: ${renderValue(x)}`).join(" · ");
  if (typeof v === "number" && v > 0 && v < 1 && !Number.isInteger(v)) return v.toFixed(3);
  return String(v);
}

export function PredictionCard({ p, match }: { p: Prediction; match?: Match }) {
  const [open, setOpen] = useState(false);
  const e = p.explanation;
  const q = p.data_quality;
  const qualityKind = q.level === "alta" ? "good" : q.level === "media" ? "warn" : "bad";
  return (
    <article className="card p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">{p.market_label}</h3>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="brand">Confianza {e.confidence_label} · {Math.round(p.confidence * 100)}/100</Badge>
          <StatusBadge kind={qualityKind}>Datos: {q.level ?? "—"}</StatusBadge>
        </div>
      </div>
      <ProbabilityBar probabilities={p.probabilities} market={p.market} match={match} pick={p.predicted_outcome} />
      {e.summary && <p className="mt-3 text-sm">{e.summary}</p>}

      {p.result && (
        <div className="mt-3">
          {p.result.actual_outcome === "void" ? <Badge>Anulada (partido no disputado o retirada)</Badge> :
            <StatusBadge kind={p.result.is_correct ? "good" : "bad"}>
              {p.result.is_correct ? "Acierto" : "Fallo"} · resultado: {outcomeLabel(p.market, p.result.actual_outcome, match)} · Brier {p.result.brier?.toFixed(3)}
            </StatusBadge>}
        </div>
      )}

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-1.5 flex items-center gap-1.5 text-sm font-medium"><ThumbsUp className="h-4 w-4 text-good" />Factores a favor</p>
          <ul className="space-y-1 text-sm text-ink-2">{(e.factors_for ?? []).map((f, i) => <li key={i}>• {f.text}</li>)}
            {!e.factors_for?.length && <li>—</li>}</ul>
        </div>
        <div>
          <p className="mb-1.5 flex items-center gap-1.5 text-sm font-medium"><ThumbsDown className="h-4 w-4 text-bad" />Factores en contra</p>
          <ul className="space-y-1 text-sm text-ink-2">{(e.factors_against ?? []).map((f, i) => <li key={i}>• {f.text}</li>)}
            {!e.factors_against?.length && <li>—</li>}</ul>
        </div>
      </div>
      {!!e.trends?.length && (
        <div className="mt-4">
          <p className="mb-1.5 flex items-center gap-1.5 text-sm font-medium"><TrendingUp className="h-4 w-4" />Tendencias</p>
          <div className="flex flex-wrap gap-1.5">{e.trends.map((t, i) => <Badge key={i}>{t}</Badge>)}</div>
        </div>
      )}
      {!!q.warnings?.length && <ul className="mt-3 space-y-1 text-sm">{q.warnings.map((w, i) => <li key={i}><StatusBadge kind="warn">{w}</StatusBadge></li>)}</ul>}
      {e.limited && <p className="mt-3 rounded-xl bg-surface-2 p-3 text-sm text-ink-2">Tu plan muestra un resumen. Los planes Pro y Elite incluyen todas las estadísticas utilizadas.</p>}

      <button onClick={() => setOpen(!open)} className="mt-4 flex min-h-[44px] items-center gap-1 text-sm text-brand" aria-expanded={open}>
        <ChevronDown className={`h-4 w-4 transition ${open ? "rotate-180" : ""}`} />{open ? "Ocultar detalles" : "Estadísticas utilizadas y trazabilidad"}
      </button>
      {open && (
        <div className="mt-2 space-y-3 text-sm">
          {e.stats_used && (
            <dl className="grid gap-x-4 gap-y-1.5 sm:grid-cols-2">
              {Object.entries(e.stats_used).map(([k, v]) => (
                <div key={k} className="min-w-0"><dt className="text-xs text-muted">{LABEL[k] ?? k}</dt><dd className="break-words">{renderValue(v)}</dd></div>
              ))}
            </dl>
          )}
          <div className="rounded-xl bg-surface-2 p-3 text-xs text-ink-2">
            {p.is_backtest ? (
              <p className="font-medium text-ink">Backtest walk-forward: datos usados hasta {q.data_until ? fmtDateTime(q.data_until) : "—"}, antes del partido</p>
            ) : (
              <p className="flex items-center gap-1.5 font-medium text-ink"><ShieldCheck className="h-4 w-4 text-good" />Guardada antes del partido</p>
            )}
            <p>Creada: {fmtDateTime(p.created_at)} · Inicio: {fmtDateTime(p.kickoff_at)}</p>
            <p>Datos hasta: {q.data_until ? fmtDateTime(q.data_until) : "—"} · Último partido usado: hace {q.days_since_last_match ?? "—"} días</p>
            <p>Motor: {p.engine} {p.engine_version}</p>
            <p className="break-all">Huella SHA-256: {p.content_hash}</p>
          </div>
        </div>
      )}
    </article>
  );
}
