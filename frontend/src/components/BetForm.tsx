import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { outcomeLabel } from "../lib/format";
import type { Match } from "../lib/types";
import { ErrorBox } from "./ui";

const MARKETS: Record<string, { label: string; options: string[] }> = {
  "1x2": { label: "Resultado (1X2)", options: ["home", "draw", "away"] },
  "over_under_2.5": { label: "Más/Menos 2,5 goles", options: ["over", "under"] },
  btts: { label: "Ambos marcan", options: ["yes", "no"] },
  other: { label: "Otro (córners, tarjetas, hándicap…)", options: [] },
};
const BOOKMAKERS = ["Ecuabet", "Betcris", "Bet593", "Doradobet", "Otra"];

function remember(k: string, v?: string) {
  try { if (v === undefined) return localStorage.getItem(k) ?? ""; localStorage.setItem(k, v); } catch { /* sin almacenamiento */ }
  return "";
}

/** Registrar una apuesta hecha en la casa de apuestas (la plataforma no acepta apuestas). */
export function BetForm({ match, onDone }: { match?: Match; onDone?: () => void }) {
  const qc = useQueryClient();
  const sportMarkets = match && match.sport !== "football"
    ? { [match.sport === "tennis" ? "match_winner" : "moneyline"]: { label: "Ganador", options: ["home", "away"] }, other: MARKETS.other }
    : MARKETS;
  const first = Object.keys(sportMarkets)[0];
  const [market, setMarket] = useState(match ? first : "other");
  const [selection, setSelection] = useState(sportMarkets[first]?.options[0] ?? "");
  const [odds, setOdds] = useState("");
  const [stake, setStake] = useState(() => remember("sportai.stake") || "");
  const [bookmaker, setBookmaker] = useState(() => remember("sportai.bookmaker") || "Ecuabet");
  const [description, setDescription] = useState("");
  const [note, setNote] = useState("");
  const [ok, setOk] = useState(false);
  const save = useMutation({
    mutationFn: () => api("/bets", { method: "POST", body: {
      match_id: market === "other" && !match ? null : match?.id ?? null, market, selection: selection.trim(),
      odds: Number(odds.replace(",", ".")), stake: Number(stake.replace(",", ".")), bookmaker, note,
      description: description || (match ? `${match.home.name} vs ${match.away.name}` : ""),
    } }),
    onSuccess: () => {
      remember("sportai.stake", stake); remember("sportai.bookmaker", bookmaker);
      setOk(true); setOdds(""); setNote("");
      qc.invalidateQueries({ queryKey: ["bets"] }); onDone?.();
    },
  });
  const opts = sportMarkets[market]?.options ?? [];
  const oddsN = Number(odds.replace(",", ".")), stakeN = Number(stake.replace(",", "."));
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); setOk(false); save.mutate(); }}>
      {!match && (
        <div><label className="label" htmlFor="bdesc">Partido o descripción</label>
          <input id="bdesc" className="input" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Ej.: Barcelona vs Alavés" required /></div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <div><label className="label" htmlFor="bmarket">Mercado</label>
          <select id="bmarket" className="input" value={market} disabled={!match}
            onChange={(e) => { setMarket(e.target.value); setSelection(sportMarkets[e.target.value]?.options[0] ?? ""); }}>
            {Object.entries(sportMarkets).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select></div>
        <div><label className="label" htmlFor="bsel">Tu selección</label>
          {opts.length ? (
            <select id="bsel" className="input" value={selection} onChange={(e) => setSelection(e.target.value)}>
              {opts.map((o) => <option key={o} value={o}>{outcomeLabel(market, o, match)}</option>)}
            </select>
          ) : <input id="bsel" className="input" value={selection} onChange={(e) => setSelection(e.target.value)} placeholder="Ej.: Más de 9,5 córners" required />}
        </div>
        <div><label className="label" htmlFor="bodds">Cuota</label>
          <input id="bodds" className="input" inputMode="decimal" value={odds} onChange={(e) => setOdds(e.target.value)} placeholder="Ej.: 1,85" required /></div>
        <div><label className="label" htmlFor="bstake">Importe apostado (USD)</label>
          <input id="bstake" className="input" inputMode="decimal" value={stake} onChange={(e) => setStake(e.target.value)} placeholder="Ej.: 5" required /></div>
        <div><label className="label" htmlFor="bbook">Casa de apuestas</label>
          <select id="bbook" className="input" value={bookmaker} onChange={(e) => setBookmaker(e.target.value)}>
            {BOOKMAKERS.map((b) => <option key={b}>{b}</option>)}
          </select></div>
        <div><label className="label" htmlFor="bnote">Nota (opcional)</label>
          <input id="bnote" className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Por qué apuestas" /></div>
      </div>
      {oddsN > 1 && stakeN > 0 && <p className="text-sm text-ink-2">Si aciertas cobras <b className="text-ink tabular-nums">{(oddsN * stakeN).toFixed(2)} USD</b> (ganancia {(stakeN * (oddsN - 1)).toFixed(2)}). Probabilidad implícita de la cuota: {(100 / oddsN).toFixed(0)} %.</p>}
      {save.error && <ErrorBox error={save.error} />}
      {ok && <p className="text-sm text-good">✓ Apuesta registrada. Se liquidará sola al terminar el partido.</p>}
      <button className="btn-primary" disabled={save.isPending}>Registrar apuesta</button>
    </form>
  );
}
