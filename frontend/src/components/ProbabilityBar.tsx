import { outcomeLabel, pct } from "../lib/format";
import type { Match } from "../lib/types";

const ORDER = ["home", "draw", "away", "over", "under", "yes", "no"];
const COLOR: Record<string, string> = { home: "var(--series-1)", draw: "var(--series-2)", away: "var(--series-3)",
  over: "var(--series-1)", under: "var(--series-3)", yes: "var(--series-1)", no: "var(--series-3)" };

/** Barra apilada de probabilidades: color por resultado (fijo), etiqueta directa con texto. */
export function ProbabilityBar({ probabilities, market, match, pick }: { probabilities: Record<string, number>; market: string; match?: Match; pick?: string }) {
  const keys = Object.keys(probabilities).sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b));
  return (
    <div>
      <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded" role="img"
        aria-label={keys.map((k) => `${outcomeLabel(market, k, match)} ${pct(probabilities[k])}`).join(", ")}>
        {keys.map((k) => (
          <div key={k} title={`${outcomeLabel(market, k, match)}: ${pct(probabilities[k], 1)}`}
            style={{ width: `${probabilities[k] * 100}%`, background: COLOR[k] }} className="first:rounded-l last:rounded-r" />
        ))}
      </div>
      <div className="mt-2 grid gap-1 text-sm" style={{ gridTemplateColumns: `repeat(${keys.length}, minmax(0, 1fr))` }}>
        {keys.map((k) => (
          <div key={k} className={k === pick ? "font-semibold" : "text-ink-2"}>
            <span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle" style={{ background: COLOR[k] }} />
            <span className="truncate align-middle">{outcomeLabel(market, k, match)}</span>
            <div className="tabular-nums">{pct(probabilities[k])}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
