import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clock } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { FollowButton } from "../components/FollowButton";
import { MatchCard as MatchCardLite } from "../components/MatchCard";
import { PredictionCard } from "../components/PredictionCard";
import { Card, Empty, ErrorBox, LiveDot, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { SPORT_EMOJI, ago, fmtDateTime, statusText } from "../lib/format";
import type { Match, Prediction } from "../lib/types";

const EVENT_ICON: Record<string, string> = { goal: "⚽", goal_cancelled: "❌", yellow_card: "🟨", red_card: "🟥", substitution: "🔁", penalty_missed: "🚫",
  kickoff: "▶️", tipoff: "▶️", match_start: "▶️", halftime_start: "⏸️", halftime_end: "▶️", full_time: "🏁", period_end: "⏱️", lead_change: "🔄",
  big_run: "🔥", set_end: "🎾", game_score: "•" };
const EVENT_LABEL: Record<string, string> = { goal: "Gol", goal_cancelled: "Gol anulado", yellow_card: "Amarilla", red_card: "Roja", substitution: "Cambio",
  penalty_missed: "Penalti fallado", kickoff: "Inicio", tipoff: "Inicio", match_start: "Inicio", halftime_start: "Descanso", halftime_end: "Segunda parte",
  full_time: "Final", period_end: "Fin de periodo", lead_change: "Cambio de líder", big_run: "Parcial", set_end: "Fin de set", game_score: "Juego" };

export function MatchDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const detail = useQuery({ queryKey: ["match", id], queryFn: () => api<{ match: Match; events: any[]; prediction_markets: string[] }>(`/sports/matches/${id}`),
    refetchInterval: (q) => (q.state.data?.match.status === "live" ? 20_000 : false) });
  const preds = useQuery({ queryKey: ["predictions", id], queryFn: () => api<{ predictions: Prediction[]; note?: string; mode?: "live" | "backtest" }>(`/predictions/match/${id}`), retry: false });
  if (detail.isLoading) return <Spinner />;
  if (detail.error) return <ErrorBox error={detail.error} />;
  const { match: m, events } = detail.data!;
  return (
    <div className="space-y-5">
      <button onClick={() => navigate(-1)} className="inline-flex min-h-[44px] items-center gap-1 text-sm text-brand"><ArrowLeft className="h-4 w-4" />Volver</button>
      <Card>
        <p className="text-center text-sm text-ink-2">{SPORT_EMOJI[m.sport]} {m.competition?.name} {m.surface ? `· ${m.surface}` : ""}</p>
        <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-center">
          <Link to={`/teams/${m.home.id}`} className="min-w-0">
            {m.home.logo_url && <img src={m.home.logo_url} alt="" className="mx-auto mb-2 h-12 w-12 object-contain" />}
            <p className="truncate font-semibold sm:text-lg">{m.home.name}</p>
          </Link>
          <div>
            <p className="text-3xl font-bold tabular-nums sm:text-4xl">{m.home_score ?? "-"} : {m.away_score ?? "-"}</p>
            <p className={`mt-1 flex items-center justify-center gap-1.5 text-sm ${m.status === "live" ? "font-semibold text-live" : "text-ink-2"}`}>
              {m.status === "live" && <LiveDot />}{m.status === "scheduled" ? fmtDateTime(m.start_time) : statusText(m)}
            </p>
          </div>
          <Link to={`/teams/${m.away.id}`} className="min-w-0">
            {m.away.logo_url && <img src={m.away.logo_url} alt="" className="mx-auto mb-2 h-12 w-12 object-contain" />}
            <p className="truncate font-semibold sm:text-lg">{m.away.name}</p>
          </Link>
        </div>
        {m.sport === "tennis" && Array.isArray(m.periods.sets) && m.periods.sets.length > 0 && (
          <p className="mt-3 text-center text-sm tabular-nums text-ink-2">Sets: {m.periods.sets.map((s: any) => `${s.home}-${s.away}`).join("  ")}</p>
        )}
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          <FollowButton kind="match" id={m.id} />
          <span className="flex items-center gap-1 text-xs text-muted"><Clock className="h-3.5 w-3.5" />Fuente: {m.source} · actualizado {ago(m.last_synced_at)}</span>
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <h2 className="text-lg font-semibold">Análisis y predicción</h2>
          {preds.isLoading ? <Spinner /> : preds.error ? <ErrorBox error={preds.error} /> : !preds.data?.predictions.length ? (
            <Card><Empty title="Sin predicción para este partido" text={preds.data?.note} /></Card>
          ) : (
            <>
              {preds.data.mode === "backtest" && (
                <div className="rounded-xl border border-warn/60 bg-surface p-3 text-sm">
                  <b>Prueba histórica (backtest).</b> Esta predicción no se publicó antes del partido: se calculó después,
                  usando solo datos anteriores a la fecha del encuentro, para medir la precisión del modelo.
                </div>
              )}
              {preds.data.predictions.map((p) => <PredictionCard key={p.id} p={p} match={m} />)}
            </>
          )}
          <p className="text-xs text-muted">Las predicciones son estimaciones estadísticas basadas en datos históricos y pueden fallar. No constituyen asesoramiento ni garantía de resultado.</p>
        </div>
        <Card title="Eventos">
          {!events.length ? <p className="text-sm text-ink-2">Sin eventos registrados.</p> : (
            <ol className="space-y-2">
              {events.filter((e) => e.type !== "game_score").map((e) => (
                <li key={e.id} className="flex gap-2 text-sm">
                  <span className="w-6 text-center">{EVENT_ICON[e.type] ?? "•"}</span>
                  <div className="min-w-0">
                    <p className="font-medium">{EVENT_LABEL[e.type] ?? e.type}{e.payload.minute ? ` · ${e.payload.minute}'` : ""}{e.payload.period ? ` · ${e.payload.period}` : ""}{e.payload.set ? ` · set ${e.payload.set}` : ""}</p>
                    <p className="truncate text-ink-2">{[e.payload.player, e.payload.side === "home" ? m.home.name : e.payload.side === "away" ? m.away.name : ""].filter(Boolean).join(" · ")}
                      {e.payload.score ? ` ${e.payload.score.home}-${e.payload.score.away}` : ""}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
    </div>
  );
}

export function TeamPage() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["team", id], queryFn: () => api<{ team: any; form: string[]; recent: Match[]; upcoming: Match[] }>(`/sports/teams/${id}`) });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const d = q.data!;
  const formTone: Record<string, string> = { W: "V", D: "E", L: "D" };
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {d.team.logo_url && <img src={d.team.logo_url} alt="" className="h-12 w-12 object-contain" />}
          <div><h1 className="text-2xl font-semibold">{d.team.name}</h1><p className="text-sm text-ink-2">{d.team.country}</p></div>
        </div>
        <FollowButton kind="team" id={d.team.id} />
      </div>
      <Card title="Forma reciente">
        <div className="flex gap-1.5">{d.form.length ? d.form.map((r, i) => (
          <span key={i} className={`flex h-8 w-8 items-center justify-center rounded-lg border text-sm font-semibold ${r === "W" ? "border-good" : r === "L" ? "border-bad" : "border-line"}`}>{formTone[r]}</span>
        )) : <span className="text-sm text-ink-2">Sin partidos registrados.</span>}</div>
        <p className="mt-2 text-xs text-muted">V = victoria · E = empate · D = derrota (más reciente primero)</p>
      </Card>
      <div className="grid gap-5 lg:grid-cols-2">
        <div><h2 className="mb-3 font-semibold">Próximos</h2>{d.upcoming.length ? <div className="space-y-3">{d.upcoming.map((m) => <MatchCardLite key={m.id} m={m} />)}</div> : <p className="text-sm text-ink-2">—</p>}</div>
        <div><h2 className="mb-3 font-semibold">Últimos resultados</h2>{d.recent.length ? <div className="space-y-3">{d.recent.map((m) => <MatchCardLite key={m.id} m={m} />)}</div> : <p className="text-sm text-ink-2">—</p>}</div>
      </div>
    </div>
  );
}

