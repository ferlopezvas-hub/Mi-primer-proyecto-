import type { Match, Sport } from "./types";

export const SPORT_LABEL: Record<Sport, string> = { football: "Fútbol", basketball: "Básquet", tennis: "Tenis" };
export const SPORT_EMOJI: Record<Sport, string> = { football: "⚽", basketball: "🏀", tennis: "🎾" };

export const fmtTime = (iso: string) => new Date(iso).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
export const fmtDate = (iso: string) => new Date(iso).toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" });
export const fmtDateTime = (iso: string) => `${fmtDate(iso)} · ${fmtTime(iso)}`;
export const pct = (v: number | null | undefined, digits = 0) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)} %`);

export function ago(iso: string | null) {
  if (!iso) return "nunca";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "hace segundos";
  if (s < 3600) return `hace ${Math.round(s / 60)} min`;
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
  return `hace ${Math.round(s / 86400)} d`;
}

export function outcomeLabel(_market: string, o: string, m?: Match) {
  const home = m?.home.name ?? "Local";
  const away = m?.away.name ?? "Visitante";
  const map: Record<string, string> = { home, away, draw: "Empate", over: "Más de 2,5", under: "Menos de 2,5", yes: "Sí", no: "No", void: "Anulada" };
  return map[o] ?? o;
}

export function statusText(m: Match) {
  if (m.status === "live") {
    if (m.sport === "football") return m.status_detail === "HT" ? "Descanso" : m.elapsed ? `${m.elapsed}'` : "En juego";
    return m.status_detail || "En juego";
  }
  return { scheduled: fmtTime(m.start_time), finished: "Final", postponed: "Aplazado", cancelled: "Cancelado", unknown: "—" }[m.status];
}
