import type { Match } from "../lib/types";

const ROWS: [string, string][] = [
  ["possession", "Posesión (%)"], ["shots", "Tiros totales"], ["shots_on_target", "Tiros a puerta"], ["xg", "Goles esperados (xG)"],
  ["corners", "Córners"], ["offsides", "Fueras de juego"], ["fouls", "Faltas"], ["yellow_cards", "Tarjetas amarillas"],
  ["red_cards", "Tarjetas rojas"], ["saves", "Paradas del portero"],
];

/** Comparativa local/visitante de las estadísticas del partido (en directo o finales). */
export function LiveStats({ m, events }: { m: Match; events: any[] }) {
  const live = m.stats?.live as { home: Record<string, number>; away: Record<string, number>; updated_at?: string } | undefined;
  const count = (type: string, side: string) => events.filter((e) => e.type === type && e.payload?.side === side).length;
  const pens = (side: string) => events.filter((e) => e.type === "goal" && e.payload?.side === side && /penal/i.test(e.payload?.detail ?? "")).length;
  const rows: { label: string; h: number; a: number }[] = [];
  if (live) {
    for (const [k, label] of ROWS) {
      const h = live.home?.[k], a = live.away?.[k];
      if (h === undefined && a === undefined) continue;
      rows.push({ label, h: Number(h ?? 0), a: Number(a ?? 0) });
    }
  } else if (events.length) {
    rows.push({ label: "Tarjetas amarillas", h: count("yellow_card", "home"), a: count("yellow_card", "away") });
    rows.push({ label: "Tarjetas rojas", h: count("red_card", "home"), a: count("red_card", "away") });
  }
  if (m.sport === "football" && events.length) {
    rows.push({ label: "Penaltis marcados", h: pens("home"), a: pens("away") });
    rows.push({ label: "Penaltis fallados", h: count("penalty_missed", "home"), a: count("penalty_missed", "away") });
  }
  const hist = m.stats && !live ? m.stats : null; // históricos importados (tiros/córners finales)
  if (!rows.length && hist && ("corners_home" in hist || "shots_home" in hist)) {
    for (const [k, label] of [["shots", "Tiros totales"], ["shots_on_target", "Tiros a puerta"], ["corners", "Córners"]] as const) {
      if (hist[`${k}_home`] !== undefined) rows.push({ label, h: hist[`${k}_home`], a: hist[`${k}_away`] });
    }
  }
  if (!rows.length) return <p className="text-sm text-ink-2">Las estadísticas aparecen cuando el partido está en juego (córners, tiros, fueras de juego, faltas, tarjetas…).</p>;
  return (
    <div className="space-y-3">
      {rows.map((r) => {
        const total = r.h + r.a || 1;
        return (
          <div key={r.label}>
            <div className="flex justify-between text-sm tabular-nums"><b>{r.h}</b><span className="text-ink-2">{r.label}</span><b>{r.a}</b></div>
            <div className="mt-1 flex h-2 gap-[2px]" role="img" aria-label={`${r.label}: ${m.home.name} ${r.h}, ${m.away.name} ${r.a}`}>
              <div className="rounded-l" style={{ width: `${(r.h / total) * 100}%`, background: "var(--series-1)" }} />
              <div className="rounded-r" style={{ width: `${(r.a / total) * 100}%`, background: "var(--series-3)" }} />
            </div>
          </div>
        );
      })}
      <p className="text-xs text-muted"><span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle" style={{ background: "var(--series-1)" }} />{m.home.name} · <span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle" style={{ background: "var(--series-3)" }} />{m.away.name}
        {live?.updated_at && <> · actualizado {new Date(live.updated_at).toLocaleTimeString("es-EC", { hour: "2-digit", minute: "2-digit" })}</>}</p>
    </div>
  );
}
