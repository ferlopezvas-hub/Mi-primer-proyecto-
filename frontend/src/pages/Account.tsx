import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff, Smartphone, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useFollows } from "../components/FollowButton";
import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ago, SPORT_LABEL } from "../lib/format";
import { disablePush, enablePush, pushState, type PushState } from "../lib/push";
import type { Notification, Plan, Sport } from "../lib/types";

export function NotificationsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["notifications", "all"], queryFn: () => api<{ items: Notification[]; unread: number }>("/notifications?limit=100"), refetchInterval: 30_000 });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["notifications"] }); qc.invalidateQueries({ queryKey: ["unread"] }); };
  const readAll = useMutation({ mutationFn: () => api("/notifications/read-all", { method: "POST" }), onSuccess: refresh });
  const readOne = useMutation({ mutationFn: (id: number) => api(`/notifications/${id}/read`, { method: "POST" }), onSuccess: refresh });
  return (
    <div className="space-y-5">
      <PageHeader title="Centro de notificaciones" subtitle={q.data ? `${q.data.unread} sin leer` : undefined}
        actions={<div className="flex gap-2"><Link to="/settings" className="btn-ghost">Preferencias</Link>
          <button className="btn-primary" onClick={() => readAll.mutate()} disabled={!q.data?.unread}>Marcar todo leído</button></div>} />
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> : !q.data?.items.length ? (
        <Empty icon={<Bell className="h-8 w-8" />} title="No tienes notificaciones" text="Sigue equipos, competiciones o partidos desde el buscador para recibir avisos." action={<Link className="btn-primary mt-2" to="/search">Buscar equipos</Link>} />
      ) : (
        <ul className="card divide-y divide-line">
          {q.data.items.map((n) => (
            <li key={n.id} className={n.read_at ? "" : "bg-surface-2/60"}>
              <Link to={n.match_id ? `/matches/${n.match_id}` : "#"} onClick={() => !n.read_at && readOne.mutate(n.id)} className="flex items-start gap-3 p-4">
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.read_at ? "bg-transparent" : "bg-brand"}`} aria-label={n.read_at ? "Leída" : "No leída"} />
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{n.title}</p>
                  <p className="text-sm text-ink-2">{n.body}</p>
                </div>
                <span className="shrink-0 text-xs text-muted">{ago(n.created_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ProfilePage() {
  const { user, reload, logout } = useAuth();
  const qc = useQueryClient();
  const [name, setName] = useState(user?.full_name ?? "");
  const [tz, setTz] = useState(user?.timezone ?? "Europe/Madrid");
  const [msg, setMsg] = useState<string | null>(null);
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [confirmDel, setConfirmDel] = useState(false);
  const [delPw, setDelPw] = useState("");
  const follows = useFollows();
  const plans = useQuery({ queryKey: ["plans"], queryFn: () => api<{ current: string; plans: Plan[]; payments_enabled: boolean }>("/me/plans") });
  const save = useMutation({ mutationFn: () => api("/me", { method: "PATCH", body: { full_name: name, timezone: tz } }), onSuccess: () => { reload(); setMsg("Perfil guardado"); } });
  const changePw = useMutation({ mutationFn: () => api("/auth/change-password", { method: "POST", body: pw }),
    onSuccess: (t: any) => { import("../lib/api").then(({ tokens }) => tokens.set(t.access_token, t.refresh_token)); setPw({ current_password: "", new_password: "" }); setMsg("Contraseña cambiada. Se cerraron las demás sesiones."); } });
  const unfollow = useMutation({ mutationFn: (id: number) => api(`/me/follows/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["follows"] }) });
  const setup = useQuery({ queryKey: ["setup"], queryFn: () => api<{ admin_exists: boolean; setup_available: boolean }>("/auth/setup-status", { auth: false }) });
  const [code, setCode] = useState("");
  const claim = useMutation({ mutationFn: () => api("/auth/claim-admin", { method: "POST", body: { code } }),
    onSuccess: async (t: any) => { const { tokens } = await import("../lib/api"); tokens.set(t.access_token, t.refresh_token); await reload(); setMsg("Ya eres administrador."); } });
  const del = useMutation({ mutationFn: (password: string) => api("/me", { method: "DELETE", body: { password } }), onSuccess: () => logout() });
  if (!user) return null;
  return (
    <div className="space-y-5">
      <PageHeader title="Perfil" subtitle={user.email} />
      {msg && <StatusBadge kind="good">{msg}</StatusBadge>}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Datos personales">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
            <div><label className="label" htmlFor="pname">Nombre</label><input id="pname" className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
            <div><label className="label" htmlFor="ptz">Zona horaria</label>
              <select id="ptz" className="input" value={tz} onChange={(e) => setTz(e.target.value)}>
                {["Europe/Madrid", "Europe/London", "Europe/Lisbon", "Atlantic/Canary", "America/Mexico_City", "America/Bogota", "America/Lima", "America/Santiago", "America/Argentina/Buenos_Aires", "America/New_York", "UTC"].map((z) => <option key={z}>{z}</option>)}
              </select></div>
            {save.error && <ErrorBox error={save.error} />}
            <button className="btn-primary" disabled={save.isPending}>Guardar</button>
          </form>
        </Card>
        <Card title="Tu plan">
          {plans.data ? (
            <div className="space-y-3">
              {plans.data.plans.map((p) => (
                <div key={p.code} className={`rounded-xl border p-3 ${p.code === plans.data.current ? "border-brand" : "border-line"}`}>
                  <div className="flex items-center justify-between"><p className="font-semibold">{p.name}</p>{p.code === plans.data.current && <Badge tone="brand">Actual</Badge>}</div>
                  <p className="text-sm text-ink-2">{p.description}</p>
                  <p className="mt-1 text-xs text-muted">{p.prediction_views_per_day ? `${p.prediction_views_per_day} análisis/día` : "Análisis ilimitados"} · hasta {p.max_follows} seguimientos · {p.full_explanations ? "explicaciones completas" : "explicaciones resumidas"}</p>
                </div>
              ))}
              {!plans.data.payments_enabled && <p className="text-xs text-muted">Los pagos aún no están activos. El cambio de plan lo gestiona un administrador.</p>}
            </div>
          ) : <Spinner />}
        </Card>
        <Card title="Lo que sigues">
          {!follows.data?.length ? <p className="text-sm text-ink-2">Aún no sigues nada. <Link to="/search" className="text-brand">Buscar</Link></p> : (
            <ul className="divide-y divide-line">{follows.data.map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-2 py-2">
                <span className="min-w-0 truncate">{f.name} <span className="text-xs text-muted">{{ team: "equipo/jugador", match: "partido", competition: "competición" }[f.kind]}{f.sport ? ` · ${SPORT_LABEL[f.sport as Sport]}` : ""}</span></span>
                <button className="btn-ghost min-h-[36px] px-3 py-1" onClick={() => unfollow.mutate(f.id)} aria-label={`Dejar de seguir ${f.name}`}><Trash2 className="h-4 w-4" /></button>
              </li>
            ))}</ul>
          )}
        </Card>
        {setup.data?.setup_available && user.role !== "admin" && (
          <Card title="Configuración inicial">
            <p className="mb-3 text-sm text-ink-2">Aún no hay administrador. Pega el código <b>ADMIN_SETUP_CODE</b> que aparece en el panel de tu servidor para convertir esta cuenta en la de administración. Solo funciona una vez.</p>
            <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); claim.mutate(); }}>
              <input id="setupcode" className="input flex-1" value={code} onChange={(e) => setCode(e.target.value)} placeholder="Código de configuración" aria-label="Código de configuración" required />
              <button className="btn-primary" disabled={claim.isPending}>Activar</button>
            </form>
            {claim.error && <div className="mt-2"><ErrorBox error={claim.error} /></div>}
          </Card>
        )}
        <Card title="Seguridad">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); changePw.mutate(); }}>
            <div><label className="label" htmlFor="cp">Contraseña actual</label><input id="cp" type="password" className="input" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} required /></div>
            <div><label className="label" htmlFor="np">Nueva contraseña</label><input id="np" type="password" className="input" autoComplete="new-password" minLength={10} value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} required /></div>
            {changePw.error && <ErrorBox error={changePw.error} />}
            <button className="btn-primary" disabled={changePw.isPending}>Cambiar contraseña</button>
          </form>
          <div className="mt-6 border-t border-line pt-4">
            <p className="text-sm font-medium">Eliminar cuenta</p>
            <p className="mb-2 text-sm text-ink-2">Se borran tus datos personales, seguimientos y notificaciones. No se puede deshacer.</p>
            {!confirmDel ? (
              <button className="btn-ghost text-bad" onClick={() => setConfirmDel(true)}>Eliminar mi cuenta</button>
            ) : (
              <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); del.mutate(delPw); }}>
                <label className="label" htmlFor="delpw">Escribe tu contraseña para confirmar</label>
                <input id="delpw" type="password" className="input" value={delPw} onChange={(e) => setDelPw(e.target.value)} required />
                <div className="flex gap-2">
                  <button className="btn-primary bg-bad" disabled={del.isPending}>Eliminar definitivamente</button>
                  <button type="button" className="btn-ghost" onClick={() => setConfirmDel(false)}>Cancelar</button>
                </div>
              </form>
            )}
            {del.error && <ErrorBox error={del.error} />}
          </div>
        </Card>
      </div>
    </div>
  );
}

interface Prefs { channels: { push: boolean }; upcoming_minutes: number; quiet_hours: { start: string; end: string } | null; events: Record<string, Record<string, boolean>> }
interface PrefsResp { preferences: Prefs; catalog: Record<string, Record<string, { label: string; default: boolean }>>; allowed_upcoming_minutes: number[] }

export function SettingsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["prefs"], queryFn: () => api<PrefsResp>("/me/notification-preferences") });
  const save = useMutation({ mutationFn: (body: any) => api("/me/notification-preferences", { method: "PUT", body }),
    onSuccess: (d: any) => qc.setQueryData(["prefs"], (old: PrefsResp | undefined) => old && { ...old, preferences: d.preferences }) });
  const [push, setPush] = useState<PushState | null>(null);
  const [pushErr, setPushErr] = useState<unknown>(null);
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem("sportai.theme") ?? "system"; } catch { return "system"; } });
  useEffect(() => { pushState().then(setPush); }, []);
  useEffect(() => {
    if (theme === "system") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("sportai.theme", theme); } catch { /* ignore */ }
  }, [theme]);
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const { preferences: p, catalog, allowed_upcoming_minutes } = q.data!;
  const togglePush = async () => {
    setPushErr(null);
    try { setPush(push === "enabled" ? await disablePush() : await enablePush()); } catch (e) { setPushErr(e); }
  };
  const pushText: Record<PushState, string> = {
    enabled: "Activadas en este dispositivo", disabled: "Desactivadas en este dispositivo", denied: "Bloqueadas en el navegador: actívalas en los ajustes del sistema",
    unsupported: "Este navegador no admite notificaciones push", "ios-needs-install": "En iPhone/iPad: pulsa Compartir → “Añadir a pantalla de inicio”, abre la app desde ahí y vuelve aquí",
    "server-off": import.meta.env.VITE_DEMO === "1" ? "No disponibles en la demo: requieren el servidor" : "El servidor aún no tiene configuradas las claves push (VAPID)",
  };
  return (
    <div className="space-y-5">
      <PageHeader title="Configuración" subtitle="Elige qué quieres recibir y cómo" />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Notificaciones push">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="flex items-center gap-2 text-sm"><Smartphone className="h-4 w-4" />{push ? pushText[push] : "Comprobando…"}</p>
            {(push === "enabled" || push === "disabled") && (
              <button className={push === "enabled" ? "btn-ghost" : "btn-primary"} onClick={togglePush}>
                {push === "enabled" ? <><BellOff className="h-4 w-4" />Desactivar</> : <><Bell className="h-4 w-4" />Activar</>}
              </button>
            )}
          </div>
          {!!pushErr && <div className="mt-3"><ErrorBox error={pushErr} /></div>}
          <label className="mt-4 flex min-h-[44px] items-center justify-between gap-3 text-sm">
            <span>Enviar avisos push (además del centro de notificaciones)</span>
            <input type="checkbox" className="h-5 w-5" checked={p.channels.push} onChange={(e) => save.mutate({ channels: { push: e.target.checked } })} />
          </label>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            <div><label className="label" htmlFor="upm">Aviso de partido próximo</label>
              <select id="upm" className="input" value={p.upcoming_minutes} onChange={(e) => save.mutate({ upcoming_minutes: Number(e.target.value) })}>
                {allowed_upcoming_minutes.map((m) => <option key={m} value={m}>{m} minutos antes</option>)}
              </select></div>
            <div><label className="label">Horas de silencio (sin push)</label>
              <div className="flex items-center gap-2">
                <input type="time" className="input" aria-label="Inicio del silencio" defaultValue={p.quiet_hours?.start ?? ""} onBlur={(e) => e.target.value && save.mutate({ quiet_hours: { start: e.target.value, end: p.quiet_hours?.end ?? "08:00" } })} />
                <input type="time" className="input" aria-label="Fin del silencio" defaultValue={p.quiet_hours?.end ?? ""} onBlur={(e) => e.target.value && save.mutate({ quiet_hours: { start: p.quiet_hours?.start ?? "23:00", end: e.target.value } })} />
              </div>
              {p.quiet_hours && <button className="mt-1 text-xs text-brand" onClick={() => save.mutate({ clear_quiet_hours: true })}>Quitar horas de silencio</button>}
            </div>
          </div>
        </Card>
        <Card title="Apariencia">
          <div className="flex gap-2">{[["system", "Automático"], ["light", "Claro"], ["dark", "Oscuro"]].map(([v, l]) => (
            <button key={v} className={theme === v ? "btn-primary" : "btn-ghost"} onClick={() => setTheme(v)}>{l}</button>
          ))}</div>
        </Card>
        {Object.entries(catalog).map(([sport, events]) => (
          <Card key={sport} title={`Eventos de ${SPORT_LABEL[sport as Sport].toLowerCase()}`}>
            <ul className="divide-y divide-line">
              {Object.entries(events).map(([k, meta]) => (
                <li key={k}>
                  <label className="flex min-h-[44px] items-center justify-between gap-3 text-sm">
                    <span>{meta.label}</span>
                    <input type="checkbox" className="h-5 w-5" checked={p.events[sport]?.[k] ?? false}
                      onChange={(e) => save.mutate({ events: { [sport]: { [k]: e.target.checked } } })} />
                  </label>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
      {save.error && <ErrorBox error={save.error} />}
      <p className="text-xs text-muted">Solo recibirás avisos de los equipos, jugadores, competiciones y partidos que sigas. Cada evento se notifica una única vez.</p>
    </div>
  );
}
