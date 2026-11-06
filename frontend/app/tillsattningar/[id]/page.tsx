"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

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
  Note,
  PageHeader,
  RequestBadge,
  Select,
  Spinner,
  StatusBadge,
  Table,
  Td,
  Textarea,
  Th,
} from "@/components/ui";
import { api } from "@/lib/api";
import {
  DOCUMENT_TEXT,
  STATUS_TEXT,
  VERIFIERING,
  visaDatum,
  visaDatumTid,
} from "@/lib/format";
import type {
  AppointmentDetail,
  DocumentType,
  InformationRequest,
  PublicDocument,
} from "@/lib/types";
import { useAction, useApi } from "@/lib/useApi";

export default function Tillsattningsdetalj() {
  const { id } = useParams<{ id: string }>();
  const arende = useApi<AppointmentDetail>(`/appointments/${id}`);
  const handlingar = useApi<PublicDocument[]>(`/appointments/${id}/documents`);
  const { kor, arbetar, fel: atgardsfel } = useAction();

  const [begaran, setBegaran] = useState<InformationRequest | null>(null);
  const [redigerad, setRedigerad] = useState<{ subject: string; body: string } | null>(null);
  const [sokresultat, setSokresultat] = useState<{
    searched: boolean;
    reason?: string;
    candidates: Array<{ url?: string; title?: string; note?: string }>;
  } | null>(null);

  const begaranId = arende.data?.information_request_id ?? null;

  useEffect(() => {
    if (!begaranId) {
      setBegaran(null);
      return;
    }
    api
      .get<InformationRequest>(`/information-requests/${begaranId}`)
      .then(setBegaran)
      .catch(() => setBegaran(null));
  }, [begaranId]);

  function uppdatera() {
    arende.ladda();
    handlingar.ladda();
    if (begaranId) {
      api.get<InformationRequest>(`/information-requests/${begaranId}`).then(setBegaran);
    }
  }

  if (arende.fel) return <ErrorBox error={arende.fel} onRetry={arende.ladda} />;
  if (arende.laddar || !arende.data) return <Spinner />;

  const a = arende.data;
  const niva = a.verification_level;

  return (
    <>
      <PageHeader
        title={a.job_ad?.title ?? "Tillsättningsärende"}
        description={
          <>
            {a.authority_name ?? "Okänd myndighet"} · <StatusBadge status={a.status} />
          </>
        }
      >
        {a.job_ad?.url && <ExternalLink href={a.job_ad.url}>Originalannonsen</ExternalLink>}
      </PageHeader>

      {atgardsfel && (
        <div className="mb-4">
          <ErrorBox error={atgardsfel} />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          {/* --- Vem fick tjansten --- */}
          <Card
            title="Vem fick tjänsten"
            description="Uppgiften antas aldrig. Den registreras bara mot en handling, och räknas som verifierad bara på nivå 1–3."
          >
            <div className="space-y-3 p-5">
              {a.appointed_person_name ? (
                <>
                  <p className="text-[1.125rem] font-semibold text-ink">{a.appointed_person_name}</p>
                  {a.appointed_person_previous_role && (
                    <p className="text-[0.875rem] text-muted">
                      Tidigare: {a.appointed_person_previous_role}
                    </p>
                  )}
                  <div className="flex flex-wrap items-center gap-2">
                    {niva !== null && (
                      <Badge tone={VERIFIERING[niva]?.racker ? "pass" : "review"}>
                        Nivå {niva} · {VERIFIERING[niva]?.text ?? "okänd nivå"}
                      </Badge>
                    )}
                    {a.diary_number && <Badge>Dnr {a.diary_number}</Badge>}
                    {a.decision_date && <Badge>Beslut {visaDatum(a.decision_date)}</Badge>}
                    {a.start_date && <Badge>Tillträde {visaDatum(a.start_date)}</Badge>}
                  </div>
                  {a.decision_document_url && (
                    <p className="text-[0.875rem]">
                      <ExternalLink href={a.decision_document_url}>
                        Handlingen som uppgiften kommer ur
                      </ExternalLink>
                    </p>
                  )}
                  <div className="pt-2">
                    <RaderaPerson arendeId={id} onKlar={uppdatera} />
                  </div>
                </>
              ) : (
                <Note>
                  Ingen uppgift om vem som fick tjänsten är fastställd. Att annonsen tagits ned
                  betyder inte att tjänsten är tillsatt, och systemet gissar inte.
                </Note>
              )}

              {a.resolution_note && (
                <div className="border-t border-line pt-3">
                  <p className="mb-1 text-[0.75rem] uppercase tracking-wide text-muted">
                    Anteckning
                  </p>
                  <p className="whitespace-pre-wrap text-[0.875rem] leading-relaxed">
                    {a.resolution_note}
                  </p>
                </div>
              )}
            </div>
          </Card>

          {/* --- Begaran om allman handling --- */}
          <Card
            title="Begäran om allmän handling"
            description="Skickas aldrig av systemet. Du godkänner texten, du skickar den, systemet registrerar att den gått iväg."
            action={begaran && <RequestBadge status={begaran.status} />}
          >
            {begaran === null ? (
              <div className="p-5">
                <Note>
                  Ingen begäran är förberedd. Ett utkast skapas när ärendet går till status
                  “Begäran förberedd”.
                </Note>
              </div>
            ) : (
              <div className="space-y-3 p-5">
                <Field label="Mottagare">
                  <Input value={begaran.recipient_email ?? ""} readOnly />
                </Field>

                <Field label="Ämne">
                  <Input
                    value={redigerad?.subject ?? begaran.subject}
                    readOnly={begaran.status !== "DRAFT"}
                    onChange={(e) =>
                      setRedigerad({
                        subject: e.target.value,
                        body: redigerad?.body ?? begaran.body,
                      })
                    }
                  />
                </Field>

                <Field
                  label="Text"
                  hint={
                    begaran.status === "DRAFT"
                      ? "Går att ändra fram till godkännandet. Efter det är texten låst."
                      : "Låst sedan godkännandet, så att det som godkändes är det som finns kvar."
                  }
                >
                  <Textarea
                    rows={12}
                    value={redigerad?.body ?? begaran.body}
                    readOnly={begaran.status !== "DRAFT"}
                    onChange={(e) =>
                      setRedigerad({
                        subject: redigerad?.subject ?? begaran.subject,
                        body: e.target.value,
                      })
                    }
                  />
                </Field>

                <div className="flex flex-wrap gap-2 border-t border-line pt-3">
                  {begaran.status === "DRAFT" && redigerad && (
                    <Button
                      onClick={async () => {
                        await kor(() =>
                          api.patch(`/information-requests/${begaran.id}`, redigerad),
                        );
                        setRedigerad(null);
                        uppdatera();
                      }}
                      disabled={arbetar}
                    >
                      Spara ändringar
                    </Button>
                  )}

                  {begaran.status === "DRAFT" && (
                    <Button
                      variant="primary"
                      disabled={arbetar || redigerad !== null}
                      onClick={async () => {
                        await kor(() =>
                          api.post(`/information-requests/${begaran.id}/approve`),
                        );
                        uppdatera();
                      }}
                    >
                      Godkänn texten
                    </Button>
                  )}

                  {begaran.status === "APPROVED" && (
                    <Button
                      variant="primary"
                      disabled={arbetar}
                      onClick={async () => {
                        await kor(() =>
                          api.post(`/information-requests/${begaran.id}/mark-sent`, {
                            channel: "EMAIL",
                          }),
                        );
                        uppdatera();
                      }}
                    >
                      Jag har skickat den
                    </Button>
                  )}
                </div>

                {begaran.status === "DRAFT" && redigerad !== null && (
                  <Caveat>Spara ändringarna innan du godkänner, annars godkänns den gamla texten.</Caveat>
                )}

                {begaran.status === "APPROVED" && (
                  <Note>
                    Godkänd {visaDatumTid(begaran.approved_at)}. Kopiera texten till din
                    e-postklient och skicka den själv. Markera därefter att den gått iväg.
                  </Note>
                )}

                {begaran.status === "SENT" && (
                  <SvarsFormular begaranId={begaran.id} onKlar={uppdatera} />
                )}

                {begaran.status === "ANSWERED" && begaran.response_note && (
                  <div className="border-t border-line pt-3">
                    <p className="mb-1 text-[0.75rem] uppercase tracking-wide text-muted">
                      Myndighetens svar
                    </p>
                    <p className="whitespace-pre-wrap text-[0.875rem] leading-relaxed">
                      {begaran.response_note}
                    </p>
                    {begaran.response_document_id && (
                      <p className="mt-2 text-[0.8125rem] text-muted">
                        Svaret är sparat som handling. Registrera namnet nedan med handlingen som
                        underlag.
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* --- Handlingar --- */}
          <Card
            title="Handlingar"
            description="Myndighetens handlingar som kan styrka tillsättningen"
            action={<NyHandling arendeId={id} onKlar={uppdatera} />}
          >
            <Table>
              <thead>
                <tr>
                  <Th>Handling</Th>
                  <Th>Typ</Th>
                  <Th>Diarienummer</Th>
                  <Th>Datum</Th>
                  <Th>Inkom via</Th>
                </tr>
              </thead>
              <tbody>
                {(handlingar.data?.length ?? 0) === 0 && (
                  <Empty colSpan={5}>
                    Inga handlingar registrerade. Anslås besluten fysiskt får de läggas in för hand.
                  </Empty>
                )}
                {handlingar.data?.map((d) => (
                  <tr key={d.id}>
                    <Td>
                      {d.url ? (
                        <ExternalLink href={d.url}>{d.title ?? "Handling"}</ExternalLink>
                      ) : (
                        (d.title ?? "Handling")
                      )}
                      <p className="mt-0.5 font-mono text-[0.6875rem] text-muted">{d.id}</p>
                    </Td>
                    <Td>
                      <Badge>{DOCUMENT_TEXT[d.document_type]}</Badge>
                    </Td>
                    <Td className="font-mono text-[0.8125rem]">{d.diary_number ?? "–"}</Td>
                    <Td className="whitespace-nowrap text-muted">{visaDatum(d.document_date)}</Td>
                    <Td className="text-muted">{d.acquisition ?? "–"}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>

          {/* --- Registrera namn --- */}
          {!a.appointed_person_name && (handlingar.data?.length ?? 0) > 0 && (
            <IdentifieraForm
              arendeId={id}
              handlingar={handlingar.data ?? []}
              onKlar={uppdatera}
            />
          )}
        </div>

        {/* --- Sidospalt --- */}
        <div className="space-y-4">
          <Card title="Åtgärder">
            <div className="space-y-2 p-5">
              <Button
                className="w-full justify-center"
                disabled={arbetar}
                onClick={async () => {
                  const r = await kor(() =>
                    api.post<{
                      searched: boolean;
                      reason?: string;
                      candidates: Array<{ url?: string; title?: string; note?: string }>;
                    }>(`/appointments/${id}/search-decision`),
                  );
                  if (r) setSokresultat(r);
                  arende.ladda();
                }}
              >
                Sök efter beslutet
              </Button>

              {sokresultat && (
                <div className="space-y-2">
                  {sokresultat.searched ? (
                    sokresultat.candidates.length > 0 ? (
                      <ul className="space-y-1 text-[0.8125rem]">
                        {sokresultat.candidates.map((k, i) => (
                          <li key={i}>
                            {k.url ? (
                              <ExternalLink href={k.url}>{k.title ?? k.url}</ExternalLink>
                            ) : (
                              (k.title ?? "–")
                            )}
                            {k.note && <span className="text-muted"> – {k.note}</span>}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <Note>Sökningen gav inget. Ärendet står kvar som olöst.</Note>
                    )
                  ) : (
                    <Caveat>Sökningen hoppades över: {sokresultat.reason}</Caveat>
                  )}
                </div>
              )}

              <AvslutaOlost arendeId={id} status={a.status} onKlar={uppdatera} />
            </div>
          </Card>

          <Card title="Uppgifter">
            <dl className="divide-y divide-line text-[0.875rem]">
              {(
                [
                  ["Status", <StatusBadge key="s" status={a.status} />],
                  ["Status ändrad", visaDatumTid(a.status_changed_at)],
                  ["Diarienummer", a.diary_number ?? "–"],
                  ["Beslutsdatum", visaDatum(a.decision_date)],
                  ["Tillträde", visaDatum(a.start_date)],
                  [
                    "Verifieringsnivå",
                    niva !== null ? `${niva} – ${VERIFIERING[niva]?.text ?? "okänd"}` : "–",
                  ],
                  ["Ansökan stängde", visaDatum(a.job_ad?.application_deadline)],
                  [
                    "Annons avpublicerad",
                    a.job_ad?.depublished_at ? visaDatumTid(a.job_ad.depublished_at) : "– (ligger kvar)",
                  ],
                  ["Senast sökt", visaDatumTid(a.last_searched_at)],
                ] as Array<[string, React.ReactNode]>
              ).map(([etikett, varde], i) => (
                <div key={i} className="flex items-start justify-between gap-4 px-5 py-2.5">
                  <dt className="text-muted">{etikett}</dt>
                  <dd className="text-right">{varde}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card title="Ärendets historik" description="Varje statusbyte, med vem och varför">
            <ol className="divide-y divide-line">
              {a.history.length === 0 && (
                <li className="px-5 py-4 text-[0.875rem] text-muted">Ingen historik</li>
              )}
              {a.history.map((h, i) => (
                <li key={i} className="px-5 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[0.875rem] font-medium">
                      {STATUS_TEXT[h.to_status]}
                    </span>
                    <span className="whitespace-nowrap text-[0.75rem] text-muted">
                      {visaDatumTid(h.changed_at)}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[0.75rem] text-muted">
                    {h.from_status ? `från ${STATUS_TEXT[h.from_status]} · ` : ""}
                    {h.changed_by}
                  </p>
                  {h.reason && (
                    <p className="mt-1 text-[0.8125rem] leading-relaxed text-ink">{h.reason}</p>
                  )}
                </li>
              ))}
            </ol>
          </Card>

          {a.job_ad && (
            <Card title="Annonsen">
              <div className="p-5 text-[0.875rem]">
                <p className="font-medium">{a.job_ad.title}</p>
                <p className="mt-1 text-muted">{a.job_ad.organisation_name}</p>
                <p className="mt-2 text-[0.8125rem] text-muted">
                  Publicerad {visaDatum(a.job_ad.published_at)} · källa{" "}
                  <span className="font-mono">{a.job_ad.source_key}</span>
                </p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

// --- Delformulär -----------------------------------------------------------

function NyHandling({ arendeId, onKlar }: { arendeId: string; onKlar: () => void }) {
  const { kor, arbetar, fel } = useAction();
  const [oppen, setOppen] = useState(false);
  const [form, setForm] = useState({
    document_type: "EMPLOYMENT_DECISION" as DocumentType,
    title: "",
    url: "",
    diary_number: "",
    document_date: "",
    acquisition: "NOTICE_BOARD_VISIT",
    extracted_text: "",
  });

  if (!oppen) return <Button onClick={() => setOppen(true)}>Registrera handling</Button>;

  return (
    <div className="w-full">
      <Button variant="ghost" onClick={() => setOppen(false)}>
        Stäng
      </Button>
      <div className="mt-2 w-[32rem] space-y-3 rounded-md border border-line bg-surface p-4">
        <Note>
          För handlingar som inte går att hämta automatiskt – ett beslut läst på en fysisk
          anslagstavla, eller ett papper som kommit med posten.
        </Note>
        <Field label="Typ av handling">
          <Select
            value={form.document_type}
            onChange={(e) => setForm({ ...form, document_type: e.target.value as DocumentType })}
          >
            {Object.entries(DOCUMENT_TEXT).map(([v, t]) => (
              <option key={v} value={v}>
                {t}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Benämning">
          <Input
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="t.ex. Anställningsbeslut, anslaget på anslagstavlan Torsplan"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Diarienummer">
            <Input
              value={form.diary_number}
              onChange={(e) => setForm({ ...form, diary_number: e.target.value })}
            />
          </Field>
          <Field label="Datum på handlingen">
            <Input
              type="date"
              value={form.document_date}
              onChange={(e) => setForm({ ...form, document_date: e.target.value })}
            />
          </Field>
        </div>
        <Field label="Inkom via" hint="t.ex. NOTICE_BOARD_VISIT, POST, REGISTRAR_REPLY">
          <Input
            value={form.acquisition}
            onChange={(e) => setForm({ ...form, acquisition: e.target.value })}
          />
        </Field>
        <Field label="Länk, om handlingen finns publicerad">
          <Input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
        </Field>
        <Field label="Handlingens text eller referat">
          <Textarea
            rows={4}
            value={form.extracted_text}
            onChange={(e) => setForm({ ...form, extracted_text: e.target.value })}
          />
        </Field>
        {fel && <ErrorBox error={fel} />}
        <Button
          variant="primary"
          disabled={arbetar || form.title.trim().length < 3}
          onClick={async () => {
            const ok = await kor(() =>
              api.post(`/appointments/${arendeId}/documents`, {
                document_type: form.document_type,
                title: form.title,
                url: form.url || null,
                diary_number: form.diary_number || null,
                document_date: form.document_date || null,
                acquisition: form.acquisition,
                extracted_text: form.extracted_text || null,
              }),
            );
            if (ok) {
              setOppen(false);
              onKlar();
            }
          }}
        >
          Spara handlingen
        </Button>
      </div>
    </div>
  );
}

function IdentifieraForm({
  arendeId,
  handlingar,
  onKlar,
}: {
  arendeId: string;
  handlingar: PublicDocument[];
  onKlar: () => void;
}) {
  const { kor, arbetar, fel } = useAction();
  const [form, setForm] = useState({
    full_name: "",
    document_id: handlingar[0]?.id ?? "",
    verification_level: 1,
    previous_role: "",
    previous_organisation: "",
    decision_date: "",
    start_date: "",
    diary_number: "",
  });

  const racker = VERIFIERING[form.verification_level]?.racker ?? false;

  return (
    <Card
      title="Registrera vem som fick tjänsten"
      description="Kräver en handling. Nivå 4–5 sparar ingen personuppgift, bara en anteckning om uppslaget."
    >
      <div className="space-y-3 p-5">
        <Field label="Handling som uppgiften kommer ur">
          <Select
            value={form.document_id}
            onChange={(e) => setForm({ ...form, document_id: e.target.value })}
          >
            {handlingar.map((d) => (
              <option key={d.id} value={d.id}>
                {DOCUMENT_TEXT[d.document_type]} – {d.title ?? d.id}
                {d.diary_number ? ` (${d.diary_number})` : ""}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Verifieringsnivå">
          <Select
            value={form.verification_level}
            onChange={(e) =>
              setForm({ ...form, verification_level: Number(e.target.value) })
            }
          >
            {Object.entries(VERIFIERING).map(([n, v]) => (
              <option key={n} value={n}>
                {n} – {v.text}
                {v.racker ? "" : " (räcker inte som belägg)"}
              </option>
            ))}
          </Select>
        </Field>

        {!racker && (
          <Caveat>
            På nivå {form.verification_level} sparas inget namn. Ärendet står kvar som olöst och
            uppgiften noteras bara som ett uppslag att följa upp.
          </Caveat>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Namn">
            <Input
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
          </Field>
          <Field label="Diarienummer">
            <Input
              value={form.diary_number}
              onChange={(e) => setForm({ ...form, diary_number: e.target.value })}
            />
          </Field>
          <Field label="Tidigare roll">
            <Input
              value={form.previous_role}
              onChange={(e) => setForm({ ...form, previous_role: e.target.value })}
            />
          </Field>
          <Field label="Tidigare organisation">
            <Input
              value={form.previous_organisation}
              onChange={(e) => setForm({ ...form, previous_organisation: e.target.value })}
            />
          </Field>
          <Field label="Beslutsdatum">
            <Input
              type="date"
              value={form.decision_date}
              onChange={(e) => setForm({ ...form, decision_date: e.target.value })}
            />
          </Field>
          <Field label="Tillträdesdatum">
            <Input
              type="date"
              value={form.start_date}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            />
          </Field>
        </div>

        {fel && <ErrorBox error={fel} />}

        <Button
          variant="primary"
          disabled={arbetar || form.full_name.trim().length < 2 || !form.document_id}
          onClick={async () => {
            const ok = await kor(() =>
              api.post(`/appointments/${arendeId}/identify`, {
                full_name: form.full_name,
                document_id: form.document_id,
                verification_level: form.verification_level,
                previous_role: form.previous_role || null,
                previous_organisation: form.previous_organisation || null,
                decision_date: form.decision_date || null,
                start_date: form.start_date || null,
                diary_number: form.diary_number || null,
              }),
            );
            if (ok) onKlar();
          }}
        >
          Registrera
        </Button>
      </div>
    </Card>
  );
}

function SvarsFormular({ begaranId, onKlar }: { begaranId: string; onKlar: () => void }) {
  const { kor, arbetar, fel } = useAction();
  const [oppen, setOppen] = useState(false);
  const [form, setForm] = useState({
    note: "",
    appointed_name: "",
    decision_date: "",
    diary_number: "",
  });

  if (!oppen)
    return (
      <div className="border-t border-line pt-3">
        <Button onClick={() => setOppen(true)}>Registrera myndighetens svar</Button>
      </div>
    );

  return (
    <div className="space-y-3 border-t border-line pt-3">
      <Field label="Svarets innehåll" hint="Sparas som en handling av typen svar från registrator.">
        <Textarea
          rows={4}
          value={form.note}
          onChange={(e) => setForm({ ...form, note: e.target.value })}
        />
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Angivet namn" hint="Sparas inte som personuppgift här.">
          <Input
            value={form.appointed_name}
            onChange={(e) => setForm({ ...form, appointed_name: e.target.value })}
          />
        </Field>
        <Field label="Beslutsdatum">
          <Input
            type="date"
            value={form.decision_date}
            onChange={(e) => setForm({ ...form, decision_date: e.target.value })}
          />
        </Field>
        <Field label="Diarienummer">
          <Input
            value={form.diary_number}
            onChange={(e) => setForm({ ...form, diary_number: e.target.value })}
          />
        </Field>
      </div>
      {fel && <ErrorBox error={fel} />}
      <div className="flex gap-2">
        <Button
          variant="primary"
          disabled={arbetar || form.note.trim().length < 3}
          onClick={async () => {
            const ok = await kor(() =>
              api.post(`/information-requests/${begaranId}/register-response`, {
                note: form.note,
                appointed_name: form.appointed_name || null,
                decision_date: form.decision_date || null,
                diary_number: form.diary_number || null,
              }),
            );
            if (ok) {
              setOppen(false);
              onKlar();
            }
          }}
        >
          Spara svaret
        </Button>
        <Button variant="ghost" onClick={() => setOppen(false)}>
          Avbryt
        </Button>
      </div>
    </div>
  );
}

function AvslutaOlost({
  arendeId,
  status,
  onKlar,
}: {
  arendeId: string;
  status: string;
  onKlar: () => void;
}) {
  const { kor, arbetar, fel } = useAction();
  const [anledning, setAnledning] = useState("");
  const [oppen, setOppen] = useState(false);

  if (status === "CLOSED_UNRESOLVED" || status === "APPOINTMENT_VERIFIED") return null;

  if (!oppen)
    return (
      <Button variant="ghost" className="w-full justify-center" onClick={() => setOppen(true)}>
        Avsluta som olöst
      </Button>
    );

  return (
    <div className="space-y-2">
      <Field label="Anledning" hint="Minst 5 tecken. Sparas i ärendets historik.">
        <Textarea
          rows={3}
          value={anledning}
          onChange={(e) => setAnledning(e.target.value)}
          placeholder="t.ex. Myndigheten uppger att beslutet endast anslås fysiskt och att handlingen inte lämnas digitalt."
        />
      </Field>
      {fel && <ErrorBox error={fel} />}
      <div className="flex gap-2">
        <Button
          variant="danger"
          disabled={arbetar || anledning.trim().length < 5}
          onClick={async () => {
            const ok = await kor(() =>
              api.post(`/appointments/${arendeId}/close-unresolved`, undefined, {
                reason: anledning,
              }),
            );
            if (ok) {
              setOppen(false);
              onKlar();
            }
          }}
        >
          Avsluta
        </Button>
        <Button variant="ghost" onClick={() => setOppen(false)}>
          Avbryt
        </Button>
      </div>
    </div>
  );
}

function RaderaPerson({ arendeId, onKlar }: { arendeId: string; onKlar: () => void }) {
  const { kor, arbetar, fel } = useAction();
  const [personId, setPersonId] = useState<string | null>(null);
  const [anledning, setAnledning] = useState("");
  const [oppen, setOppen] = useState(false);

  // Person-id finns inte i AppointmentDetail; det hamtas ur arendets
  // personuppgiftsrad via raderingsendpointen, som kraver id. Darfor fragar vi
  // anvandaren forst och hamtar id nar rutan oppnas.
  useEffect(() => {
    if (!oppen) return;
    api
      .get<{ id: string } | null>(`/appointments/${arendeId}/appointed-person`)
      .then((p) => setPersonId(p?.id ?? null))
      .catch(() => setPersonId(null));
  }, [oppen, arendeId]);

  if (!oppen)
    return (
      <Button variant="ghost" onClick={() => setOppen(true)}>
        Rätta eller radera personuppgiften
      </Button>
    );

  return (
    <div className="space-y-2 rounded-md border border-line bg-surface p-3">
      <Note>
        Radering enligt dataskyddsförordningen artikel 17. Ärendet och handlingen behålls – det är
        myndighetens handling, inte vår att radera. Bara namnuppgiften tas bort.
      </Note>
      <Field label="Anledning">
        <Input value={anledning} onChange={(e) => setAnledning(e.target.value)} />
      </Field>
      {fel && <ErrorBox error={fel} />}
      <div className="flex gap-2">
        <Button
          variant="danger"
          disabled={arbetar || !personId || anledning.trim().length < 3}
          onClick={async () => {
            const ok = await kor(() =>
              api.del(`/appointed-persons/${personId}`, { reason: anledning }),
            );
            if (ok) {
              setOppen(false);
              onKlar();
            }
          }}
        >
          Radera namnuppgiften
        </Button>
        <Button variant="ghost" onClick={() => setOppen(false)}>
          Avbryt
        </Button>
      </div>
      {personId === null && (
        <Caveat>
          Ingen personuppgift hittades för ärendet. Namnet kan redan vara raderat.
        </Caveat>
      )}
    </div>
  );
}
