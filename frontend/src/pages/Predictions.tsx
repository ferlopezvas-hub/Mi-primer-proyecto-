import { useQuery } from "@tanstack/react-query";
import { Gauge } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner, StatusBadge, Tabs } from "../components/ui";
import { api, DEMO } from "../lib/api";
import { SPORT_EMOJI, SPORT_LABEL, fmtDateTime, outcomeLabel, pct } from "../lib/format";
import type { Block, Evaluation, Prediction, Sport } from "../lib/types";

const MARKET_NAME: Record<string, string> = { "football:1x2": "Fútbol · 1X2", "football:over_under_2.5": "Fútbol · Más/Menos 2,5",
  "football:btts": "Fútbol · Ambos marcan", "basketball:moneyline": "Básquet · Ganador", "tennis:match_winner": "Tenis · Ganador" };

export function PredictionsPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as "history" | "accuracy") ?? "history";
  return (
    <div className="space-y-5">
      <PageHeader title="Predicciones" subtitle="Cada predicción se guarda antes del partido y no puede modificarse"
        actions={<Tabs value={tab} onChange={(v) => setParams({ tab: v })} options={[{ value: "history", label: "Historial" }, { value: "accuracy", label: "Precisión" }]} />} />
      {tab === "history" ? <History /> : <Accuracy />}
    </div>
  );
}

function History() {
  const [state, setState] = useState<"all" | "resolved" | "pending">("all");
  const [backtest, setBacktest] = useState(DEMO);
  const q = useQuery({ queryKey: ["history", state, backtest], queryFn: () => api<Prediction[]>(`/predictions/history?state=${state}&limit=100&include_backtest=${backtest}`) });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={state} onChange={setState} options={[{ value: "all", label: "Todas" }, { value: "pending", label: "Pendientes" }, { value: "resolved", label: "Resueltas" }]} />
        <label className="flex min-h-[44px] items-center gap-2 text-sm">
          <input id="incbt" type="checkbox" className="h-5 w-5" checked={backtest} onChange={(e) => setBacktest(e.target.checked)} />
          Incluir pruebas históricas (backtest)
        </label>
      </div>
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> : !q.data?.length ? (
        <Empty icon={<Gauge className="h-8 w-8" />} title="Aún no hay predicciones" text={backtest ? "No hay predicciones para este filtro." : "Las predicciones nuevas aparecerán aquí en cuanto el sistema analice los próximos partidos. Activa “Incluir pruebas históricas” para ver las del backtest."} />
      ) : (
        <div className="card divide-y divide-line">
          {q.data.map((p) => (
            <Link key={p.id} to={`/matches/${p.match_id}`} className="flex flex-wrap items-center justify-between gap-2 p-4 hover:bg-surface-2">
              <div className="min-w-0">
                <p className="truncate font-medium">{SPORT_EMOJI[p.sport]} {p.match?.home.name} vs {p.match?.away.name}</p>
                <p className="text-sm text-ink-2">{p.market_label} · {fmtDateTime(p.kickoff_at)}</p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {p.is_backtest && <Badge>Backtest</Badge>}
                <Badge tone="brand">{outcomeLabel(p.market, p.predicted_outcome, p.match)} · {pct(p.probabilities[p.predicted_outcome])}</Badge>
                {!p.result ? <Badge>Pendiente</Badge> : p.result.actual_outcome === "void" ? <Badge>Anulada</Badge> :
                  <StatusBadge kind={p.result.is_correct ? "good" : "bad"}>{p.result.is_correct ? "Acierto" : "Fallo"}</StatusBadge>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function TargetBar({ value, target }: { value: number | null; target: number }) {
  return (
    <div className="relative h-4 w-full rounded bg-surface-2" role="img" aria-label={`Acierto ${pct(value, 1)} frente a objetivo ${pct(target)}`}>
      {value !== null && <div className="h-4 rounded" style={{ width: `${value * 100}%`, background: "var(--series-1)" }} />}
      <div className="absolute -top-1 h-6 w-0.5 bg-ink" style={{ left: `${target * 100}%` }} title={`Objetivo ${pct(target)}`} />
    </div>
  );
}

function BlockRow({ name, b }: { name: string; b: Block }) {
  return (
    <tr className="border-t border-line">
      <td className="py-2 pr-3">{name}</td>
      <td className="py-2 pr-3 tabular-nums">{b.n}</td>
      <td className="py-2 pr-3 tabular-nums font-medium">{pct(b.accuracy, 1)}</td>
      <td className="hidden py-2 pr-3 tabular-nums text-ink-2 sm:table-cell">{b.accuracy_ci95 ? `${pct(b.accuracy_ci95[0], 1)} – ${pct(b.accuracy_ci95[1], 1)}` : "—"}</td>
      <td className="py-2 pr-3 tabular-nums">{b.brier?.toFixed(3) ?? "—"}{b.brier_uniform_baseline !== undefined && <span className="hidden text-xs text-muted sm:inline"> (azar {b.brier_uniform_baseline.toFixed(3)})</span>}</td>
      <td className="hidden py-2 pr-3 tabular-nums md:table-cell">{b.log_loss?.toFixed(3) ?? "—"}</td>
      <td className="py-2">{b.conclusive ? <StatusBadge kind="good">Suficiente</StatusBadge> : <StatusBadge kind="warn">Muestra pequeña</StatusBadge>}</td>
    </tr>
  );
}

function BlockTable({ rows }: { rows: [string, Block][] }) {
  return (
    <div className="-mx-4 overflow-x-auto px-4">
      <table className="w-full min-w-[420px] text-left text-sm">
        <thead className="text-xs text-muted"><tr>
          <th className="pb-2 pr-3 font-medium">Grupo</th><th className="pb-2 pr-3 font-medium">N</th><th className="pb-2 pr-3 font-medium">Acierto</th>
          <th className="hidden pb-2 pr-3 font-medium sm:table-cell">IC 95 %</th><th className="pb-2 pr-3 font-medium">Brier</th>
          <th className="hidden pb-2 pr-3 font-medium md:table-cell">Log loss</th><th className="pb-2 font-medium">Fiabilidad</th>
        </tr></thead>
        <tbody>{rows.map(([k, b]) => <BlockRow key={k} name={k} b={b} />)}</tbody>
      </table>
    </div>
  );
}

function Calibration({ ev }: { ev: Evaluation }) {
  const keys = Object.keys(ev.calibration);
  const [market, setMarket] = useState(keys[0]);
  const [asTable, setAsTable] = useState(false);
  const c = ev.calibration[market ?? keys[0]];
  if (!c) return null;
  const data = c.bins.map((b) => ({ p: +(b.mean_predicted * 100).toFixed(1), obs: +(b.observed_frequency * 100).toFixed(1), n: b.n, ideal: +(b.mean_predicted * 100).toFixed(1) }));
  return (
    <Card title="Calibración de probabilidades" action={<button className="text-sm text-brand" onClick={() => setAsTable(!asTable)}>{asTable ? "Ver gráfico" : "Ver tabla"}</button>}>
      <p className="mb-3 text-sm text-ink-2">Si el modelo dice 60 %, ¿ocurre el 60 % de las veces? Cuanto más cerca de la diagonal, mejor. ECE: <b>{c.ece ?? "—"}</b> (0 = perfecta).</p>
      <select className="input mb-3 sm:w-auto" value={market} onChange={(e) => setMarket(e.target.value)} aria-label="Mercado">
        {keys.map((k) => <option key={k} value={k}>{MARKET_NAME[k] ?? k}</option>)}
      </select>
      {asTable ? (
        <table className="w-full text-left text-sm"><thead className="text-xs text-muted"><tr><th>Probabilidad predicha</th><th>Frecuencia observada</th><th>N</th></tr></thead>
          <tbody>{data.map((d) => <tr key={d.p} className="border-t border-line"><td className="py-1.5">{d.p} %</td><td>{d.obs} %</td><td>{d.n}</td></tr>)}</tbody></table>
      ) : (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: -12 }}>
              <CartesianGrid stroke="var(--line)" strokeDasharray="0" vertical={false} />
              <XAxis dataKey="p" type="number" domain={[0, 100]} tick={{ fill: "var(--muted)", fontSize: 12 }} stroke="var(--line)" unit="%" />
              <YAxis type="number" domain={[0, 100]} tick={{ fill: "var(--muted)", fontSize: 12 }} stroke="var(--line)" unit="%" />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 12, color: "var(--ink)" }}
                formatter={(v: number, name: string) => [`${v} %`, name === "obs" ? "Observado" : "Ideal"]} labelFormatter={(l) => `Predicho ≈ ${l} %`} />
              <Line dataKey="ideal" stroke="var(--muted)" strokeDasharray="4 4" dot={false} strokeWidth={1.5} isAnimationActive={false} />
              <Line dataKey="obs" stroke="var(--series-1)" strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)", fill: "var(--series-1)" }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="mt-2 text-xs text-muted">Línea discontinua: calibración perfecta. Puntos: {c.n_points} probabilidades evaluadas.</p>
    </Card>
  );
}

function Accuracy() {
  const [mode, setMode] = useState<"all" | "live" | "backtest">("all");
  const q = useQuery({ queryKey: ["evaluation", mode], queryFn: () => api<Evaluation>(`/evaluation${mode === "all" ? "" : `?mode=${mode}`}`) });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const ev = q.data!;
  const o = ev.overall;
  return (
    <div className="space-y-5">
      <Tabs value={mode} onChange={setMode} options={[{ value: "all", label: "Todo" }, { value: "live", label: "Predicciones nuevas" }, { value: "backtest", label: "Pruebas históricas" }]} />
      <Card>
        <div className="grid gap-5 md:grid-cols-[auto_1fr] md:items-center">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted">Acierto real</p>
            <p className="text-5xl font-semibold tabular-nums">{pct(o.accuracy, 1)}</p>
            <p className="text-sm text-ink-2">{o.n} predicciones resueltas{o.accuracy_ci95 ? ` · IC 95 %: ${pct(o.accuracy_ci95[0], 1)}–${pct(o.accuracy_ci95[1], 1)}` : ""}</p>
          </div>
          <div className="space-y-2">
            <TargetBar value={o.accuracy} target={ev.target_accuracy} />
            <div className="flex flex-wrap justify-between gap-2 text-sm">
              <span>Objetivo experimental: <b>{pct(ev.target_accuracy)}</b></span>
              {o.gap_to_target !== null && <span className="tabular-nums">{o.gap_to_target >= 0 ? "Por encima" : "Por debajo"} en {pct(Math.abs(o.gap_to_target), 1)}</span>}
            </div>
            <p className="text-xs text-ink-2">{ev.target_note} Pendientes de resolver: {ev.pending_predictions}. El acierto global mezcla mercados con distinto número de resultados posibles: consulta la tabla por tipo de predicción.</p>
          </div>
        </div>
      </Card>
      {o.n === 0 ? <Empty title="Todavía no hay predicciones resueltas en este modo" /> : (
        <>
          <Card title="Por tipo de predicción"><BlockTable rows={Object.entries(ev.by_market).map(([k, b]) => [MARKET_NAME[k] ?? k, b])} /></Card>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Por nivel de confianza">
              <p className="mb-3 text-sm text-ink-2">Si la confianza funciona, “alta” debe acertar más que “baja”.</p>
              <div className="space-y-3">
                {(["alta", "media", "baja"] as const).filter((k) => ev.by_confidence[k]).map((k) => {
                  const b = ev.by_confidence[k];
                  return (
                    <div key={k}>
                      <div className="flex justify-between text-sm"><span className="capitalize">{k}</span><span className="tabular-nums">{pct(b.accuracy, 1)} · n={b.n}</span></div>
                      <div className="mt-1 h-2.5 rounded bg-surface-2"><div className="h-2.5 rounded" style={{ width: `${(b.accuracy ?? 0) * 100}%`, background: "var(--series-1)" }} /></div>
                    </div>
                  );
                })}
              </div>
            </Card>
            <Card title="Por deporte"><BlockTable rows={Object.entries(ev.by_sport).map(([k, b]) => [SPORT_LABEL[k as Sport] ?? k, b])} /></Card>
          </div>
          <Calibration ev={ev} />
          <Card title={mode === "live" ? "Por competición" : "Por competición y temporada"}><BlockTable rows={Object.entries(ev.by_competition)} /></Card>
          <p className="text-xs text-muted">Brier: error cuadrático de las probabilidades (menor es mejor; se compara con repartir la probabilidad a partes iguales). Log loss: penaliza la seguridad excesiva en fallos. Con menos de {ev.min_sample_for_conclusions} casos el porcentaje no es concluyente.</p>
        </>
      )}
    </div>
  );
}
