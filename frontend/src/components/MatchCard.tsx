import clsx from "clsx";
import { Link } from "react-router-dom";
import { SPORT_EMOJI, fmtDate, statusText } from "../lib/format";
import type { Match } from "../lib/types";
import { LiveDot } from "./ui";

function TeamRow({ name, logo, score, bold }: { name: string; logo: string | null; score: number | null; bold: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-2">
        {logo ? <img src={logo} alt="" className="h-5 w-5 shrink-0 object-contain" loading="lazy" /> : <span className="h-5 w-5 shrink-0 rounded-full bg-surface-2" />}
        <span className={clsx("truncate", bold && "font-semibold")}>{name}</span>
      </div>
      <span className={clsx("tabular-nums text-lg", bold ? "font-semibold" : "text-ink-2")}>{score ?? ""}</span>
    </div>
  );
}

export function MatchCard({ m, extra }: { m: Match; extra?: React.ReactNode }) {
  const hs = m.home_score ?? -1, as = m.away_score ?? -1;
  const done = m.status === "finished";
  return (
    <Link to={`/matches/${m.id}`} className="card block p-4 transition hover:border-brand/50 focus:outline-none focus:ring-2 focus:ring-brand">
      <div className="mb-3 flex items-center justify-between gap-2 text-xs text-ink-2">
        <span className="truncate">{SPORT_EMOJI[m.sport]} {m.competition?.name ?? "—"}</span>
        <span className={clsx("flex shrink-0 items-center gap-1.5 font-medium", m.status === "live" && "text-live")}>
          {m.status === "live" && <LiveDot />}
          {m.status === "scheduled" ? `${fmtDate(m.start_time)} · ${statusText(m)}` : statusText(m)}
        </span>
      </div>
      <div className="space-y-1.5">
        <TeamRow name={m.home.name} logo={m.home.logo_url} score={m.home_score} bold={done && hs > as} />
        <TeamRow name={m.away.name} logo={m.away.logo_url} score={m.away_score} bold={done && as > hs} />
      </div>
      {extra && <div className="mt-3 border-t border-line pt-3">{extra}</div>}
    </Link>
  );
}
