"use client";

import Link from "next/link";
import { Suspense, useState } from "react";

import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorBox,
  Note,
  PageHeader,
  Pagination,
  RequestBadge,
  Select,
  Spinner,
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/ui";
import {
  REQUEST_TEXT,
  STATUS_TEXT,
  VERIFIERING,
  visaDatum,
  visaDatumTid,
  visaTal,
} from "@/lib/format";
import type { Appointment, InformationRequest, Page } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const PER_SIDA = 50;

function Arenden() {
  const [status, setStatus] = useState("");
  const [olosta, setOlosta] = useState(false);
  const [offset, setOffset] = useState(0);

  const { data, fel, laddar, ladda } = useApi<Page<Appointment>>("/appointments", {
    status: status || undefined,
    unresolved_only: olosta ? "true" : undefined,
    limit: PER_SIDA,
    offset,
  });

  return (
    <Card
      title={data ? `${visaTal(data.total)} ärenden` : "Ärenden"}
      description="Ett ärende avslutas inte för att annonsen försvann. Den som fick tjänsten står här bara om det finns en handling som visar det."
      action={
        <div className="flex items-center gap-2">
          <Button variant={olosta ? "primary" : "secondary"} onClick={() => setOlosta(!olosta)}>
            Endast olösta
          </Button>
          <Select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
            className="w-56"
          >
            <option value="">Alla statusar</option>
            {Object.entries(STATUS_TEXT).map(([v, t]) => (
              <option key={v} value={v}>
                {t}
              </option>
            ))}
          </Select>
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
          <Table>
            <thead>
              <tr>
                <Th>Befattning</Th>
                <Th>Myndighet</Th>
                <Th>Status</Th>
                <Th>Tillsatt</Th>
                <Th>Beslut</Th>
                <Th>Senast ändrad</Th>
              </tr>
            </thead>
            <tbody>
              {(data?.items.length ?? 0) === 0 && (
                <Empty colSpan={6}>Inga tillsättningsärenden matchar filtret</Empty>
              )}
              {data?.items.map((a) => (
                <tr key={a.id} className="hover:bg-surface">
                  <Td>
                    <Link
                      href={`/tillsattningar/${a.id}`}
                      className="font-medium text-accent hover:underline"
                    >
                      {a.job_ad?.title ?? "Tjänst"}
                    </Link>
                  </Td>
                  <Td className="text-muted">{a.authority_name ?? "–"}</Td>
                  <Td>
                    <StatusBadge status={a.status} />
                  </Td>
                  <Td>
                    {a.appointed_person_name ? (
                      <>
                        <span className="font-medium">{a.appointed_person_name}</span>
                        {a.verification_level !== null && (
                          <p className="mt-0.5 text-[0.75rem] text-muted">
                            nivå {a.verification_level} ·{" "}
                            {VERIFIERING[a.verification_level]?.text ?? "–"}
                          </p>
                        )}
                      </>
                    ) : (
                      <span className="text-muted">ej fastställt</span>
                    )}
                  </Td>
                  <Td className="whitespace-nowrap text-muted">
                    {visaDatum(a.decision_date)}
                    {a.diary_number && (
                      <p className="mt-0.5 font-mono text-[0.75rem]">{a.diary_number}</p>
                    )}
                  </Td>
                  <Td className="whitespace-nowrap text-muted">{visaDatumTid(a.status_changed_at)}</Td>
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
  );
}

function Begaranden() {
  const [status, setStatus] = useState("");
  const { data, fel, laddar, ladda } = useApi<Page<InformationRequest>>("/information-requests", {
    status: status || undefined,
    limit: 100,
  });

  const utkast = data?.items.filter((b) => b.status === "DRAFT").length ?? 0;

  return (
    <>
      <div className="mb-4">
        <Note>
          En begäran om allmän handling skickas aldrig automatiskt. Utkastet skrivs av systemet, men
          det är du som godkänner texten och du som skickar den. Systemet registrerar bara att den
          har skickats.
        </Note>
      </div>

      <Card
        title={data ? `${visaTal(data.total)} begäranden` : "Begäranden"}
        description={utkast > 0 ? `${utkast} utkast väntar på godkännande` : undefined}
        action={
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-48">
            <option value="">Alla statusar</option>
            {Object.entries(REQUEST_TEXT).map(([v, t]) => (
              <option key={v} value={v}>
                {t}
              </option>
            ))}
          </Select>
        }
      >
        {fel ? (
          <div className="p-5">
            <ErrorBox error={fel} onRetry={ladda} />
          </div>
        ) : laddar && !data ? (
          <Spinner />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Ämne</Th>
                <Th>Mottagare</Th>
                <Th>Status</Th>
                <Th>Godkänd</Th>
                <Th>Skickad</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {(data?.items.length ?? 0) === 0 && (
                <Empty colSpan={6}>Inga begäranden har skapats</Empty>
              )}
              {data?.items.map((b) => (
                <tr key={b.id} className="hover:bg-surface">
                  <Td className="max-w-md">
                    <span className="font-medium">{b.subject}</span>
                  </Td>
                  <Td className="text-muted">{b.recipient_email ?? "–"}</Td>
                  <Td>
                    <RequestBadge status={b.status} />
                  </Td>
                  <Td className="whitespace-nowrap text-muted">{visaDatumTid(b.approved_at)}</Td>
                  <Td className="whitespace-nowrap text-muted">
                    {visaDatumTid(b.sent_at)}
                    {b.sent_channel && (
                      <span className="ml-1">
                        <Badge>{b.sent_channel}</Badge>
                      </span>
                    )}
                  </Td>
                  <Td>
                    {b.appointment_id && (
                      <Link
                        href={`/tillsattningar/${b.appointment_id}`}
                        className="text-[0.8125rem] text-accent hover:underline"
                      >
                        Öppna ärendet
                      </Link>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}

export default function Tillsattningar() {
  const [flik, setFlik] = useState<"arenden" | "begaranden">("arenden");

  return (
    <Suspense fallback={<Spinner />}>
      <PageHeader
        title="Tillsättningar"
        description="Spårar vem som faktiskt fick en utannonserad chefstjänst. Ett namn registreras bara mot en handling, och bara verifieringsnivå 1–3 räknas som verifierat."
      />

      <div className="mb-4 flex gap-1 border-b border-line">
        {(
          [
            ["arenden", "Ärenden"],
            ["begaranden", "Begäranden om allmän handling"],
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

      {flik === "arenden" ? <Arenden /> : <Begaranden />}
    </Suspense>
  );
}
