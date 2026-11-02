import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, tokens } from "./api";
import type { User } from "./types";

interface AuthCtx { user: User | null; loading: boolean; login: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; password: string; full_name: string; accept_terms: boolean }) => Promise<void>;
  logout: () => Promise<void>; reload: () => Promise<void> }

const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    if (!tokens.access && !tokens.refresh) { setUser(null); setLoading(false); return; }
    for (let attempt = 0; attempt < 4; attempt++) {
      try { setUser(await api<User>("/me")); break; } catch (e) {
        // Solo un 401 significa sesión inválida; 429/red/5xx son temporales: se reintenta.
        if (e instanceof ApiError && e.status === 401) { setUser(null); break; }
        if (attempt === 3) { setUser(null); break; }
        await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
      }
    }
    setLoading(false);
  }, []);
  useEffect(() => {
    reload();
    const out = () => setUser(null);
    const recheck = () => { reload(); };
    window.addEventListener("sportai:logout", out);
    window.addEventListener("sportai:access", recheck);
    return () => { window.removeEventListener("sportai:logout", out); window.removeEventListener("sportai:access", recheck); };
  }, [reload]);
  const login = async (email: string, password: string) => {
    const t = await api("/auth/login", { method: "POST", body: { email, password }, auth: false });
    tokens.set(t.access_token, t.refresh_token);
    await reload();
  };
  const register = async (data: { email: string; password: string; full_name: string; accept_terms: boolean }) => {
    const r = await api("/auth/register", { method: "POST", body: data, auth: false });
    tokens.set(r.tokens.access_token, r.tokens.refresh_token);
    setUser(r.user);
  };
  const logout = async () => {
    const rt = tokens.refresh;
    if (rt) await api("/auth/logout", { method: "POST", body: { refresh_token: rt }, auth: false }).catch(() => undefined);
    tokens.clear();
    setUser(null);
  };
  return <Ctx.Provider value={{ user, loading, login, register, logout, reload }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
