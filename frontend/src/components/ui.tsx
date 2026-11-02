import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Info, Loader2, XCircle } from "lucide-react";
import type { ReactNode } from "react";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

export function Card({ children, className, title, action }: { children: ReactNode; className?: string; title?: string; action?: ReactNode }) {
  return (
    <section className={clsx("card min-w-0 p-4 sm:p-5", className)}>
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-base font-semibold">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Spinner({ label = "Cargando…" }: { label?: string }) {
  return <div className="flex items-center gap-2 p-6 text-sm text-ink-2"><Loader2 className="h-4 w-4 animate-spin" />{label}</div>;
}

export function ErrorBox({ error }: { error: unknown }) {
  return (
    <div role="alert" className="flex items-start gap-2 rounded-xl border border-line bg-surface-2 p-3 text-sm">
      <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
      <span>{error instanceof Error ? error.message : "Se produjo un error"}</span>
    </div>
  );
}

export function Empty({ icon, title, text, action }: { icon?: ReactNode; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      <div className="text-3xl text-muted">{icon ?? <Info className="h-8 w-8" />}</div>
      <p className="font-medium">{title}</p>
      {text && <p className="max-w-md text-sm text-ink-2">{text}</p>}
      {action}
    </div>
  );
}

type Tone = "good" | "warn" | "bad" | "neutral" | "live" | "brand";
export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  const tones: Record<Tone, string> = {
    good: "border-good/40 text-ink", warn: "border-warn/60 text-ink", bad: "border-bad/50 text-ink",
    neutral: "border-line text-ink-2", live: "border-live bg-live text-white", brand: "border-brand/40 text-ink",
  };
  return <span className={clsx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", tones[tone], className)}>{children}</span>;
}

/** Estado siempre con icono + texto (nunca solo color). */
export function StatusBadge({ kind, children }: { kind: "good" | "warn" | "bad"; children: ReactNode }) {
  const Icon = kind === "good" ? CheckCircle2 : kind === "warn" ? AlertTriangle : XCircle;
  const color = kind === "good" ? "text-good" : kind === "warn" ? "text-warn" : "text-bad";
  return <Badge tone={kind}><Icon className={clsx("h-3.5 w-3.5", color)} />{children}</Badge>;
}

export function LiveDot() {
  return <span className="relative inline-flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-live opacity-60" /><span className="relative inline-flex h-2 w-2 rounded-full bg-live" /></span>;
}

export function Tabs<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[] }) {
  return (
    <div role="tablist" className="inline-flex max-w-full gap-1 overflow-x-auto rounded-xl border border-line bg-surface p-1">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={clsx("min-h-[36px] whitespace-nowrap rounded-lg px-3 text-sm font-medium", value === o.value ? "bg-brand text-brand-ink" : "text-ink-2 hover:bg-surface-2")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-2">{hint}</p>}
    </div>
  );
}
