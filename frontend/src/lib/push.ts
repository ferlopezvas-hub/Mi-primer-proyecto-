import { api } from "./api";

export type PushState = "unsupported" | "ios-needs-install" | "denied" | "disabled" | "enabled" | "server-off";

const isIOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || (navigator as any).standalone === true;

function b64ToUint8(b64: string) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export async function registerSW() {
  if ("serviceWorker" in navigator) {
    try { return await navigator.serviceWorker.register("/sw.js"); } catch { return null; }
  }
  return null;
}

export async function pushState(): Promise<PushState> {
  if (import.meta.env.VITE_DEMO === "1") return "server-off";
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    return isIOS() && !isStandalone() ? "ios-needs-install" : "unsupported";
  }
  if (Notification.permission === "denied") return "denied";
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = await reg?.pushManager.getSubscription();
  return sub ? "enabled" : "disabled";
}

export async function enablePush(): Promise<PushState> {
  const { key, enabled } = await api<{ key: string | null; enabled: boolean }>("/notifications/vapid-public-key", { auth: false });
  if (!enabled || !key) return "server-off";
  const perm = await Notification.requestPermission();
  if (perm !== "granted") return perm === "denied" ? "denied" : "disabled";
  const reg = (await navigator.serviceWorker.getRegistration()) ?? (await registerSW());
  if (!reg) return "unsupported";
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToUint8(key) });
  const json = sub.toJSON();
  await api("/me/push-subscriptions", { method: "POST", body: { endpoint: json.endpoint, keys: json.keys, user_agent: navigator.userAgent.slice(0, 300) } });
  return "enabled";
}

export async function disablePush(): Promise<PushState> {
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = await reg?.pushManager.getSubscription();
  if (sub) {
    await api(`/me/push-subscriptions?endpoint=${encodeURIComponent(sub.endpoint)}`, { method: "DELETE" }).catch(() => undefined);
    await sub.unsubscribe();
  }
  return "disabled";
}
