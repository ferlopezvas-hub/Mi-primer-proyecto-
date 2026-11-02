const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";
const ACCESS = "sportai.access";
const REFRESH = "sportai.refresh";

function read(k: string) { try { return localStorage.getItem(k); } catch { return null; } }
function write(k: string, v: string | null) { try { v === null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* modo privado */ } }

export const tokens = {
  get access() { return read(ACCESS); },
  get refresh() { return read(REFRESH); },
  set(access: string, refresh: string) { write(ACCESS, access); write(REFRESH, refresh); },
  clear() { write(ACCESS, null); write(REFRESH, null); },
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

let refreshing: Promise<boolean> | null = null;
async function tryRefresh(): Promise<boolean> {
  const rt = tokens.refresh;
  if (!rt) return false;
  refreshing ??= fetch(`${BASE}/api/v1/auth/refresh`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: rt }),
  }).then(async (r) => {
    if (!r.ok) { tokens.clear(); return false; }
    const d = await r.json();
    tokens.set(d.access_token, d.refresh_token);
    return true;
  }).catch(() => false).finally(() => { setTimeout(() => { refreshing = null; }, 0); });
  return refreshing;
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; auth?: boolean } = {}): Promise<T> {
  const doFetch = () => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (opts.auth !== false && tokens.access) headers.Authorization = `Bearer ${tokens.access}`;
    return fetch(`${BASE}/api/v1${path}`, { method: opts.method ?? "GET", headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body) });
  };
  let res: Response;
  try { res = await doFetch(); } catch { throw new ApiError(0, "Sin conexión con el servidor. Reintentando…"); }
  if (res.status === 401 && opts.auth !== false && (await tryRefresh())) res = await doFetch();
  if (res.status === 401 && opts.auth !== false) { tokens.clear(); window.dispatchEvent(new Event("sportai:logout")); }
  if (!res.ok) {
    let msg = `Error ${res.status}`;
    try { const d = await res.json(); msg = typeof d.detail === "string" ? d.detail : Array.isArray(d.detail) ? d.detail.map((x: any) => x.msg).join(". ") : msg; } catch { /* sin cuerpo */ }
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}
