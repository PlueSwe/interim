"use client";

import Link from "next/link";
import { Suspense, useState } from "react";

import { OpportunityTable } from "@/components/opportunity-table";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorBox,
  ExternalLink,
  Input,
  Kpi,
  Note,
  PageHeader,
  Pagination,
  Spinner,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { PUBLICATION_TEXT, SOURCE_STATUS_TEXT, visaDatum, visaDatumTid, visaTal } from "@/lib/format";
import type { Authority, Coverage, Opportunity, Page } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const PER_SIDA = 50;

function Tjanster() {
  const [offset, setOffset] = useState(0);
  const [form, setForm] = useState<"PERMANENT" | "FIXED_TERM">("PERMANENT");

  const { data, fel, laddar, ladda } = useApi<Page<Opportunity>>("/opportunities", {
    employment_type: form,
    sort: "deadline",
    limit: PER_SIDA,
    offset,
  });

  return (
    <Card
      title={data ? `${visaTal(data.total)} tjänster` : "Tjänster"}
      description="Tillsvidare- och tidsbegränsade chefstjänster hos myndigheter, kommuner, regioner och lärosäten"
      action={
        <div className="flex gap-1">
          {(
            [
              ["PERMANENT", "Tillsvidare"],
              ["FIXED_TERM", "Tidsbegränsade"],
            ] as const
          ).map(([v, t]) => (
            <Button
              key={v}
              variant={form === v ? "primary" : "secondary"}
              onClick={() => {
                setForm(v);
                setOffset(0);
              }}
            >
              {t}
            </Button>
          ))}
        </div>
      }
    >
      {fel ? (
        <div className="p-5">
          <ErrorBox error={fel} onRetry={ladda} />
        </div>
      ) : laddar && !data ? (
        <Spinner />
      ) : (
        <>
          <OpportunityTable poster={data?.items ?? []} visaArvode={false} />
          {data && (
            <Pagination
              total={data.total}
              limit={data.limit}
              offset={data.offset}
              onChange={setOffset}
            />
          )}
        </>
      )}
    </Card>
  );
}

function Myndighetsregister() {
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const tackning = useApi<Coverage>("/authorities/coverage");
  const { data, fel, laddar, ladda } = useApi<Page<Authority>>("/authorities", {
    q: q || undefined,
    limit: 100,
    offset,
  });

  return (
    <>
      {tackning.data && (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Kpi label="Organisationer" value={visaTal(tackning.data.authorities_total)} />
          <Kpi
            label="Aktiv bevakning"
            value={visaTal(tackning.data.authorities_active)}
            hint="Karriärsidan hämtas automatiskt"
          />
          <Kpi
            label="Overifierade"
            value={visaTal(tackning.data.authorities_unverified)}
            tone="review"
            hint="Finns i registret men bevakas inte ännu"
          />
          <Kpi label="Med vakansadress" value={visaTal(tackning.data.with_vacancies_url)} />
          <Kpi label="Med registrator" value={visaTal(tackning.data.with_registrar_email)} />
          <Kpi
            label="Fysisk anslagstavla"
            value={visaTal(tackning.data.physical_notice_board)}
            hint="Beslut anslås inte på webben"
            tone="review"
          />
        </div>
      )}

      {tackning.data?.note && (
        <div className="mb-4">
          <Note>{tackning.data.note}</Note>
        </div>
      )}

      <Card
        title={data ? `${visaTal(data.total)} organisationer i registret` : "Myndighetsregister"}
        description="Varje organisationsnummer kommer från en källa. Inga nummer är konstruerade."
        action={
          <Input
            placeholder="Sök organisation"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
            className="w-60"
          />
        }
      >
        {fel ? (
          <div className="p-5">
            <ErrorBox error={fel} onRetry={ladda} />
          </div>
        ) : laddar && !data ? (
          <Spinner />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Organisation</Th>
                  <Th>Plattform</Th>
                  <Th>Insamling</Th>
                  <Th>Beslut anslås</Th>
                  <Th>Registrator</Th>
                  <Th>Status</Th>
                  <Th>Senast kontrollerad</Th>
                </tr>
              </thead>
              <tbody>
                {(data?.items.length ?? 0) === 0 && (
                  <Empty colSpan={7}>Inga organisationer matchar sökningen</Empty>
                )}
                {data?.items.map((m) => (
                  <tr key={m.id} className="hover:bg-surface">
                    <Td>
                      <span className="font-medium">{m.organisation_name ?? "–"}</span>
                      {m.vacancies_url && (
                        <p className="mt-0.5 text-[0.75rem]">
                          <ExternalLink href={m.vacancies_url}>Lediga tjänster</ExternalLink>
                        </p>
                      )}
                    </Td>
                    <Td className="text-muted">{m.recruitment_platform}</Td>
                    <Td className="text-muted">{m.collection_method}</Td>
                    <Td>
                      <Badge
                        tone={
                          m.appointment_publication_mode === "PHYSICAL_NOTICE_BOARD"
                            ? "review"
                            : "neutral"
                        }
                        title={m.notice_board_location ?? undefined}
                      >
                        {PUBLICATION_TEXT[m.appointment_publication_mode]}
                      </Badge>
                      {m.notice_board_location && (
                        <p className="mt-0.5 text-[0.75rem] text-muted">{m.notice_board_location}</p>
                      )}
                    </Td>
                    <Td className="text-muted">{m.registrar_email ?? "–"}</Td>
                    <Td>
                      <Badge
                        tone={
                          m.status === "ACTIVE"
                            ? "pass"
                            : m.status === "FAILING" || m.status === "BLOCKED"
                              ? "excluded"
                              : "neutral"
                        }
                      >
                        {SOURCE_STATUS_TEXT[m.status]}
                      </Badge>
                      {m.verified_at && (
                        <p className="mt-0.5 text-[0.75rem] text-muted" title={m.verification_source ?? ""}>
                          verifierad {visaDatum(m.verified_at)}
                        </p>
                      )}
                    </Td>
                    <Td className="whitespace-nowrap text-muted">{visaDatumTid(m.last_checked_at)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            {data && (
              <Pagination
                total={data.total}
                limit={data.limit}
                offset={data.offset}
                onChange={setOffset}
              />
            )}
          </>
        )}
      </Card>
    </>
  );
}

export default function Myndighetstjanster() {
  const [flik, setFlik] = useState<"tjanster" | "register">("tjanster");

  return (
    <Suspense fallback={<Spinner />}>
      <PageHeader
        title="Myndighetstjänster"
        description="Fasta och tidsbegränsade chefstjänster, samt registret över de organisationer vars egna karriärsidor bevakas."
      >
        <Link href="/tillsattningar" className="text-[0.875rem] text-accent hover:underline">
          Följ upp stängda rekryteringar →
        </Link>
      </PageHeader>

      <div className="mb-4 flex gap-1 border-b border-line">
        {(
          [
            ["tjanster", "Lediga tjänster"],
            ["register", "Myndighetsregister"],
          ] as const
        ).map(([v, t]) => (
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

      {flik === "tjanster" ? <Tjanster /> : <Myndighetsregister />}
    </Suspense>
  );
}
