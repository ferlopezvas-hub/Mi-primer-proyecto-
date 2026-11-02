import { useQuery } from "@tanstack/react-query";
import { Bell, CalendarDays, Radio } from "lucide-react";
import { Link } from "react-router-dom";
import { MatchCard } from "../components/MatchCard";
import { ProbabilityBar } from "../components/ProbabilityBar";
import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner, Stat } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ago, pct } from "../lib/format";
import type { Evaluation, Match, Notification } from "../lib/types";

interface Upcoming { match: Match; market: string; probabilities: Record<string, number>; predicted_outcome: string; confidence: number; confidence_label: string; data_quality_level: string }

export function Dashboard() {
  const { user } = useAuth();
  const today = new Date().toISOString().slice(0, 10);
  const live = useQuery({ queryKey: ["live"], queryFn: () => api<Match[]>("/sports/live"), refetchInterval: 30_000 });
  const todayQ = useQuery({ queryKey: ["matches", today], queryFn: () => api<Match[]>(`/sports/matches?date_from=${today}&date_to=${today}&limit=100`) });
  const upcoming = useQuery({ queryKey: ["upcoming"], queryFn: () => api<Upcoming[]>("/predictions/upcoming?limit=6") });
  const evalQ = useQuery({ queryKey: ["evaluation", "live"], queryFn: () => api<Evaluation>("/evaluation?mode=live") });
  const backQ = useQuery({ queryKey: ["evaluation", "backtest"], queryFn: () => api<Evaluation>("/evaluation?mode=backtest") });
  const bt = backQ.data?.by_market["football:1x2"];
  const notes = useQuery({ queryKey: ["notifications", "recent"], queryFn: () => api<{ items: Notification[]; unread: number }>("/notifications?limit=5") });

  const ev = evalQ.data;
  return (
    <div className="space-y-6">
      <PageHeader title={`Hola${user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}`} subtitle="Tu resumen deportivo de hoy" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="En directo" value={live.data?.length ?? "—"} hint={<Link to="/live" className="text-brand">Ver partidos</Link>} />
        <Stat label="Partidos hoy" value={todayQ.data?.length ?? "—"} hint={<Link to="/calendar" className="text-brand">Calendario</Link>} />
        <Stat label="Avisos sin leer" value={notes.data?.unread ?? "—"} hint={<Link to="/notifications" className="text-brand">Centro de avisos</Link>} />
        <Stat label="Acierto (predicciones nuevas)" value={ev?.overall.n ? pct(ev.overall.accuracy, 1) : "—"}
          hint={ev ? (ev.overall.n ? <>{ev.overall.n} resueltas · objetivo {pct(ev.target_accuracy)}</> : "Aún sin predicciones nuevas resueltas") : "—"} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="En directo" action={<Link to="/live" className="text-sm text-brand">Todo</Link>}>
            {live.isLoading ? <Spinner /> : live.error ? <ErrorBox error={live.error} /> : !live.data?.length ? (
              <Empty icon={<Radio className="h-8 w-8" />} title="No hay partidos en juego ahora mismo" text="Los marcadores se actualizan solos cada minuto, también con la app cerrada (las notificaciones te avisarán)." />
            ) : <div className="grid gap-3 sm:grid-cols-2">{live.data.slice(0, 4).map((m) => <MatchCard key={m.id} m={m} />)}</div>}
          </Card>

          <Card title="Próximas predicciones" action={<Link to="/predictions" className="text-sm text-brand">Historial</Link>}>
            {upcoming.isLoading ? <Spinner /> : upcoming.error ? <ErrorBox error={upcoming.error} /> : !upcoming.data?.length ? (
              <Empty icon={<CalendarDays className="h-8 w-8" />} title="Sin predicciones pendientes"
                text="Se generan automáticamente en las 72 h previas a cada partido, solo cuando hay datos históricos suficientes." />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {upcoming.data.map((u) => (
                  <MatchCard key={u.match.id} m={u.match} extra={
                    <div className="space-y-2">
                      <ProbabilityBar probabilities={u.probabilities} market={u.market} match={u.match} pick={u.predicted_outcome} />
                      <div className="flex flex-wrap gap-1.5">
                        <Badge>Confianza {u.confidence_label}</Badge>
                        <Badge>Datos: calidad {u.data_quality_level}</Badge>
                      </div>
                    </div>
                  } />
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Últimos avisos" action={<Link to="/notifications" className="text-sm text-brand">Ver todos</Link>}>
            {notes.isLoading ? <Spinner /> : !notes.data?.items.length ? (
              <Empty icon={<Bell className="h-8 w-8" />} title="Sin avisos todavía" text="Sigue equipos o partidos para recibir goles, inicios y finales." />
            ) : (
              <ul className="divide-y divide-line">
                {notes.data.items.map((n) => (
                  <li key={n.id} className="py-2.5">
                    <Link to={n.match_id ? `/matches/${n.match_id}` : "/notifications"} className="block">
                      <p className="text-sm font-medium">{n.title}</p>
                      <p className="truncate text-sm text-ink-2">{n.body}</p>
                      <p className="text-xs text-muted">{ago(n.created_at)}</p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Transparencia del modelo">
            {ev ? (
              <div className="space-y-2 text-sm">
                <p>Predicciones nuevas (guardadas antes del partido): <b className="tabular-nums">{ev.overall.n ? pct(ev.overall.accuracy, 1) : "—"}</b> sobre {ev.overall.n} resueltas{ev.overall.n > 0 && !ev.overall.conclusive ? " (muestra aún pequeña)" : ""}.</p>
                {bt && <p>Prueba histórica, fútbol 1X2: <b className="tabular-nums">{pct(bt.accuracy, 1)}</b> en {bt.n} partidos.</p>}
                <p className="text-ink-2">Objetivo experimental: {pct(ev.target_accuracy)}. Los modelos nunca se fuerzan para alcanzarlo.</p>
                <Link className="text-brand" to="/predictions?tab=accuracy">Ver precisión detallada →</Link>
              </div>
            ) : <Spinner />}
          </Card>
        </div>
      </div>
    </div>
  );
}
