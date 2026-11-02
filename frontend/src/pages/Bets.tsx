import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Wallet } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BetForm } from "../components/BetForm";
import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner, Stat, StatusBadge, Tabs } from "../components/ui";
import { api } from "../lib/api";
import { fmtDate, fmtDateTime, outcomeLabel, pct } from "../lib/format";
import type { Bet, BetAgg, BetSummary } from "../lib/types";

const money = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)} USD`);
const MARKET: Record<string, string> = { "1x2": "1X2", "over_under_2.5": "Más/Menos 2,5", btts: "Ambos marcan", moneyline: "Ganador", match_winner: "Ganador", other: "Otro" };
const MODEL: Record<string, string> = { siguiendo_modelo: "Siguiendo al modelo", contra_modelo: "Contra el modelo", sin_prediccion: "Sin predicción del modelo" };
const TIMING: Record<string, string> = { antes_del_partido: "Antes del partido", en_vivo: "En vivo" };

function AggTable({ rows, names }: { rows: Record<string, BetAgg>; names?: Record<string, string> }) {
  const entries = Object.entries(rows);
  if (!entries.length) return <p className="text-sm text-ink-2">Sin datos todavía.</p>;
  return (
    <div className="-mx-4 overflow-x-auto px-4">
      <table className="w-full min-w-[420px] text-left text-sm">
        <thead className="text-xs text-muted"><tr><th className="pb-2 pr-2 font-medium">Grupo</th><th className="pb-2 pr-2 font-medium">Liquidadas</th>
          <th className="pb-2 pr-2 font-medium">Aciertos</th><th className="pb-2 pr-2 font-medium">Beneficio</th><th className="pb-2 font-medium">ROI</th></tr></thead>
        <tbody>{entries.map(([k, a]) => (
          <tr key={k} className="border-t border-line">
            <td className="py-2 pr-2">{names?.[k] ?? k}</td><td className="py-2 pr-2 tabular-nums">{a.settled}</td>
            <td className="py-2 pr-2 tabular-nums">{pct(a.hit_rate)}</td>
            <td className={`py-2 pr-2 tabular-nums font-medium ${a.profit > 0 ? "text-good" : a.profit < 0 ? "text-bad" : ""}`}>{money(a.profit)}</td>
            <td className="py-2 tabular-nums">{pct(a.roi, 1)}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export function BetsPage() {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [view, setView] = useState<"all" | "pending">("all");
  const sum = useQuery({ queryKey: ["bets", "summary"], queryFn: () => api<BetSummary>("/bets/summary"), refetchInterval: 60_000 });
  const list = useQuery({ queryKey: ["bets", "list", view], queryFn: () => api<Bet[]>(`/bets${view === "pending" ? "?status=pending" : ""}`), refetchInterval: 60_000 });
  const refresh = () => qc.invalidateQueries({ queryKey: ["bets"] });
  const del = useMutation({ mutationFn: (id: number) => api(`/bets/${id}`, { method: "DELETE" }), onSuccess: refresh });
  const settle = useMutation({ mutationFn: ({ id, status }: { id: number; status: string }) => api(`/bets/${id}`, { method: "PATCH", body: { status } }), onSuccess: refresh });
  const o = sum.data?.overall;

  return (
    <div className="space-y-5">
      <PageHeader title="Mis apuestas" subtitle="Anota lo que apuestas en tu casa de apuestas y mide tu resultado real"
        actions={<button className="btn-primary" onClick={() => setAdding(!adding)}><Plus className="h-4 w-4" />Nueva apuesta</button>} />
      {adding && (
        <Card title="Registrar apuesta sin partido vinculado">
          <p className="mb-3 text-sm text-ink-2">Para apuestas de 1X2, goles o ambos marcan, regístrala desde la ficha del partido: así se liquida sola y se compara con el modelo.</p>
          <BetForm onDone={() => setAdding(false)} />
        </Card>
      )}
      {sum.isLoading ? <Spinner /> : sum.error ? <ErrorBox error={sum.error} /> : o && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Beneficio" value={<span className={o.profit > 0 ? "text-good" : o.profit < 0 ? "text-bad" : ""}>{money(o.profit)}</span>} hint={`Apostado: ${o.staked.toFixed(2)} USD`} />
            <Stat label="Rentabilidad (ROI)" value={pct(o.roi, 1)} hint="Beneficio ÷ importe apostado" />
            <Stat label="Aciertos" value={pct(o.hit_rate)} hint={`${o.won} de ${o.settled} · cuota media ${o.avg_odds ?? "—"}`} />
            <Stat label="Pendientes" value={sum.data!.pending} hint="Se liquidan al terminar el partido" />
          </div>
          {o.settled > 0 && o.settled < 100 && (
            <p className="rounded-xl border border-warn/60 bg-surface p-3 text-sm text-ink-2">Con {o.settled} apuestas liquidadas el resultado depende mucho de la suerte. Hacen falta varios cientos para saber si hay una ventaja real.</p>
          )}
          {sum.data!.cumulative.length > 1 && (
            <Card title="Evolución del beneficio">
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={sum.data!.cumulative.map((c, i) => ({ ...c, i: i + 1 }))} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                    <CartesianGrid stroke="var(--line)" vertical={false} />
                    <XAxis dataKey="i" tick={{ fill: "var(--muted)", fontSize: 12 }} stroke="var(--line)" />
                    <YAxis tick={{ fill: "var(--muted)", fontSize: 12 }} stroke="var(--line)" />
                    <ReferenceLine y={0} stroke="var(--muted)" />
                    <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 12, color: "var(--ink)" }}
                      formatter={(v: number) => [money(v), "Beneficio acumulado"]} labelFormatter={(l, p) => `Apuesta ${l} · ${p?.[0] ? fmtDate(p[0].payload.date) : ""}`} />
                    <Line dataKey="profit" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
          )}
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="¿Te va mejor siguiendo al modelo?"><AggTable rows={sum.data!.by_model} names={MODEL} /></Card>
            <Card title="Por casa de apuestas"><AggTable rows={sum.data!.by_bookmaker} /></Card>
            <Card title="Por mercado"><AggTable rows={sum.data!.by_market} names={MARKET} /></Card>
            <Card title="Antes del partido o en vivo"><AggTable rows={sum.data!.by_timing} names={TIMING} /></Card>
          </div>
        </>
      )}

      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Historial</h2>
        <Tabs value={view} onChange={setView} options={[{ value: "all", label: "Todas" }, { value: "pending", label: "Pendientes" }]} />
      </div>
      {(del.error || settle.error) && <ErrorBox error={del.error ?? settle.error} />}
      {list.isLoading ? <Spinner /> : list.error ? <ErrorBox error={list.error} /> : !list.data?.length ? (
        <Empty icon={<Wallet className="h-8 w-8" />} title="Aún no has registrado apuestas"
          text="Abre un partido próximo o en juego y pulsa “Registrar apuesta”. La app la liquidará sola y calculará tu beneficio real." />
      ) : (
        <ul className="card divide-y divide-line">
          {list.data.map((b) => (
            <li key={b.id} className="flex flex-wrap items-start justify-between gap-3 p-4">
              <div className="min-w-0">
                {b.match ? <Link to={`/matches/${b.match.id}`} className="font-medium hover:text-brand">{b.description}</Link> : <p className="font-medium">{b.description}</p>}
                <p className="text-sm text-ink-2">{MARKET[b.market] ?? b.market}: <b className="text-ink">{b.market === "other" ? b.selection : outcomeLabel(b.market, b.selection, b.match ?? undefined)}</b> · cuota {b.odds} · {b.stake.toFixed(2)} USD · {b.bookmaker || "—"}</p>
                <p className="text-xs text-muted">{fmtDateTime(b.placed_at)}{b.in_play ? " · en vivo" : ""}
                  {b.model_pick && <> · modelo: {outcomeLabel(b.market, b.model_pick, b.match ?? undefined)}{b.model_probability !== null && <> ({pct(b.model_probability)} para tu selección)</>}</>}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {b.status === "pending" ? <Badge>Pendiente</Badge> : b.status === "void" ? <Badge>Anulada</Badge> :
                  <StatusBadge kind={b.status === "won" ? "good" : "bad"}>{b.status === "won" ? "Ganada" : "Perdida"} {money(b.profit)}</StatusBadge>}
                {b.market === "other" && b.status === "pending" && (
                  <>
                    <button className="btn-ghost min-h-[36px] px-3 py-1" onClick={() => settle.mutate({ id: b.id, status: "won" })}>Ganada</button>
                    <button className="btn-ghost min-h-[36px] px-3 py-1" onClick={() => settle.mutate({ id: b.id, status: "lost" })}>Perdida</button>
                  </>
                )}
                {b.status === "pending" && <button className="btn-ghost min-h-[36px] px-3 py-1" aria-label="Borrar apuesta" onClick={() => del.mutate(b.id)}><Trash2 className="h-4 w-4" /></button>}
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted">Esta página no acepta apuestas: solo registra las que haces en tu casa de apuestas. Juega con responsabilidad y solo con dinero que puedas perder.</p>
    </div>
  );
}
