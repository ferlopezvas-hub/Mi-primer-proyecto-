import { Clock, LogOut } from "lucide-react";
import logo from "../assets/logo.svg";
import { useAuth } from "../lib/auth";
import { fmtDateTime } from "../lib/format";

/** Pantalla para usuarios registrados sin un periodo de acceso activo. */
export function AccessPending() {
  const { user, logout, reload } = useAuth();
  const expired = !!user?.access_expires_at;
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="card w-full max-w-md p-6 text-center">
        <img src={logo} alt="" className="mx-auto mb-4 h-14 w-14" />
        <Clock className="mx-auto mb-2 h-8 w-8 text-warn" />
        <h1 className="text-xl font-semibold">{expired ? "Tu acceso ha vencido" : "Tu cuenta está pendiente de activación"}</h1>
        <p className="mt-2 text-sm text-ink-2">
          {expired ? <>Venció el {fmtDateTime(user!.access_expires_at!)}. </> : null}
          El acceso se activa por periodos (normalmente 30 días) una vez confirmado el pago.
        </p>
        <div className="mt-4 rounded-xl bg-surface-2 p-3 text-sm">
          <p className="text-ink-2">Tu usuario: <b className="text-ink">{user?.email}</b></p>
          {user?.admin_contact ? <p className="mt-1">Contacto para activar o renovar: <b className="select-all">{user.admin_contact}</b></p>
            : <p className="mt-1 text-ink-2">Contacta con el administrador para activar tu acceso.</p>}
        </div>
        <div className="mt-5 flex justify-center gap-2">
          <button className="btn-primary" onClick={() => reload()}>Ya pagué, comprobar</button>
          <button className="btn-ghost" onClick={logout}><LogOut className="h-4 w-4" />Salir</button>
        </div>
      </div>
    </div>
  );
}
