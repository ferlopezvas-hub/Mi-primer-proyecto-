/**
 * Modo demo: responde a las llamadas de la app con un paquete de datos REALES exportado
 * de la base de datos (backend/scripts/export_demo.py), sin servidor. Lo que el usuario
 * cambia (seguimientos, preferencias, avisos leídos) se guarda solo en su navegador.
 */
import type { Match } from "./types";

declare global {
  interface Window { __SPORTAI_DEMO__?: any }
}

class DemoError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

let dataPromise: Promise<any> | null = null;
function load(): Promise<any> {
  dataPromise ??= window.__SPORTAI_DEMO__
    ? Promise.resolve(window.__SPORTAI_DEMO__)
    : fetch("demo-data.json").then((r) => r.json());
  return dataPromise;
}

const STORE = "sportai.demo.state";
interface State { follows?: any[]; prefs?: any; read?: number[]; nextFollowId?: number; users?: Record<number, any> }
function readState(): State { try { return JSON.parse(localStorage.getItem(STORE) || "{}"); } catch { return {}; } }
function writeState(s: State) { try { localStorage.setItem(STORE, JSON.stringify(s)); } catch { /* sin almacenamiento */ } }

const NOT_AVAILABLE = "No disponible en la versión de demostración.";
const dayKey = (iso: string) => {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

function deepMerge(base: any, patch: any): any {
  const out = Array.isArray(base) ? [...base] : { ...base };
  for (const [k, v] of Object.entries(patch ?? {})) {
    out[k] = v && typeof v === "object" && !Array.isArray(v) && base?.[k] && typeof base[k] === "object" ? deepMerge(base[k], v) : v;
  }
  return out;
}

export async function demoApi<T>(path: string, opts: { method?: string; body?: any } = {}): Promise<T> {
  const d = await load();
  const method = (opts.method ?? "GET").toUpperCase();
  const url = new URL(path, "http://demo.local");
  const p = url.pathname;
  const q = url.searchParams;
  const st = readState();
  const matches: Match[] = d.matches;
  const sport = q.get("sport");

  // ---------------------------------------------------------------- auth
  if (p === "/auth/setup-status") return { admin_exists: true, setup_available: false } as T;
  if (p.startsWith("/auth/")) {
    if (p === "/auth/login" || p === "/auth/refresh" || p === "/auth/change-password")
      return { access_token: "demo", refresh_token: "demo", token_type: "bearer", expires_in: 3600 } as T;
    if (p === "/auth/register") return { user: d.me, tokens: { access_token: "demo", refresh_token: "demo" } } as T;
    if (p === "/auth/forgot-password") return { detail: "En la demo no se envían correos. En la versión real recibirías un enlace por email." } as T;
    if (p === "/auth/reset-password") throw new DemoError(400, NOT_AVAILABLE);
    return undefined as T;
  }

  // ---------------------------------------------------------------- perfil
  if (p === "/me" && method === "GET") return d.me;
  if (p === "/me" && method === "PATCH") return { ...d.me, ...opts.body };
  if (p === "/me" && method === "DELETE") throw new DemoError(400, NOT_AVAILABLE);
  if (p === "/me/plans") return d.plans;
  if (p === "/me/notification-preferences") {
    let prefs = st.prefs ?? d.prefs.preferences;
    if (method === "PUT") {
      const b = { ...opts.body };
      if (b.clear_quiet_hours) { prefs = { ...prefs, quiet_hours: null }; delete b.clear_quiet_hours; }
      prefs = deepMerge(prefs, b);
      writeState({ ...st, prefs });
      return { preferences: prefs } as T;
    }
    return { ...d.prefs, preferences: prefs } as T;
  }
  if (p === "/me/follows" || p.startsWith("/me/follows/")) {
    let follows: any[] = st.follows ?? d.follows;
    if (method === "POST") {
      const { kind, target_id } = opts.body;
      const found = follows.find((f) => f.kind === kind && f.target_id === target_id);
      if (found) return found;
      if (follows.length >= 500) throw new DemoError(402, "Límite de seguimientos alcanzado");
      let name = "—", sp: string | null = null;
      if (kind === "match") { const m = matches.find((x) => x.id === target_id); if (m) { name = `${m.home.name} vs ${m.away.name}`; sp = m.sport; } }
      else if (kind === "team") { const t = matches.flatMap((m) => [m.home, m.away]).find((x) => x.id === target_id); if (t) { name = t.name; sp = t.sport; } }
      else { const c = d.competitions.find((x: any) => x.id === target_id); if (c) { name = c.name; sp = c.sport; } }
      const id = (st.nextFollowId ?? 1000) + 1;
      const f = { id, kind, target_id, name, sport: sp };
      follows = [f, ...follows];
      writeState({ ...st, follows, nextFollowId: id });
      return f as T;
    }
    if (method === "DELETE") {
      const id = Number(p.split("/").pop());
      writeState({ ...st, follows: follows.filter((f) => f.id !== id) });
      return undefined as T;
    }
    return follows as T;
  }
  if (p.startsWith("/me/push-subscriptions")) throw new DemoError(400, NOT_AVAILABLE);

  // ---------------------------------------------------------------- avisos
  if (p === "/notifications/vapid-public-key") return { key: null, enabled: false } as T;
  if (p.startsWith("/notifications")) {
    const read = new Set(st.read ?? []);
    const items = (d.notifications as any[]).map((n) => ({ ...n, read_at: n.read_at ?? (read.has(n.id) ? new Date().toISOString() : null) }));
    if (p === "/notifications/read-all") { writeState({ ...st, read: items.map((n) => n.id) }); return undefined as T; }
    if (p.endsWith("/read")) { const id = Number(p.split("/")[2]); writeState({ ...st, read: [...read, id] }); return undefined as T; }
    const unread = items.filter((n) => !n.read_at).length;
    let list = q.get("unread_only") === "true" ? items.filter((n) => !n.read_at) : items;
    list = list.slice(0, Number(q.get("limit") ?? 30));
    return { items: list, unread } as T;
  }

  // ---------------------------------------------------------------- deporte
  if (p === "/sports/live") return matches.filter((m) => m.status === "live" && (!sport || m.sport === sport)) as T;
  if (p === "/sports/competitions") return d.competitions;
  if (p === "/sports/calendar") {
    const month = q.get("month") ?? "";
    const days: Record<string, Record<string, number>> = {};
    for (const m of matches) {
      if (sport && m.sport !== sport) continue;
      const k = dayKey(m.start_time);
      if (!k.startsWith(month)) continue;
      days[k] ??= {};
      days[k][m.sport] = (days[k][m.sport] ?? 0) + 1;
    }
    return { month, days } as T;
  }
  if (p === "/sports/matches") {
    const from = q.get("date_from"), to = q.get("date_to"), team = Number(q.get("team_id") || 0);
    const list = matches.filter((m) => (!sport || m.sport === sport) && (!from || dayKey(m.start_time) >= from)
      && (!to || dayKey(m.start_time) <= to) && (!team || m.home.id === team || m.away.id === team)
      && (!q.get("status") || m.status === q.get("status")));
    return list.slice(0, Number(q.get("limit") ?? 50)) as T;
  }
  if (p.startsWith("/sports/matches/")) {
    const det = d.details[p.split("/")[3]];
    if (!det) throw new DemoError(404, "Partido no encontrado");
    return det;
  }
  if (p.startsWith("/sports/teams/")) {
    const id = Number(p.split("/")[3]);
    const mine = matches.filter((m) => m.home.id === id || m.away.id === id);
    const team = mine[0] ? (mine[0].home.id === id ? mine[0].home : mine[0].away) : null;
    if (!team) throw new DemoError(404, "No encontrado");
    const recent = mine.filter((m) => m.status === "finished").sort((a, b) => b.start_time.localeCompare(a.start_time)).slice(0, 10);
    const form = recent.map((m) => {
      const [a, b] = m.home.id === id ? [m.home_score!, m.away_score!] : [m.away_score!, m.home_score!];
      return a > b ? "W" : a < b ? "L" : "D";
    });
    return { team, form, recent, upcoming: mine.filter((m) => m.status === "scheduled").slice(0, 5) } as T;
  }
  if (p === "/sports/search") {
    const term = (q.get("q") ?? "").toLowerCase();
    const seen = new Map<number, any>();
    for (const m of matches) for (const t of [m.home, m.away]) if (t.name.toLowerCase().includes(term)) seen.set(t.id, t);
    const comps = (d.competitions as any[]).filter((c) => c.name.toLowerCase().includes(term));
    return { teams: [...seen.values()].sort((a, b) => a.name.localeCompare(b.name)).slice(0, 15), competitions: comps.slice(0, 10), matches: [] } as T;
  }

  // ---------------------------------------------------------------- predicciones
  if (p.startsWith("/predictions/match/")) {
    const r = d.predictions[p.split("/")[3]];
    if (!r) throw new DemoError(404, "Partido no encontrado");
    return r;
  }
  if (p === "/predictions/upcoming") return [] as T;
  if (p === "/predictions/top") return { threshold: 0.7, items: [],
    disclaimer: "Estimaciones estadísticas, no garantías. En la demo no hay partidos próximos." } as T;
  if (p === "/predictions/history") {
    const state = q.get("state") ?? "all";
    const includeBacktest = q.get("include_backtest") === "true";
    const out: any[] = [];
    for (const r of Object.values<any>(d.predictions)) {
      for (const pr of r.predictions) {
        if (pr.is_backtest && !includeBacktest) continue;
        if (sport && pr.sport !== sport) continue;
        if (state === "resolved" && !pr.result) continue;
        if (state === "pending" && pr.result) continue;
        out.push({ ...pr, match: r.match });
      }
    }
    out.sort((a, b) => b.kickoff_at.localeCompare(a.kickoff_at));
    return out.slice(0, Number(q.get("limit") ?? 50)) as T;
  }
  if (p === "/evaluation") return d.evaluation[q.get("mode") ?? "all"];

  // ---------------------------------------------------------------- administración
  if (p === "/admin/metrics") return d.admin.metrics;
  if (p === "/admin/providers") return d.admin.providers;
  if (p === "/admin/jobs") return d.admin.jobs;
  if (p.startsWith("/admin/jobs/")) throw new DemoError(400, "En la demo no hay servidor que ejecute tareas.");
  if (p === "/admin/users") {
    const users = d.admin.users.items.map((u: any) => ({ ...u, ...(st.users?.[u.id] ?? {}) }));
    return { total: users.length, items: users } as T;
  }
  if (p.startsWith("/admin/users/") && method === "PATCH") {
    const id = Number(p.split("/")[3]);
    const users = { ...(st.users ?? {}) };
    const body = { ...opts.body };
    if (body.plan_code) { body.plan = d.plans.plans.find((x: any) => x.code === body.plan_code); delete body.plan_code; }
    users[id] = { ...(users[id] ?? {}), ...body };
    writeState({ ...st, users });
    return users[id];
  }
  if (p === "/admin/audit") return [] as T;

  throw new DemoError(404, `Sin datos de demostración para ${p}`);
}

export const DEMO_INFO = () => load().then((d) => ({ generatedAt: d.generated_at as string, since: d.since as string, source: d.source as string }));
