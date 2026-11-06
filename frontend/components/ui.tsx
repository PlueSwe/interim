// Grundkomponenter. Handskrivna i stallet for installerade via shadcn-cli,
// eftersom hela behovet ar ett tiotal element och ett generatorsteg da bara
// lagger till en kedja att halla uppdaterad.

"use client";

import clsx from "clsx";
import Link from "next/link";
import type { ReactNode } from "react";

import type { AppointmentStatus, ExclusionVerdict, RequestStatus } from "@/lib/types";
import { REQUEST_TEXT, STATUS_TEXT, VERDICT_TEXT } from "@/lib/format";

// --- Yta -------------------------------------------------------------------

export function Card({
  children,
  className,
  title,
  description,
  action,
}: {
  children?: ReactNode;
  className?: string;
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section
      className={clsx(
        "rounded-lg border border-line bg-white shadow-card",
        className,
      )}
    >
      {(title || action) && (
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-3.5">
          <div>
            {title && <h2 className="text-[0.9375rem] font-semibold text-ink">{title}</h2>}
            {description && <p className="mt-0.5 text-[0.8125rem] text-muted">{description}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        <h1 className="text-[1.375rem] font-semibold tracking-[-0.01em] text-ink">{title}</h1>
        {description && <p className="mt-1 text-[0.875rem] leading-relaxed text-muted">{description}</p>}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}

// --- Knappar och falt ------------------------------------------------------

export function Button({
  children,
  onClick,
  variant = "secondary",
  type = "button",
  disabled,
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  type?: "button" | "submit";
  disabled?: boolean;
  className?: string;
}) {
  const stilar = {
    primary: "bg-accent text-white hover:bg-accent-hover border-transparent",
    secondary: "bg-white text-ink hover:bg-surface border-line",
    danger: "bg-white text-excluded hover:bg-excluded-soft border-line",
    ghost: "bg-transparent text-muted hover:text-ink hover:bg-surface border-transparent",
  }[variant];

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-[0.8125rem] font-medium",
        "transition-colors disabled:cursor-not-allowed disabled:opacity-45",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        stilar,
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[0.75rem] font-medium uppercase tracking-wide text-muted">
        {label}
      </span>
      {children}
      {hint && <span className="mt-1 block text-[0.75rem] text-muted">{hint}</span>}
    </label>
  );
}

const faltklasser =
  "w-full rounded-md border border-line bg-white px-2.5 py-1.5 text-[0.875rem] text-ink " +
  "placeholder:text-muted/70 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={clsx(faltklasser, props.className)} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea {...props} className={clsx(faltklasser, "font-mono text-[0.8125rem]", props.className)} />
  );
}

export function Select({
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <select {...props} className={clsx(faltklasser, props.className)}>
      {children}
    </select>
  );
}

// --- Markorer --------------------------------------------------------------

export function Badge({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "pass" | "review" | "excluded" | "accent";
  title?: string;
}) {
  const stilar = {
    neutral: "bg-surface text-muted border-line",
    pass: "bg-pass-soft text-pass border-pass/20",
    review: "bg-review-soft text-review border-review/20",
    excluded: "bg-excluded-soft text-excluded border-excluded/20",
    accent: "bg-accent-soft text-accent border-accent/20",
  }[tone];
  return (
    <span
      title={title}
      className={clsx(
        "inline-flex items-center whitespace-nowrap rounded border px-1.5 py-0.5 text-[0.6875rem] font-medium",
        stilar,
      )}
    >
      {children}
    </span>
  );
}

export function VerdictBadge({ verdict }: { verdict: ExclusionVerdict }) {
  const tone = verdict === "PASS" ? "pass" : verdict === "EXCLUDED" ? "excluded" : "review";
  return <Badge tone={tone}>{VERDICT_TEXT[verdict]}</Badge>;
}

export function StatusBadge({ status }: { status: AppointmentStatus }) {
  // Fargen foljer om arendet ar avgjort, vantar pa oss, eller vantar pa nagon
  // annan. Det ar den skillnad man behover se i en lista.
  const tone =
    status === "APPOINTMENT_VERIFIED"
      ? "pass"
      : status === "CLOSED_UNRESOLVED" || status === "POSITION_CANCELLED"
        ? "neutral"
        : status === "REQUEST_READY" || status === "APPOINTMENT_IDENTIFIED"
          ? "review"
          : "accent";
  return <Badge tone={tone}>{STATUS_TEXT[status]}</Badge>;
}

export function RequestBadge({ status }: { status: RequestStatus }) {
  const tone =
    status === "SENT" || status === "ANSWERED"
      ? "pass"
      : status === "DRAFT"
        ? "review"
        : status === "REFUSED" || status === "ABANDONED"
          ? "excluded"
          : "accent";
  return <Badge tone={tone}>{REQUEST_TEXT[status]}</Badge>;
}

/** Poang 0-100. Fargen ar avsiktligt dampad: siffran ar en uppskattning. */
export function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) {
    return (
      <span className="text-[0.8125rem] text-muted" title="Ingen poäng sätts på ett exkluderat uppdrag">
        –
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-2">
      <span className="w-10 text-right font-mono text-[0.875rem] font-medium tabular-nums text-ink">
        {score}
      </span>
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-line" aria-hidden>
        <span
          className={clsx(
            "block h-full rounded-full",
            score >= 80 ? "bg-accent" : score >= 60 ? "bg-accent/60" : "bg-muted/40",
          )}
          style={{ width: `${score}%` }}
        />
      </span>
    </span>
  );
}

// --- Tabell ----------------------------------------------------------------

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[0.875rem]">{children}</table>
    </div>
  );
}

export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <th
      className={clsx(
        "border-b border-line bg-surface px-4 py-2 text-left text-[0.75rem] font-semibold uppercase tracking-wide text-muted",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  className,
  colSpan,
  title,
}: {
  children?: ReactNode;
  className?: string;
  colSpan?: number;
  title?: string;
}) {
  return (
    <td
      colSpan={colSpan}
      title={title}
      className={clsx("border-b border-line px-4 py-2.5 align-top", className)}
    >
      {children}
    </td>
  );
}

export function Empty({ children, colSpan }: { children: ReactNode; colSpan: number }) {
  return (
    <tr>
      <Td colSpan={colSpan} className="py-10 text-center text-[0.875rem] text-muted">
        {children}
      </Td>
    </tr>
  );
}

// --- Tillstand -------------------------------------------------------------

export function Spinner({ label = "Hämtar…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 px-5 py-10 text-[0.875rem] text-muted">
      <span
        className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line border-t-accent"
        aria-hidden
      />
      {label}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-excluded/25 bg-excluded-soft px-4 py-3">
      <p className="text-[0.875rem] font-medium text-excluded">Anropet misslyckades</p>
      <p className="mt-0.5 text-[0.8125rem] text-ink">{error}</p>
      {onRetry && (
        <div className="mt-2">
          <Button onClick={onRetry}>Försök igen</Button>
        </div>
      )}
    </div>
  );
}

/** Ruta for en uppgift som inte ar belagd. Anvands dar det vore latt att tro
 *  att systemet vet mer an det gor. */
export function Caveat({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md border border-review/25 bg-review-soft px-3 py-2 text-[0.8125rem] leading-relaxed text-review">
      {children}
    </p>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md border border-line bg-surface px-3 py-2 text-[0.8125rem] leading-relaxed text-muted">
      {children}
    </p>
  );
}

// --- Ovrigt ----------------------------------------------------------------

export function Kpi({
  label,
  value,
  hint,
  href,
  tone,
}: {
  label: string;
  value: number | string;
  hint?: string;
  href?: string;
  tone?: "pass" | "review" | "excluded";
}) {
  const inre = (
    <>
      <p className="text-[0.75rem] font-medium uppercase tracking-wide text-muted">{label}</p>
      <p
        className={clsx(
          "mt-1.5 font-mono text-[1.75rem] font-semibold leading-none tabular-nums",
          tone === "review" ? "text-review" : tone === "excluded" ? "text-excluded" : "text-ink",
        )}
      >
        {value}
      </p>
      {hint && <p className="mt-1.5 text-[0.75rem] leading-snug text-muted">{hint}</p>}
    </>
  );
  const klass =
    "block rounded-lg border border-line bg-white px-4 py-3.5 shadow-card transition-colors";
  return href ? (
    <Link href={href} className={clsx(klass, "hover:border-accent/40 hover:bg-accent-soft/40")}>
      {inre}
    </Link>
  ) : (
    <div className={klass}>{inre}</div>
  );
}

export function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="text-accent underline decoration-accent/30 underline-offset-2 hover:decoration-accent"
    >
      {children}
    </a>
  );
}

export function Pagination({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  const sida = Math.floor(offset / limit) + 1;
  const sidor = Math.ceil(total / limit);
  return (
    <div className="flex items-center justify-between border-t border-line px-5 py-3 text-[0.8125rem] text-muted">
      <span>
        {offset + 1}–{Math.min(offset + limit, total)} av {total}
      </span>
      <div className="flex items-center gap-2">
        <Button disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          Föregående
        </Button>
        <span className="tabular-nums">
          {sida} / {sidor}
        </span>
        <Button disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
          Nästa
        </Button>
      </div>
    </div>
  );
}
