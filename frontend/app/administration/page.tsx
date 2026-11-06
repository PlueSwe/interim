"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  Badge,
  Button,
  Card,
  Caveat,
  Empty,
  ErrorBox,
  ExternalLink,
  Field,
  Input,
  Kpi,
  Note,
  PageHeader,
  Select,
  Spinner,
  Table,
  Td,
  Textarea,
  Th,
} from "@/components/ui";
import { api } from "@/lib/api";
import {
  ACCESS_TEXT,
  RUN_STATUS_TEXT,
  SOURCE_STATUS_TEXT,
  VERIFIERING,
  visaDatumTid,
  visaTal,
} from "@/lib/format";
import type { Profile, Run, Source } from "@/lib/types";
import { useAction, useApi } from "@/lib/useApi";

type Flik = "kallor" | "korningar" | "profil" | "regler" | "import" | "radata" | "logg";

const FLIKAR: Array<[Flik, string]> = [
  ["kallor", "Källor"],
  ["korningar", "Körningar"],
  ["profil", "Konsultprofil"],
  ["regler", "Exkluderingsregler"],
  ["import", "Manuell import"],
  ["radata", "Rådata"],
  ["logg", "Revisionslogg"],
];

// --- Källor ----------------------------------------------------------------

interface InsamlingsResultat {
  source: string;
  status: string;
  skipped: boolean;
  skip_reason: string | null;
  found: number;
  new: number;
  changed: number;
  duplicate: number;
  irrelevant: number;
  excluded: number;
  review_required: number;
  errors: number;
  notes: string[];
}

function Kallor() {
  const { data, fel, laddar, ladda } = useApi<Source[]>("/admin/sources");
  const tackning = useApi<{
    authorities: Record<string, number | string>;
    sources: {
      total: number;
      automatic: number;
      manual_only: number;
      blocked: number;
      active: number;
      failing: string[];
    };
  }>("/admin/coverage");
  const { kor, arbetar } = useAction();
  const [resultat, setResultat] = useState<InsamlingsResultat | null>(null);

  if (fel) return <ErrorBox error={fel} onRetry={ladda} />;
  if (laddar || !data) return <Spinner />;

  return (
    <>
      {tackning.data && (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
          <Kpi label="Källor i registret" value={visaTal(tackning.data.sources.total)} />
          <Kpi
            label="Automatiska"
            value={visaTal(tackning.data.sources.automatic)}
            hint="Öppet API eller publik sida"
          />
          <Kpi
            label="Endast manuella"
            value={visaTal(tackning.data.sources.manual_only)}
            tone="review"
            hint="Användarvillkoren tillåter ingen insamling"
          />
          <Kpi
            label="Blockerade"
            value={visaTal(tackning.data.sources.blocked)}
            tone="excluded"
            hint="robots.txt tillåter inte hämtning"
          />
          <Kpi label="Aktiva nu" value={visaTal(tackning.data.sources.active)} />
        </div>
      )}

      <div className="mb-4">
        <Note>
          Källor som inte får hämtas står kvar i registret med skälet angivet. Att dölja dem skulle
          se ut som full täckning. Samlar systemet in något olagligt är det ett fel – inte en
          funktion.
        </Note>
      </div>

      {resultat && (
        <div className="mb-4">
          <Card title={`Körning: ${resultat.source}`}>
            <div className="space-y-2 p-5 text-[0.875rem]">
              {resultat.skipped ? (
                <Caveat>Hoppades över: {resultat.skip_reason}</Caveat>
              ) : (
                <p>
                  <Badge tone={resultat.errors > 0 ? "review" : "pass"}>{resultat.status}</Badge>{" "}
                  {resultat.found} hittade · {resultat.new} nya · {resultat.changed} ändrade ·{" "}
                  {resultat.duplicate} dubletter · {resultat.irrelevant} ej relevanta ·{" "}
                  {resultat.excluded} exkluderade · {resultat.review_required} till granskning ·{" "}
                  {resultat.errors} fel
                </p>
              )}
              {resultat.notes.length > 0 && (
                <ul className="space-y-0.5 text-[0.8125rem] text-muted">
                  {resultat.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        </div>
      )}

      <Card title={`${data.length} källor`} description="En adapter per källa, med sitt rättsliga läge">
        <Table>
          <thead>
            <tr>
              <Th>Källa</Th>
              <Th className="w-40">Åtkomstläge</Th>
              <Th className="w-32">Status</Th>
              <Th className="w-28">robots.txt</Th>
              <Th className="w-44">Senast lyckad</Th>
              <Th>Anmärkning</Th>
              <Th className="w-28" />
            </tr>
          </thead>
          <tbody>
            {data.map((k) => {
              const korbar = k.access_mode === "OPEN_API" || k.access_mode === "PUBLIC_HTML";
              return (
                <tr key={k.key} className="hover:bg-surface">
                  <Td>
                    <span className="font-medium">{k.name}</span>
                    <p className="mt-0.5 font-mono text-[0.75rem] text-muted">{k.key}</p>
                    {k.base_url && (
                      <p className="mt-0.5 text-[0.75rem]">
                        <ExternalLink href={k.base_url}>{k.base_url}</ExternalLink>
                      </p>
                    )}
                  </Td>
                  <Td>
                    <Badge
                      tone={
                        k.access_mode === "BLOCKED"
                          ? "excluded"
                          : k.access_mode === "MANUAL_ONLY"
                            ? "review"
                            : "pass"
                      }
                    >
                      {ACCESS_TEXT[k.access_mode]}
                    </Badge>
                  </Td>
                  <Td>
                    <Badge
                      tone={
                        k.status === "ACTIVE"
                          ? "pass"
                          : k.status === "FAILING" || k.status === "BLOCKED"
                            ? "excluded"
                            : "neutral"
                      }
                    >
                      {SOURCE_STATUS_TEXT[k.status]}
                    </Badge>
                    {k.consecutive_failures > 0 && (
                      <p className="mt-0.5 text-[0.75rem] text-excluded">
                        {k.consecutive_failures} fel i rad
                      </p>
                    )}
                  </Td>
                  <Td className="text-[0.8125rem]">
                    {k.robots_allows === null ? (
                      <span className="text-muted">ej kontrollerad</span>
                    ) : k.robots_allows ? (
                      <span className="text-pass">tillåter</span>
                    ) : (
                      <span className="text-excluded">nekar</span>
                    )}
                    {k.robots_checked_at && (
                      <p className="text-[0.75rem] text-muted">{k.robots_checked_at}</p>
                    )}
                  </Td>
                  <Td className="whitespace-nowrap text-[0.8125rem] text-muted">
                    {visaDatumTid(k.last_success_at)}
                    {k.last_error && (
                      <p className="mt-0.5 max-w-xs truncate text-excluded" title={k.last_error}>
                        {k.last_error}
                      </p>
                    )}
                  </Td>
                  <Td className="text-[0.8125rem] leading-relaxed text-muted">
                    {k.legal_note ?? "–"}
                  </Td>
                  <Td>
                    {korbar && (
                      <Button
                        disabled={arbetar}
                        onClick={async () => {
                          const r = await kor(() =>
                            api.post<InsamlingsResultat>(`/admin/sources/${k.key}/collect`),
                          );
                          if (r) setResultat(r);
                          ladda();
                        }}
                      >
                        Hämta nu
                      </Button>
                    )}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </Card>
    </>
  );
}

// --- Körningar -------------------------------------------------------------

function Korningar() {
  const { data, fel, laddar, ladda } = useApi<Run[]>("/admin/runs", { limit: 100 });

  if (fel) return <ErrorBox error={fel} onRetry={ladda} />;
  if (laddar || !data) return <Spinner />;

  return (
    <Card
      title="Senaste körningar"
      description="En insamling som inte hittade något ska se ut som det. En som misslyckades likaså."
    >
      <Table>
        <thead>
          <tr>
            <Th>Källa</Th>
            <Th className="w-28">Status</Th>
            <Th className="w-44">Startad</Th>
            <Th className="w-20">Hittade</Th>
            <Th className="w-16">Nya</Th>
            <Th className="w-20">Ändrade</Th>
            <Th className="w-24">Dubletter</Th>
            <Th className="w-16">Fel</Th>
            <Th>Felmeddelande</Th>
          </tr>
        </thead>
        <tbody>
          {data.length === 0 && <Empty colSpan={9}>Inga körningar har gjorts</Empty>}
          {data.map((k) => (
            <tr key={k.id} className="hover:bg-surface">
              <Td className="font-mono text-[0.8125rem]">{k.source_key}</Td>
              <Td>
                <Badge
                  tone={
                    k.status === "SUCCESS"
                      ? "pass"
                      : k.status === "SKIPPED"
                        ? "neutral"
                        : k.errors > 0 || k.status === "FAILED"
                          ? "excluded"
                          : "review"
                  }
                >
                  {RUN_STATUS_TEXT[k.status as keyof typeof RUN_STATUS_TEXT] ?? k.status}
                </Badge>
              </Td>
              <Td className="whitespace-nowrap text-muted">{visaDatumTid(k.started_at)}</Td>
              <Td className="font-mono tabular-nums">{k.items_found}</Td>
              <Td className="font-mono tabular-nums">{k.items_new}</Td>
              <Td className="font-mono tabular-nums">{k.items_changed}</Td>
              <Td className="font-mono tabular-nums">{k.items_duplicate}</Td>
              <Td className="font-mono tabular-nums">{k.errors}</Td>
              <Td className="max-w-sm text-[0.8125rem] text-excluded">{k.error_detail ?? "–"}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

// --- Konsultprofil ---------------------------------------------------------

const VIKT_ETIKETT: Record<string, string> = {
  role: "Roll och ansvar",
  leadership: "Ledarerfarenhet",
  public_sector: "Offentlig sektor",
  it: "IT-kompetens",
  change: "Förändringsledning",
  geography: "Geografi",
  duration: "Uppdragets längd",
  fee: "Arvode",
};

function Profilen() {
  const { data, fel, laddar, ladda } = useApi<Profile>("/admin/profile");
  const { kor, arbetar, fel: sparfel } = useAction();
  const [vikter, setVikter] = useState<Record<string, number> | null>(null);
  const [rubrik, setRubrik] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setVikter(data.weights ?? {});
      setRubrik(data.headline ?? "");
    }
  }, [data]);

  if (fel) return <ErrorBox error={fel} onRetry={ladda} />;
  if (laddar || !data || vikter === null) return <Spinner />;

  const summa = Object.values(vikter).reduce((a, b) => a + b, 0);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card
        title="Viktning"
        description="Poängen räknas om för alla uppdrag när vikterna ändras. Ingen vikt får vara noll."
      >
        <div className="space-y-3 p-5">
          {Object.entries(vikter).map(([nyckel, v]) => (
            <Field key={nyckel} label={VIKT_ETIKETT[nyckel] ?? nyckel}>
              <Input
                type="number"
                min={1}
                max={100}
                value={v}
                onChange={(e) =>
                  setVikter({ ...vikter, [nyckel]: Number(e.target.value) })
                }
              />
            </Field>
          ))}
          <p className="text-[0.8125rem] text-muted">
            Summa: <span className="font-mono tabular-nums">{summa}</span>
            {summa !== 100 && (
              <span className="ml-2 text-review">
                avviker från 100 – poängen normaliseras men blir svårare att jämföra
              </span>
            )}
          </p>
          {sparfel && <ErrorBox error={sparfel} />}
          <Button
            variant="primary"
            disabled={arbetar}
            onClick={async () => {
              const ok = await kor(() => api.patch("/admin/profile", { weights: vikter }));
              if (ok) ladda();
            }}
          >
            Spara viktning
          </Button>
        </div>
      </Card>

      <Card title="Profil" description="Underlaget som uppdragen matchas mot">
        <div className="space-y-3 p-5">
          <Field label="Rubrik">
            <Textarea
              rows={3}
              value={rubrik ?? ""}
              onChange={(e) => setRubrik(e.target.value)}
            />
          </Field>
          <Button
            disabled={arbetar}
            onClick={async () => {
              const ok = await kor(() => api.patch("/admin/profile", { headline: rubrik }));
              if (ok) ladda();
            }}
          >
            Spara rubrik
          </Button>

          <div className="border-t border-line pt-3">
            <p className="mb-2 text-[0.75rem] font-medium uppercase tracking-wide text-muted">
              Erfarenhet ({data.experiences?.length ?? 0} poster)
            </p>
            <ul className="space-y-1 text-[0.875rem]">
              {(data.experiences ?? []).map((e, i) => (
                <li key={i} className="text-ink">
                  {String((e as Record<string, unknown>).role ?? "")}
                  {(e as Record<string, unknown>).organisation
                    ? ` – ${String((e as Record<string, unknown>).organisation)}`
                    : ""}
                </li>
              ))}
            </ul>
          </div>

          <div className="border-t border-line pt-3">
            <p className="mb-2 text-[0.75rem] font-medium uppercase tracking-wide text-muted">
              Kompetens ({data.skills?.length ?? 0})
            </p>
            <div className="flex flex-wrap gap-1">
              {(data.skills ?? []).map((s) => (
                <Badge key={s}>{s}</Badge>
              ))}
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}

// --- Exkluderingsregler ----------------------------------------------------

interface Regel {
  rule_id: string;
  kind: string;
  description: string;
  pattern: string;
  requires_near: string[];
}

function Regler() {
  const { data, fel, laddar, ladda } = useApi<{
    rules: Regel[];
    verdicts: Record<string, string>;
    verification_levels: Record<string, string>;
    note: string;
  }>("/admin/exclusion-rules");

  if (fel) return <ErrorBox error={fel} onRetry={ladda} />;
  if (laddar || !data) return <Spinner />;

  const grupper: Array<[string, string]> = [
    ["EXCLUDE", "Exkluderar"],
    ["AMBIGUOUS", "Kräver granskning"],
    ["BENIGN", "Exkluderar aldrig"],
  ];

  return (
    <div className="space-y-4">
      <Card title="Bedömningar">
        <dl className="divide-y divide-line">
          {Object.entries(data.verdicts).map(([v, t]) => (
            <div key={v} className="flex items-start gap-4 px-5 py-2.5 text-[0.875rem]">
              <dt className="w-40 shrink-0 font-mono text-[0.8125rem]">{v}</dt>
              <dd className="text-muted">{t}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card
        title="Verifieringsnivåer för tillsättningar"
        description="Bara nivå 1–3 räknas som verifierat"
      >
        <dl className="divide-y divide-line">
          {Object.entries(data.verification_levels).map(([n, t]) => (
            <div key={n} className="flex items-start gap-4 px-5 py-2.5 text-[0.875rem]">
              <dt className="w-10 shrink-0 font-mono">{n}</dt>
              <dd className="flex-1">{t}</dd>
              <dd>
                {VERIFIERING[Number(n)]?.racker ? (
                  <Badge tone="pass">räcker</Badge>
                ) : (
                  <Badge tone="review">räcker inte</Badge>
                )}
              </dd>
            </div>
          ))}
        </dl>
      </Card>

      <div>
        <Note>{data.note}</Note>
      </div>

      {grupper.map(([typ, titel]) => {
        const regler = data.rules.filter((r) => r.kind === typ);
        return (
          <Card key={typ} title={`${titel} (${regler.length})`}>
            <Table>
              <thead>
                <tr>
                  <Th className="w-56">Regel</Th>
                  <Th>Beskrivning</Th>
                  <Th>Mönster</Th>
                  <Th className="w-48">Kräver närliggande ord</Th>
                </tr>
              </thead>
              <tbody>
                {regler.map((r) => (
                  <tr key={r.rule_id}>
                    <Td className="font-mono text-[0.8125rem]">{r.rule_id}</Td>
                    <Td className="text-[0.875rem]">{r.description}</Td>
                    <Td className="max-w-md break-all font-mono text-[0.75rem] text-muted">
                      {r.pattern}
                    </Td>
                    <Td className="text-[0.8125rem] text-muted">
                      {r.requires_near.length > 0 ? r.requires_near.join(", ") : "–"}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        );
      })}
    </div>
  );
}

// --- Manuell import --------------------------------------------------------

function Import() {
  const { kor, arbetar, fel } = useAction();
  const [innehall, setInnehall] = useState("");
  const [filnamn, setFilnamn] = useState("");
  const [resultat, setResultat] = useState<Record<string, unknown> | null>(null);

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Card
        title="Importera annonser"
        description="CSV eller JSON. För källor vars användarvillkor inte tillåter automatisk insamling."
      >
        <div className="space-y-3 p-5">
          <Field label="Filnamn (valfritt)">
            <Input
              value={filnamn}
              onChange={(e) => setFilnamn(e.target.value)}
              placeholder="t.ex. mercell-export-2026-11.csv"
            />
          </Field>
          <Field
            label="Innehåll"
            hint="Svenska eller engelska kolumnnamn fungerar. Okända kolumner sparas men används inte."
          >
            <Textarea
              rows={14}
              value={innehall}
              onChange={(e) => setInnehall(e.target.value)}
              placeholder={
                "titel;organisation;orgnr;beskrivning;sista ansökningsdag;kommun\n" +
                "Interim IT-chef;Exempelmyndigheten;202100-0000;...;2026-12-31;Stockholm"
              }
            />
          </Field>
          {fel && <ErrorBox error={fel} />}
          <Button
            variant="primary"
            disabled={arbetar || innehall.trim().length === 0}
            onClick={async () => {
              const r = await kor(() =>
                api.post<Record<string, unknown>>("/admin/import", {
                  content: innehall,
                  filename: filnamn || null,
                }),
              );
              if (r) setResultat(r);
            }}
          >
            Importera
          </Button>
        </div>
      </Card>

      <div className="space-y-4">
        <Card title="Resultat">
          <div className="p-5">
            {resultat === null ? (
              <Note>Ingen import har gjorts i denna session.</Note>
            ) : (
              <dl className="space-y-1.5 text-[0.875rem]">
                {Object.entries(resultat).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4">
                    <dt className="text-muted">{k}</dt>
                    <dd className="font-mono tabular-nums">
                      {Array.isArray(v) ? v.length : String(v)}
                    </dd>
                  </div>
                ))}
                {Array.isArray(resultat.notes) && (resultat.notes as string[]).length > 0 && (
                  <ul className="mt-3 space-y-0.5 border-t border-line pt-3 text-[0.8125rem] text-muted">
                    {(resultat.notes as string[]).map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                )}
              </dl>
            )}
          </div>
        </Card>

        <Card title="Sekretess">
          <div className="p-5">
            <Note>
              Importen vägrar innehåll som är märkt sekretessbelagt. Underlag som omfattas av
              offentlighets- och sekretesslagen ska inte läggas i det här systemet.
            </Note>
          </div>
        </Card>
      </div>
    </div>
  );
}

// --- Rådata ----------------------------------------------------------------

interface Snapshot {
  id: string;
  source_key: string;
  external_id: string | null;
  url: string | null;
  fetched_at: string;
  http_status: number | null;
  content_type: string | null;
  sha256: string;
  byte_size: number | null;
  integrity_ok: boolean;
  content: string | null;
  truncated: boolean;
}

function Radata({ forvalt }: { forvalt: string | null }) {
  const [id, setId] = useState(forvalt ?? "");
  const [sokt, setSokt] = useState(forvalt ?? "");
  const { data, fel, laddar } = useApi<Snapshot>(sokt ? `/admin/snapshots/${sokt}` : null);

  return (
    <Card
      title="Ögonblicksbild"
      description="Rådatan bakom en uppgift, med kontroll av att innehållet inte ändrats sedan insamlingen"
      action={
        <div className="flex gap-2">
          <Input
            value={id}
            onChange={(e) => setId(e.target.value)}
            placeholder="snapshot-id"
            className="w-80 font-mono text-[0.8125rem]"
          />
          <Button onClick={() => setSokt(id.trim())} disabled={!id.trim()}>
            Visa
          </Button>
        </div>
      }
    >
      <div className="p-5">
        {!sokt ? (
          <Note>
            Ange ett snapshot-id. Du kommer hit via länken “Visa ögonblicksbild” på ett uppdrag.
          </Note>
        ) : fel ? (
          <ErrorBox error={fel} />
        ) : laddar || !data ? (
          <Spinner />
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={data.integrity_ok ? "pass" : "excluded"}>
                {data.integrity_ok ? "sha256 stämmer" : "sha256 STÄMMER INTE"}
              </Badge>
              <Badge>{data.source_key}</Badge>
              {data.http_status && <Badge>HTTP {data.http_status}</Badge>}
              {data.content_type && <Badge>{data.content_type}</Badge>}
              {data.byte_size && <Badge>{visaTal(data.byte_size)} byte</Badge>}
            </div>

            {!data.integrity_ok && (
              <Caveat>
                Innehållet matchar inte den sparade kontrollsumman. Uppgifter som bygger på detta
                snapshot går inte längre att belägga.
              </Caveat>
            )}

            <dl className="grid gap-x-6 gap-y-1 text-[0.875rem] sm:grid-cols-2">
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Hämtad</dt>
                <dd>{visaDatumTid(data.fetched_at)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Id hos källan</dt>
                <dd className="break-all font-mono text-[0.75rem]">{data.external_id ?? "–"}</dd>
              </div>
              <div className="col-span-full flex justify-between gap-2">
                <dt className="text-muted">sha256</dt>
                <dd className="break-all font-mono text-[0.75rem]">{data.sha256}</dd>
              </div>
              {data.url && (
                <div className="col-span-full flex justify-between gap-2">
                  <dt className="text-muted">Adress</dt>
                  <dd className="break-all">
                    <ExternalLink href={data.url}>{data.url}</ExternalLink>
                  </dd>
                </div>
              )}
            </dl>

            <div>
              <p className="mb-1 text-[0.75rem] uppercase tracking-wide text-muted">
                Innehåll{data.truncated && " (avkortat)"}
              </p>
              <pre className="max-h-[32rem] overflow-auto rounded border border-line bg-surface p-3 font-mono text-[0.75rem] leading-relaxed">
                {data.content ?? "– ingen fil sparad –"}
              </pre>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

// --- Revisionslogg ---------------------------------------------------------

interface LoggRad {
  at: string;
  user: string | null;
  action: string;
  object_type: string;
  object_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
}

function Logg() {
  const { data, fel, laddar, ladda } = useApi<LoggRad[]>("/admin/audit", { limit: 200 });

  if (fel) return <ErrorBox error={fel} onRetry={ladda} />;
  if (laddar || !data) return <Spinner />;

  return (
    <Card
      title="Revisionslogg"
      description="Varje manuell ändring som påverkar ett beslut, med före- och efterläge"
    >
      <Table>
        <thead>
          <tr>
            <Th className="w-44">Tid</Th>
            <Th className="w-48">Användare</Th>
            <Th className="w-48">Åtgärd</Th>
            <Th>Före</Th>
            <Th>Efter</Th>
          </tr>
        </thead>
        <tbody>
          {data.length === 0 && <Empty colSpan={5}>Inga ändringar loggade</Empty>}
          {data.map((r, i) => (
            <tr key={i} className="hover:bg-surface">
              <Td className="whitespace-nowrap text-muted">{visaDatumTid(r.at)}</Td>
              <Td className="text-[0.8125rem]">
                {r.user ?? "–"}
                {r.ip && <p className="font-mono text-[0.6875rem] text-muted">{r.ip}</p>}
              </Td>
              <Td>
                <span className="font-mono text-[0.8125rem]">{r.action}</span>
                <p className="mt-0.5 text-[0.75rem] text-muted">{r.object_type}</p>
              </Td>
              <Td>
                {r.before ? (
                  <pre className="max-w-xs overflow-x-auto font-mono text-[0.6875rem] text-muted">
                    {JSON.stringify(r.before, null, 1)}
                  </pre>
                ) : (
                  <span className="text-muted">–</span>
                )}
              </Td>
              <Td>
                {r.after ? (
                  <pre className="max-w-xs overflow-x-auto font-mono text-[0.6875rem] text-muted">
                    {JSON.stringify(r.after, null, 1)}
                  </pre>
                ) : (
                  <span className="text-muted">–</span>
                )}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

// --- Sidan -----------------------------------------------------------------

function Innehall() {
  const params = useSearchParams();
  const snapshot = params.get("snapshot");
  const [flik, setFlik] = useState<Flik>(snapshot ? "radata" : "kallor");

  return (
    <>
      <PageHeader
        title="Administration"
        description="Källornas rättsliga läge, insamlingarnas utfall, matchningens vikter och spåret från uppgift till rådata."
      />

      <div className="mb-4 flex flex-wrap gap-1 border-b border-line">
        {FLIKAR.map(([v, t]) => (
          <button
            key={v}
            onClick={() => setFlik(v)}
            className={
              flik === v
                ? "-mb-px border-b-2 border-accent px-3 py-2 text-[0.875rem] font-medium text-accent"
                : "-mb-px border-b-2 border-transparent px-3 py-2 text-[0.875rem] text-muted hover:text-ink"
            }
          >
            {t}
          </button>
        ))}
      </div>

      {flik === "kallor" && <Kallor />}
      {flik === "korningar" && <Korningar />}
      {flik === "profil" && <Profilen />}
      {flik === "regler" && <Regler />}
      {flik === "import" && <Import />}
      {flik === "radata" && <Radata forvalt={snapshot} />}
      {flik === "logg" && <Logg />}
    </>
  );
}

export default function Administration() {
  return (
    <Suspense fallback={<Spinner />}>
      <Innehall />
    </Suspense>
  );
}
