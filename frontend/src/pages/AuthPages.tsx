import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ErrorBox } from "../components/ui";
import { api, DEMO } from "../lib/api";
import { useAuth } from "../lib/auth";
import logo from "../assets/logo.svg";

function Shell({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <img src={logo} alt="" className="mb-3 h-14 w-14" />
          <h1 className="text-2xl font-semibold">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
        </div>
        <div className="card p-5">{children}</div>
      </div>
    </div>
  );
}

function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const run = (fn: () => Promise<void>) => async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError(null);
    try { await fn(); } catch (err) { setError(err); } finally { setBusy(false); }
  };
  return { busy, error, run };
}

export function LoginPage() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState(DEMO ? "demo@sportai" : "");
  const [password, setPassword] = useState(DEMO ? "demo" : "");
  const { busy, error, run } = useSubmit();
  return (
    <Shell title="Bienvenido" subtitle={DEMO ? "Demo: pulsa Iniciar sesión, no hace falta cuenta" : "Inteligencia deportiva con datos transparentes"}>
      <form className="space-y-4" onSubmit={run(async () => { await login(email, password); nav("/"); })}>
        <div><label className="label" htmlFor="email">Email</label>
          <input id="email" className="input" type={DEMO ? "text" : "email"} autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><label className="label" htmlFor="password">Contraseña</label>
          <input id="password" className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        {!!error && <ErrorBox error={error} />}
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Entrando…" : "Iniciar sesión"}</button>
        <div className="flex justify-between text-sm">
          <Link className="text-brand" to="/forgot-password">¿Olvidaste la contraseña?</Link>
          <Link className="text-brand" to="/register">Crear cuenta</Link>
        </div>
      </form>
    </Shell>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ full_name: "", email: "", password: "", accept_terms: false });
  const { busy, error, run } = useSubmit();
  return (
    <Shell title="Crea tu cuenta" subtitle="Plan gratuito. Sin tarjeta.">
      <form className="space-y-4" onSubmit={run(async () => { await register(f); nav("/"); })}>
        <div><label className="label" htmlFor="name">Nombre</label>
          <input id="name" className="input" autoComplete="name" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></div>
        <div><label className="label" htmlFor="remail">Email</label>
          <input id="remail" className="input" type="email" autoComplete="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
        <div><label className="label" htmlFor="rpass">Contraseña</label>
          <input id="rpass" className="input" type="password" autoComplete="new-password" required minLength={10} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          <p className="mt-1 text-xs text-muted">Mínimo 10 caracteres con mayúsculas, minúsculas y números.</p></div>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1 h-4 w-4" checked={f.accept_terms} onChange={(e) => setF({ ...f, accept_terms: e.target.checked })} required />
          <span>Acepto los términos de uso y la política de privacidad. Entiendo que las predicciones son estimaciones estadísticas, no garantías.</span>
        </label>
        {!!error && <ErrorBox error={error} />}
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Creando…" : "Crear cuenta"}</button>
        <p className="text-center text-sm">¿Ya tienes cuenta? <Link className="text-brand" to="/login">Inicia sesión</Link></p>
      </form>
    </Shell>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const { busy, error, run } = useSubmit();
  return (
    <Shell title="Recuperar contraseña" subtitle="Te enviaremos un enlace por email">
      {done ? <p className="text-sm">{done}</p> : (
        <form className="space-y-4" onSubmit={run(async () => {
          const r = await api("/auth/forgot-password", { method: "POST", body: { email }, auth: false }); setDone(r.detail);
        })}>
          <div><label className="label" htmlFor="femail">Email</label>
            <input id="femail" className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          {!!error && <ErrorBox error={error} />}
          <button className="btn-primary w-full" disabled={busy}>Enviar enlace</button>
        </form>
      )}
      <p className="mt-4 text-center text-sm"><Link className="text-brand" to="/login">Volver</Link></p>
    </Shell>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const [pwd, setPwd] = useState("");
  const [done, setDone] = useState(false);
  const { busy, error, run } = useSubmit();
  return (
    <Shell title="Nueva contraseña">
      {done ? <p className="text-sm">Contraseña actualizada. <Link className="text-brand" to="/login">Inicia sesión</Link></p> : (
        <form className="space-y-4" onSubmit={run(async () => {
          await api("/auth/reset-password", { method: "POST", body: { token: params.get("token"), new_password: pwd }, auth: false }); setDone(true);
        })}>
          <div><label className="label" htmlFor="npass">Nueva contraseña</label>
            <input id="npass" className="input" type="password" autoComplete="new-password" required minLength={10} value={pwd} onChange={(e) => setPwd(e.target.value)} /></div>
          {!!error && <ErrorBox error={error} />}
          <button className="btn-primary w-full" disabled={busy}>Guardar</button>
        </form>
      )}
    </Shell>
  );
}
