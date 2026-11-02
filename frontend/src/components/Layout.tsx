import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Bell, CalendarDays, Gauge, LayoutDashboard, LogOut, Menu, Radio, Search, Settings, Shield, User, X } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api, DEMO } from "../lib/api";
import { useAuth } from "../lib/auth";
import logo from "../assets/logo.svg";

const NAV = [
  { to: "/", label: "Inicio", icon: LayoutDashboard, end: true },
  { to: "/search", label: "Buscar", icon: Search },
  { to: "/calendar", label: "Calendario", icon: CalendarDays },
  { to: "/live", label: "En directo", icon: Radio },
  { to: "/predictions", label: "Predicciones", icon: Gauge },
  { to: "/notifications", label: "Notificaciones", icon: Bell },
  { to: "/profile", label: "Perfil", icon: User },
  { to: "/settings", label: "Configuración", icon: Settings },
];
const MOBILE = ["/", "/live", "/calendar", "/predictions", "/notifications"];

export function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  const { data: unread } = useQuery({
    queryKey: ["unread"], refetchInterval: 30_000,
    queryFn: () => api<{ unread: number }>("/notifications?limit=1").then((d) => d.unread),
  });
  const items = user?.role === "admin" ? [...NAV, { to: "/admin", label: "Administración", icon: Shield }] : NAV;

  const link = (n: (typeof items)[number], compact = false) => (
    <NavLink key={n.to} to={n.to} end={"end" in n ? n.end : false}
      className={({ isActive }) => clsx(
        compact ? "flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px]" : "flex min-h-[44px] items-center gap-3 rounded-xl px-3 text-sm font-medium",
        isActive ? (compact ? "text-brand" : "bg-brand text-brand-ink") : compact ? "text-ink-2" : "text-ink-2 hover:bg-surface-2")}>
      <span className="relative">
        <n.icon className="h-5 w-5" />
        {n.to === "/notifications" && !!unread && (
          <span className="absolute -right-2 -top-1.5 min-w-[16px] rounded-full bg-live px-1 text-center text-[10px] font-semibold leading-4 text-white">{unread > 99 ? "99+" : unread}</span>
        )}
      </span>
      <span className={compact ? "" : "truncate"}>{compact ? ({ "En directo": "Directo", Notificaciones: "Avisos" } as Record<string, string>)[n.label] ?? n.label : n.label}</span>
    </NavLink>
  );

  const sidebar = (
    <div className="flex h-full flex-col gap-1 p-3">
      <div className="mb-4 flex items-center gap-2 px-2 pt-2">
        <img src={logo} alt="" className="h-8 w-8" />
        <div className="leading-tight"><p className="text-sm font-bold">SPORT AI</p><p className="text-xs text-muted">PREDICTOR</p></div>
      </div>
      <nav className="flex flex-1 flex-col gap-1" aria-label="Principal">{items.map((n) => link(n))}</nav>
      <div className="mt-2 border-t border-line pt-3">
        <p className="truncate px-3 text-xs text-muted">{user?.email}</p>
        <p className="px-3 text-xs text-muted">Plan {user?.plan.name}</p>
        <button onClick={logout} className="mt-2 flex min-h-[44px] w-full items-center gap-3 rounded-xl px-3 text-sm text-ink-2 hover:bg-surface-2">
          <LogOut className="h-5 w-5" /> Cerrar sesión
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:pl-64">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-line bg-surface lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85%] bg-surface shadow-xl">
            <button aria-label="Cerrar menú" onClick={() => setOpen(false)} className="absolute right-2 top-2 p-2"><X className="h-5 w-5" /></button>
            {sidebar}
          </aside>
        </div>
      )}
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-surface/90 px-4 py-2 backdrop-blur lg:hidden" style={{ paddingTop: "max(0.5rem, env(safe-area-inset-top))" }}>
        <button aria-label="Abrir menú" onClick={() => setOpen(true)} className="-ml-2 p-2"><Menu className="h-6 w-6" /></button>
        <span className="font-semibold">SPORT AI PREDICTOR</span>
      </header>
      <main className="mx-auto max-w-6xl px-4 pb-28 pt-5 sm:px-6 lg:pb-10 lg:pt-8">
        {DEMO && (
          <div className="mb-5 rounded-xl border border-warn/60 bg-surface px-3 py-2 text-sm text-ink-2" role="note">
            <b className="text-ink">Demo</b> con datos reales de fútbol hasta el 2 nov 2026. Sin directo ni push (necesitan el servidor).
          </div>
        )}
        <Outlet />
      </main>
      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-surface lg:hidden" aria-label="Accesos rápidos">
        {items.filter((n) => MOBILE.includes(n.to)).map((n) => link(n, true))}
      </nav>
    </div>
  );
}
