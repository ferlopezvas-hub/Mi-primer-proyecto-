import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { useState } from "react";
import { Badge, Card, ErrorBox, PageHeader, Spinner, Stat, StatusBadge, Tabs } from "../components/ui";
import { api } from "../lib/api";
import { ago } from "../lib/format";

const TASKS = ["sync_fixtures", "sync_live", "sync_results", "generate_predictions", "resolve_predictions", "check_upcoming", "fanout_events"];

export function AdminPage() {
  const [tab, setTab] = useState<"overview" | "users" | "system">("overview");
  return (
    <div className="space-y-5">
      <PageHeader title="Administración" actions={<Tabs value={tab} onChange={setTab} options={[{ value: "overview", label: "Métricas" }, { value: "users", label: "Usuarios" }, { value: "system", label: "Sistema" }]} />} />
      {tab === "overview" ? <Overview /> : tab === "users" ? <Users /> : <System />}
    </div>
  );
}

function Overview() {
  const q = useQuery({ queryKey: ["admin", "metrics"], queryFn: () => api<any>("/admin/metrics?days=30") });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const d = q.data;
  const days = Object.entries(d.daily as Record<string, Record<string, { events: number; users: number }>>);
  const max = Math.max(1, ...days.map(([, v]) => Object.values(v).reduce((a, b) => Math.max(a, b.users), 0)));
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Usuarios" value={d.users_total} hint={Object.entries(d.users_by_plan).map(([k, v]) => `${k}: ${v}`).join(" · ")} />
        <Stat label="Activos (30 d)" value={d.users_active_period} />
        <Stat label="Avisos enviados (30 d)" value={d.notifications_period} hint={`${d.push_subscriptions} dispositivos push`} />
        <Stat label="Predicciones" value={d.predictions_live} hint={`${d.predictions_backtest} de backtest`} />
      </div>
      <Card title="Usuarios activos por día (30 días)">
        {!days.length ? <p className="text-sm text-ink-2">Sin actividad registrada.</p> : (
          <div className="flex h-40 items-end gap-[2px]" role="img" aria-label="Usuarios activos diarios">
            {days.map(([day, v]) => {
              const u = Math.max(0, ...Object.values(v).map((x) => x.users));
              return <div key={day} title={`${day}: ${u} usuarios`} className="flex-1 rounded-t" style={{ height: `${(u / max) * 100}%`, minHeight: 2, background: "var(--series-1)" }} />;
            })}
          </div>
        )}
      </Card>
      <Card title="Partidos en base de datos">
        <div className="flex flex-wrap gap-2">{Object.entries(d.matches).map(([k, v]) => <Badge key={k}>{k}: {String(v)}</Badge>)}</div>
      </Card>
    </div>
  );
}

function Users() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const q = useQuery({ queryKey: ["admin", "users", search], queryFn: () => api<{ total: number; items: any[] }>(`/admin/users?q=${encodeURIComponent(search)}`) });
  const patch = useMutation({ mutationFn: ({ id, body }: { id: number; body: any }) => api(`/admin/users/${id}`, { method: "PATCH", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }) });
  return (
    <Card title={q.data ? `${q.data.total} usuarios` : "Usuarios"}>
      {patch.error && <div className="mb-3"><ErrorBox error={patch.error} /></div>}
      <input className="input mb-3" placeholder="Buscar por email" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Buscar usuarios" />
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> : (
        <div className="-mx-4 overflow-x-auto px-4">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="text-xs text-muted"><tr><th className="pb-2">Email</th><th className="pb-2">Plan</th><th className="pb-2">Rol</th><th className="pb-2">Estado</th><th className="pb-2">Último acceso</th></tr></thead>
            <tbody>{q.data!.items.map((u) => (
              <tr key={u.id} className="border-t border-line">
                <td className="py-2 pr-2">{u.email}</td>
                <td className="py-2 pr-2"><select className="rounded-lg border border-line bg-surface px-2 py-1" value={u.plan.code} onChange={(e) => patch.mutate({ id: u.id, body: { plan_code: e.target.value } })}>
                  {["free", "pro", "elite"].map((p) => <option key={p}>{p}</option>)}</select></td>
                <td className="py-2 pr-2"><select className="rounded-lg border border-line bg-surface px-2 py-1" value={u.role} onChange={(e) => patch.mutate({ id: u.id, body: { role: e.target.value } })}>
                  <option value="user">user</option><option value="admin">admin</option></select></td>
                <td className="py-2 pr-2"><button onClick={() => patch.mutate({ id: u.id, body: { is_active: !u.is_active } })}>
                  {u.is_active ? <StatusBadge kind="good">Activo</StatusBadge> : <StatusBadge kind="bad">Desactivado</StatusBadge>}</button></td>
                <td className="py-2 text-ink-2">{ago(u.last_login_at)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function System() {
  const providers = useQuery({ queryKey: ["admin", "providers"], queryFn: () => api<any[]>("/admin/providers"), refetchInterval: 30_000 });
  const jobs = useQuery({ queryKey: ["admin", "jobs"], queryFn: () => api<any>("/admin/jobs?limit=40"), refetchInterval: 15_000 });
  const run = useMutation({ mutationFn: (name: string) => api(`/admin/jobs/${name}/run`, { method: "POST" }) });
  return (
    <div className="space-y-5">
      <Card title="Proveedores de datos">
        {providers.isLoading ? <Spinner /> : providers.error ? <ErrorBox error={providers.error} /> : (
          <div className="grid gap-3 sm:grid-cols-2">
            {providers.data!.map((p) => (
              <div key={p.name} className="rounded-xl border border-line p-3 text-sm">
                <div className="flex items-center justify-between"><p className="font-semibold">{p.name}</p>
                  {!p.configured ? <Badge>Sin API key</Badge> : p.circuit.open ? <StatusBadge kind="bad">Circuito abierto</StatusBadge> : <StatusBadge kind="good">Operativo</StatusBadge>}</div>
                <p className="text-ink-2">Deporte: {p.sport} · Directo: {p.supports_live ? "sí" : "no"}</p>
                <p className="text-ink-2">Cuota hoy: {p.quota_used_today}{p.daily_quota ? ` / ${p.daily_quota}` : ""}</p>
                <p className="text-ink-2">Último éxito: {p.circuit.last_success ? ago(new Date(p.circuit.last_success * 1000).toISOString()) : "—"}</p>
                {p.circuit.last_error && <p className="truncate text-xs text-muted">Último error: {p.circuit.last_error}</p>}
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card title="Tareas en segundo plano" action={jobs.data && <Badge>{jobs.data.live_matches} partidos en directo</Badge>}>
        <div className="mb-4 flex flex-wrap gap-2">{TASKS.map((t) => (
          <button key={t} className="btn-ghost min-h-[36px] px-3 py-1" onClick={() => run.mutate(t)}><Play className="h-3.5 w-3.5" />{t}</button>
        ))}</div>
        {run.error && <div className="mb-3"><ErrorBox error={run.error} /></div>}
        {run.isSuccess && <p className="mb-3 text-sm text-ink-2">Tarea en cola.</p>}
        {jobs.isLoading ? <Spinner /> : (
          <div className="-mx-4 overflow-x-auto px-4">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="text-xs text-muted"><tr><th className="pb-2">Tarea</th><th className="pb-2">Estado</th><th className="pb-2">Inicio</th><th className="pb-2">Detalle</th></tr></thead>
              <tbody>{jobs.data?.runs.map((r: any) => (
                <tr key={r.id} className="border-t border-line align-top">
                  <td className="py-2 pr-2">{r.name}</td>
                  <td className="py-2 pr-2">{r.status === "ok" ? <StatusBadge kind="good">ok</StatusBadge> : r.status === "error" ? <StatusBadge kind="bad">error</StatusBadge> : <Badge>{r.status}</Badge>}</td>
                  <td className="py-2 pr-2 text-ink-2">{ago(r.started_at)}</td>
                  <td className="max-w-xs truncate py-2 text-xs text-muted" title={JSON.stringify(r.detail)}>{JSON.stringify(r.detail)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
