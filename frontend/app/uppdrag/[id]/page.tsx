"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import {
  Badge,
  Button,
  Card,
  Caveat,
  ErrorBox,
  ExternalLink,
  Field,
  Note,
  PageHeader,
  ScoreBadge,
  Select,
  Spinner,
  Table,
  Td,
  Textarea,
  Th,
  VerdictBadge,
} from "@/components/ui";
import { api } from "@/lib/api";
import {
  EMPLOYMENT_TEXT,
  KIND_TEXT,
  ROLE_TEXT,
  VERDICT_TEXT,
  dagarKvar,
  visaDatum,
  visaDatumTid,
  visaKronor,
} from "@/lib/format";
import type { ExclusionVerdict, OpportunityDetail } from "@/lib/types";
import { useAction, useApi } from "@/lib/useApi";

export default function Uppdragsdetalj() {
  const { id } = useParams<{ id: string }>();
  const { data, fel, laddar, ladda } = useApi<OpportunityDetail>(`/opportunities/${id}`);
  const { kor, arbetar, fel: andringsfel } = useAction();

  const [visaOverprovning, setVisaOverprovning] = useState(false);
  const [nyttBeslut, setNyttBeslut] = useState<ExclusionVerdict>("PASS");
  const [anledning, setAnledning] = useState("");

  async function overprova() {
    const ok = await kor(() =>
      api.post(`/opportunities/${id}/exclusion-override`, {
        verdict: nyttBeslut,
        reason: anledning,
      }),
    );
    if (ok) {
      setVisaOverprovning(false);
      setAnledning("");
      ladda();
    }
  }

  if (fel) return <ErrorBox error={fel} onRetry={ladda} />;
  if (laddar || !data) return <Spinner />;

  const annons = data.job_ad;
  const matchning = data.matching;

  return (
    <>
      <PageHeader
        title={annons?.title ?? "Uppdrag"}
        description={
          <>
            {annons?.organisation_name ?? "Okänd organisation"}
            {annons?.workplace_municipality ? ` · ${annons.workplace_municipality}` : ""}
            {" · "}
            <Badge>{KIND_TEXT[data.kind]}</Badge>
          </>
        }
      >
        {annons?.url && <ExternalLink href={annons.url}>Öppna originalannonsen</ExternalLink>}
      </PageHeader>

      {andringsfel && (
        <div className="mb-4">
          <ErrorBox error={andringsfel} />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          {/* --- Matchning --- */}
          <Card
            title="Matchning"
            description="Poängen är en uppskattning av hur väl annonsen liknar din profil"
          >
            {matchning === null ? (
              <div className="p-5">
                <Note>
                  Ingen poäng är satt. Ett exkluderat uppdrag poängsätts inte – det vore att
                  rangordna något som ändå är uteslutet.
                </Note>
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-6 border-b border-line px-5 py-4">
                  <div>
                    <p className="text-[0.75rem] font-medium uppercase tracking-wide text-muted">
                      Poäng
                    </p>
                    <p className="mt-1 font-mono text-[2rem] font-semibold leading-none tabular-nums text-ink">
                      {matchning.score}
                      <span className="text-[1rem] font-normal text-muted"> / 100</span>
                    </p>
                  </div>
                  {matchning.confidence !== null && (
                    <div>
                      <p className="text-[0.75rem] font-medium uppercase tracking-wide text-muted">
                        Underlag
                      </p>
                      <p className="mt-1 font-mono text-[1.25rem] font-semibold leading-none tabular-nums text-ink">
                        {matchning.confidence} %
                      </p>
                      <p className="mt-0.5 text-[0.75rem] text-muted">
                        andel av vikten som har stöd i annonstexten
                      </p>
                    </div>
                  )}
                </div>

                {matchning.subscores && (
                  <Table>
                    <thead>
                      <tr>
                        <Th>Kriterium</Th>
                        <Th className="w-24">Poäng</Th>
                        <Th>Underlag i texten</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(matchning.subscores).map(([nyckel, k]) => (
                        <tr key={nyckel}>
                          <Td className="whitespace-nowrap font-medium">{k.label}</Td>
                          <Td className="whitespace-nowrap font-mono tabular-nums">
                            {k.points} / {k.weight}
                          </Td>
                          <Td>
                            {k.unknown ? (
                              <span className="text-[0.8125rem] text-review">
                                uppgift saknas i annonsen – räknas som nedre uppskattning
                              </span>
                            ) : k.evidence.length > 0 ? (
                              <ul className="space-y-0.5 text-[0.8125rem] text-muted">
                                {k.evidence.map((b, i) => (
                                  <li key={i}>{b}</li>
                                ))}
                              </ul>
                            ) : (
                              <span className="text-[0.8125rem] text-muted">–</span>
                            )}
                          </Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                )}

                {matchning.explanation && (
                  <div className="border-t border-line px-5 py-4">
                    <p className="mb-2 text-[0.75rem] font-medium uppercase tracking-wide text-muted">
                      Förklaring
                    </p>
                    <pre className="whitespace-pre-wrap font-sans text-[0.8125rem] leading-relaxed text-ink">
                      {matchning.explanation}
                    </pre>
                  </div>
                )}
              </>
            )}
          </Card>

          {/* --- Exkluderingsbedomning --- */}
          <Card
            title="Exkluderingsbedömning"
            description="Uppdrag som kräver säkerhetsprövning, registerkontroll eller motsvarande personkontroll ska inte visas som sökbara"
            action={<VerdictBadge verdict={data.exclusion_status} />}
          >
            {data.exclusion === null ? (
              <div className="p-5">
                <Note>Ingen bedömning finns sparad.</Note>
              </div>
            ) : (
              <div className="space-y-3 p-5">
                <dl className="grid gap-x-6 gap-y-2 text-[0.875rem] sm:grid-cols-2">
                  <div>
                    <dt className="text-[0.75rem] uppercase tracking-wide text-muted">Regel</dt>
                    <dd className="font-mono text-[0.8125rem]">{data.exclusion.rule_id ?? "–"}</dd>
                  </div>
                  <div>
                    <dt className="text-[0.75rem] uppercase tracking-wide text-muted">Bedömd av</dt>
                    <dd>
                      {data.exclusion.assessor}
                      {data.exclusion.ai_model ? ` (${data.exclusion.ai_model})` : ""}
                      {" · "}
                      {visaDatumTid(data.exclusion.assessed_at)}
                    </dd>
                  </div>
                </dl>

                {data.exclusion.matched_quote ? (
                  <div>
                    <p className="mb-1 text-[0.75rem] uppercase tracking-wide text-muted">
                      Ordalydelse som utlöste regeln
                      {data.exclusion.page_number !== null && ` (sida ${data.exclusion.page_number})`}
                    </p>
                    <blockquote className="border-l-2 border-accent/40 bg-surface px-3 py-2 text-[0.875rem] italic leading-relaxed text-ink">
                      {data.exclusion.matched_quote}
                    </blockquote>
                    {data.exclusion.document_url && (
                      <p className="mt-1 text-[0.8125rem]">
                        <ExternalLink href={data.exclusion.document_url}>Källdokument</ExternalLink>
                        {data.exclusion.quote_offset !== null && (
                          <span className="ml-2 text-muted">
                            tecken {data.exclusion.quote_offset}
                          </span>
                        )}
                      </p>
                    )}
                  </div>
                ) : (
                  <Note>
                    Inget citat sparat. Det förekommer bara när bedömningen är PASS utan träff på
                    någon regel.
                  </Note>
                )}

                {data.exclusion.ai_reasoning && (
                  <div>
                    <p className="mb-1 text-[0.75rem] uppercase tracking-wide text-muted">
                      Bedömning
                    </p>
                    <p className="text-[0.875rem] leading-relaxed">{data.exclusion.ai_reasoning}</p>
                  </div>
                )}

                {data.exclusion.override_reason && (
                  <Caveat>
                    Manuellt överprövad: {data.exclusion.override_reason}
                  </Caveat>
                )}

                <div className="border-t border-line pt-3">
                  {visaOverprovning ? (
                    <div className="space-y-3">
                      <Field label="Nytt beslut">
                        <Select
                          value={nyttBeslut}
                          onChange={(e) => setNyttBeslut(e.target.value as ExclusionVerdict)}
                        >
                          {Object.entries(VERDICT_TEXT).map(([v, t]) => (
                            <option key={v} value={v}>
                              {t}
                            </option>
                          ))}
                        </Select>
                      </Field>
                      <Field
                        label="Anledning"
                        hint="Sparas i revisionsloggen tillsammans med det tidigare beslutet. Minst 10 tecken."
                      >
                        <Textarea
                          rows={3}
                          value={anledning}
                          onChange={(e) => setAnledning(e.target.value)}
                          placeholder="t.ex. Kontrollen gäller endast fast anställda, inte konsultuppdraget."
                        />
                      </Field>
                      <div className="flex gap-2">
                        <Button
                          variant="primary"
                          onClick={overprova}
                          disabled={arbetar || anledning.trim().length < 10}
                        >
                          Spara beslut
                        </Button>
                        <Button variant="ghost" onClick={() => setVisaOverprovning(false)}>
                          Avbryt
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <Button onClick={() => setVisaOverprovning(true)}>Överpröva bedömningen</Button>
                  )}
                </div>
              </div>
            )}
          </Card>

          {/* --- Annonstext --- */}
          <Card title="Annonstext" description="Sparad som den såg ut vid insamlingen">
            <div className="p-5">
              {annons?.description ? (
                <pre className="max-h-[32rem] overflow-y-auto whitespace-pre-wrap font-sans text-[0.875rem] leading-relaxed text-ink">
                  {annons.description}
                </pre>
              ) : (
                <Note>Ingen annonstext sparad.</Note>
              )}
            </div>
          </Card>
        </div>

        {/* --- Sidospalt --- */}
        <div className="space-y-4">
          <Card title="Uppgifter">
            <dl className="divide-y divide-line text-[0.875rem]">
              {[
                ["Poäng", <ScoreBadge key="p" score={data.match_score} />],
                ["Roll", annons ? ROLE_TEXT[annons.role_family] : "–"],
                ["Anställningsform", annons ? EMPLOYMENT_TEXT[annons.employment_type] : "–"],
                ["Yrkesbegrepp", annons?.occupation_label ?? "–"],
                ["Publicerad", visaDatumTid(annons?.published_at)],
                [
                  "Sista ansökningsdag",
                  <span key="d">
                    {visaDatum(annons?.application_deadline)}
                    {dagarKvar(annons?.application_deadline) && (
                      <span className="ml-2 text-muted">
                        ({dagarKvar(annons?.application_deadline)})
                      </span>
                    )}
                  </span>,
                ],
                [
                  "Avpublicerad",
                  annons?.depublished_at ? visaDatumTid(annons.depublished_at) : "– (ligger kvar)",
                ],
                ["Längd", data.duration_months ? `${data.duration_months} månader` : "–"],
                [
                  "Arvode",
                  data.fee_sek_per_hour ? `${visaKronor(data.fee_sek_per_hour)}/tim` : "–",
                ],
                ["Kommun", annons?.workplace_municipality ?? "–"],
                ["Län", annons?.workplace_region ?? "–"],
              ].map(([etikett, varde], i) => (
                <div key={i} className="flex items-start justify-between gap-4 px-5 py-2.5">
                  <dt className="text-muted">{etikett}</dt>
                  <dd className="text-right">{varde}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card title="Spårbarhet" description="Varje uppgift ska gå att följa till sin källa">
            <dl className="divide-y divide-line text-[0.875rem]">
              <div className="flex items-start justify-between gap-4 px-5 py-2.5">
                <dt className="text-muted">Källa</dt>
                <dd className="font-mono text-[0.8125rem]">{annons?.source_key ?? "–"}</dd>
              </div>
              <div className="flex items-start justify-between gap-4 px-5 py-2.5">
                <dt className="text-muted">Id hos källan</dt>
                <dd className="break-all font-mono text-[0.75rem]">{annons?.external_id ?? "–"}</dd>
              </div>
              <div className="flex items-start justify-between gap-4 px-5 py-2.5">
                <dt className="text-muted">Rådata</dt>
                <dd>
                  {annons?.snapshot_id ? (
                    <Link
                      href={`/administration?snapshot=${annons.snapshot_id}`}
                      className="text-accent hover:underline"
                    >
                      Visa ögonblicksbild
                    </Link>
                  ) : (
                    "–"
                  )}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4 px-5 py-2.5">
                <dt className="text-muted">Inläst</dt>
                <dd>{visaDatumTid(data.created_at)}</dd>
              </div>
            </dl>
          </Card>

          {data.appointment_id && (
            <Card title="Tillsättning">
              <div className="p-5">
                <p className="text-[0.875rem] leading-relaxed text-muted">
                  Rekryteringen följs upp som eget ärende.
                </p>
                <div className="mt-3">
                  <Link
                    href={`/tillsattningar/${data.appointment_id}`}
                    className="text-[0.875rem] font-medium text-accent hover:underline"
                  >
                    Öppna tillsättningsärendet →
                  </Link>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
