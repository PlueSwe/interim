"use client";

import Link from "next/link";
import { useState } from "react";

import {
  Badge,
  Card,
  Empty,
  ErrorBox,
  ExternalLink,
  Note,
  PageHeader,
  Pagination,
  Spinner,
  Table,
  Td,
  Th,
  VerdictBadge,
} from "@/components/ui";
import { visaDatumTid, visaTal } from "@/lib/format";
import type { Exclusion, Opportunity, Page } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Rad = Opportunity & { exclusion: Exclusion | null };

function Lista({
  titel,
  beskrivning,
  rader,
  total,
  limit,
  offset,
  onOffset,
  tomText,
}: {
  titel: string;
  beskrivning: string;
  rader: Rad[];
  total?: number;
  limit?: number;
  offset?: number;
  onOffset?: (n: number) => void;
  tomText: string;
}) {
  return (
    <Card title={titel} description={beskrivning}>
      <Table>
        <thead>
          <tr>
            <Th>Uppdrag</Th>
            <Th className="w-36">Beslut</Th>
            <Th className="w-44">Regel</Th>
            <Th>Ordalydelse som utlöste regeln</Th>
            <Th className="w-40">Bedömd</Th>
          </tr>
        </thead>
        <tbody>
          {rader.length === 0 && <Empty colSpan={5}>{tomText}</Empty>}
          {rader.map((u) => (
            <tr key={u.id} className="hover:bg-surface">
              <Td>
                <Link href={`/uppdrag/${u.id}`} className="font-medium text-accent hover:underline">
                  {u.job_ad?.title ?? "Uppdrag"}
                </Link>
                <p className="mt-0.5 text-[0.75rem] text-muted">
                  {u.job_ad?.organisation_name ?? "–"}
                </p>
              </Td>
              <Td>
                <VerdictBadge verdict={u.exclusion_status} />
              </Td>
              <Td>
                <span className="font-mono text-[0.75rem]">{u.exclusion?.rule_id ?? "–"}</span>
                {u.exclusion?.override_reason && (
                  <p className="mt-0.5">
                    <Badge tone="review">överprövad</Badge>
                  </p>
                )}
              </Td>
              <Td>
                {u.exclusion?.matched_quote ? (
                  <blockquote className="border-l-2 border-excluded/30 pl-2 text-[0.8125rem] italic leading-relaxed">
                    {u.exclusion.matched_quote}
                  </blockquote>
                ) : (
                  <span className="text-[0.8125rem] text-muted">inget citat sparat</span>
                )}
                {u.exclusion?.document_url && (
                  <p className="mt-1 text-[0.75rem]">
                    <ExternalLink href={u.exclusion.document_url}>
                      Källa
                      {u.exclusion.page_number !== null && `, sida ${u.exclusion.page_number}`}
                    </ExternalLink>
                  </p>
                )}
              </Td>
              <Td className="whitespace-nowrap text-[0.8125rem] text-muted">
                {u.exclusion?.assessor ?? "–"}
                <br />
                {visaDatumTid(u.exclusion?.assessed_at)}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {total !== undefined && limit !== undefined && offset !== undefined && onOffset && (
        <Pagination total={total} limit={limit} offset={offset} onChange={onOffset} />
      )}
    </Card>
  );
}

export default function Exkluderade() {
  const [offset, setOffset] = useState(0);
  const exkluderade = useApi<Page<Rad>>("/opportunities/excluded", { limit: 50, offset });
  const granskning = useApi<{ total: number; items: Rad[] }>("/opportunities/review");

  if (exkluderade.fel) return <ErrorBox error={exkluderade.fel} onRetry={exkluderade.ladda} />;
  if (exkluderade.laddar && !exkluderade.data) return <Spinner />;

  return (
    <>
      <PageHeader
        title="Exkluderade uppdrag"
        description="Uppdrag som kräver säkerhetsprövning, registerkontroll, bakgrundskontroll eller motsvarande personkontroll. Varje beslut visas med den ordalydelse som utlöste det."
      />

      <div className="mb-5">
        <Note>
          Vanliga krav på GDPR, sekretessförbindelse och informationssäkerhetsarbete leder inte till
          exkludering – bara faktisk personkontroll gör det. Är texten otydlig eller för kort hamnar
          uppdraget under “Kräver granskning” i stället för att godkännas.
        </Note>
      </div>

      <div className="space-y-5">
        {granskning.data && granskning.data.items.length > 0 && (
          <Lista
            titel={`${visaTal(granskning.data.total)} kräver granskning`}
            beskrivning="Osäkra fall. Inget osäkert uppdrag markeras automatiskt som godkänt – det är du som avgör."
            rader={granskning.data.items}
            tomText="Inga uppdrag väntar på granskning"
          />
        )}

        <Lista
          titel={`${visaTal(exkluderade.data?.total ?? 0)} exkluderade`}
          beskrivning="Ligger utanför den sökbara listan men sparas med fullständigt underlag"
          rader={exkluderade.data?.items ?? []}
          total={exkluderade.data?.total}
          limit={exkluderade.data?.limit}
          offset={exkluderade.data?.offset}
          onOffset={setOffset}
          tomText="Inga uppdrag har exkluderats"
        />
      </div>
    </>
  );
}
