import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ChevronLeft, ChevronRight, Radio, Search as SearchIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { FollowButton } from "../components/FollowButton";
import { MatchCard } from "../components/MatchCard";
import { Card, Empty, ErrorBox, PageHeader, Spinner, Tabs } from "../components/ui";
import { api } from "../lib/api";
import { SPORT_EMOJI, SPORT_LABEL } from "../lib/format";
import type { Competition, Match, Sport, Team } from "../lib/types";

type SportFilter = "all" | Sport;
const SPORT_TABS: { value: SportFilter; label: string }[] = [
  { value: "all", label: "Todos" }, { value: "football", label: "⚽ Fútbol" }, { value: "basketball", label: "🏀 Básquet" }, { value: "tennis", label: "🎾 Tenis" },
];
const sportQS = (s: SportFilter) => (s === "all" ? "" : `sport=${s}`);

export function SearchPage() {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  const res = useQuery({
    queryKey: ["search", debounced], enabled: debounced.length >= 2,
    queryFn: () => api<{ teams: Team[]; competitions: Competition[]; matches: Match[] }>(`/sports/search?q=${encodeURIComponent(debounced)}`),
  });
  return (
    <div className="space-y-5">
      <PageHeader title="Buscador deportivo" subtitle="Equipos, jugadores y competiciones" />
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" />
        <input autoFocus className="input pl-10" placeholder="Ej.: Real Madrid, Premier League, Alcaraz…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar" />
      </div>
      {debounced.length < 2 ? <Empty icon={<SearchIcon className="h-8 w-8" />} title="Escribe al menos 2 letras" /> :
        res.isLoading ? <Spinner /> : res.error ? <ErrorBox error={res.error} /> : res.data && (
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Equipos y jugadores">
              {!res.data.teams.length ? <p className="text-sm text-ink-2">Sin resultados.</p> : (
                <ul className="divide-y divide-line">
                  {res.data.teams.map((t) => (
                    <li key={t.id} className="flex items-center justify-between gap-2 py-2">
                      <Link to={`/teams/${t.id}`} className="flex min-w-0 items-center gap-2">
                        {t.logo_url ? <img src={t.logo_url} alt="" className="h-6 w-6 object-contain" /> : <span>{SPORT_EMOJI[t.sport]}</span>}
                        <span className="truncate font-medium">{t.name}</span>
                        <span className="text-xs text-muted">{SPORT_LABEL[t.sport]}</span>
                      </Link>
                      <FollowButton kind="team" id={t.id} compact />
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Competiciones">
              {!res.data.competitions.length ? <p className="text-sm text-ink-2">Sin resultados.</p> : (
                <ul className="divide-y divide-line">
                  {res.data.competitions.map((c) => (
                    <li key={c.id} className="flex items-center justify-between gap-2 py-2">
                      <span className="min-w-0 truncate">{SPORT_EMOJI[c.sport]} {c.name} <span className="text-xs text-muted">{c.season}</span></span>
                      <FollowButton kind="competition" id={c.id} compact />
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            {!!res.data.matches.length && (
              <div className="lg:col-span-2">
                <h2 className="mb-3 font-semibold">Próximos partidos</h2>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{res.data.matches.map((m) => <MatchCard key={m.id} m={m} />)}</div>
              </div>
            )}
          </div>
        )}
    </div>
  );
}

const WEEKDAYS = ["L", "M", "X", "J", "V", "S", "D"];
const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function CalendarPage() {
  const [cursor, setCursor] = useState(() => { const d = new Date(); d.setDate(1); return d; });
  const [selected, setSelected] = useState(() => ymd(new Date()));
  const [sport, setSport] = useState<SportFilter>("all");
  const month = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}`;
  const cal = useQuery({ queryKey: ["calendar", month, sport], queryFn: () => api<{ days: Record<string, Record<string, number>> }>(`/sports/calendar?month=${month}&${sportQS(sport)}`) });
  const day = useQuery({ queryKey: ["matches", selected, sport], queryFn: () => api<Match[]>(`/sports/matches?date_from=${selected}&date_to=${selected}&limit=200&${sportQS(sport)}`) });
  const cells = useMemo(() => {
    const first = new Date(cursor); const offset = (first.getDay() + 6) % 7;
    const days = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
    return [...Array(offset).fill(null), ...Array.from({ length: days }, (_, i) => new Date(cursor.getFullYear(), cursor.getMonth(), i + 1))];
  }, [cursor]);
  const move = (n: number) => setCursor((c) => new Date(c.getFullYear(), c.getMonth() + n, 1));
  return (
    <div className="space-y-5">
      <PageHeader title="Calendario" subtitle="Actualizado automáticamente desde los proveedores de datos" actions={<Tabs value={sport} onChange={setSport} options={SPORT_TABS} />} />
      <div className="grid gap-5 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <button className="btn-ghost px-3" onClick={() => move(-1)} aria-label="Mes anterior"><ChevronLeft className="h-4 w-4" /></button>
            <p className="font-semibold capitalize">{cursor.toLocaleDateString("es-ES", { month: "long", year: "numeric" })}</p>
            <button className="btn-ghost px-3" onClick={() => move(1)} aria-label="Mes siguiente"><ChevronRight className="h-4 w-4" /></button>
          </div>
          <div className="grid grid-cols-7 gap-1 text-center text-xs text-muted">{WEEKDAYS.map((d) => <div key={d}>{d}</div>)}</div>
          <div className="mt-1 grid grid-cols-7 gap-1">
            {cells.map((d, i) => {
              if (!d) return <div key={i} />;
              const key = ymd(d); const counts = cal.data?.days[key]; const total = counts ? Object.values(counts).reduce((a, b) => a + b, 0) : 0;
              return (
                <button key={key} onClick={() => setSelected(key)} aria-pressed={selected === key}
                  className={clsx("flex aspect-square flex-col items-center justify-center rounded-lg text-sm", selected === key ? "bg-brand text-brand-ink" : "hover:bg-surface-2", key === ymd(new Date()) && selected !== key && "ring-1 ring-brand")}>
                  <span>{d.getDate()}</span>
                  {total > 0 && <span className={clsx("text-[10px] tabular-nums", selected === key ? "text-brand-ink" : "text-muted")}>{total}</span>}
                </button>
              );
            })}
          </div>
        </Card>
        <div className="lg:col-span-3">
          <h2 className="mb-3 font-semibold capitalize">{new Date(selected + "T12:00:00").toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" })}</h2>
          {day.isLoading ? <Spinner /> : day.error ? <ErrorBox error={day.error} /> : !day.data?.length ? <Empty title="No hay partidos este día" /> : (
            <div className="grid gap-3 sm:grid-cols-2">{day.data.map((m) => <MatchCard key={m.id} m={m} />)}</div>
          )}
        </div>
      </div>
    </div>
  );
}

export function LivePage() {
  const [sport, setSport] = useState<SportFilter>("all");
  const live = useQuery({ queryKey: ["live", sport], queryFn: () => api<Match[]>(`/sports/live?${sportQS(sport)}`), refetchInterval: 20_000 });
  return (
    <div className="space-y-5">
      <PageHeader title="En directo" subtitle="Se actualiza cada 20 segundos en pantalla; el servidor sigue los partidos 24/7"
        actions={<Tabs value={sport} onChange={setSport} options={SPORT_TABS} />} />
      {live.isLoading ? <Spinner /> : live.error ? <ErrorBox error={live.error} /> : !live.data?.length ? (
        <Empty icon={<Radio className="h-8 w-8" />} title="Ningún partido en juego" text="Activa las notificaciones y sigue a tus equipos para enterarte al momento." />
      ) : <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{live.data.map((m) => <MatchCard key={m.id} m={m} />)}</div>}
    </div>
  );
}
