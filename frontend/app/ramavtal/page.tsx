"use client";

import {
  Badge,
  Card,
  Empty,
  ErrorBox,
  ExternalLink,
  Note,
  PageHeader,
  Spinner,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { visaDatum, visaTal } from "@/lib/format";
import type { FrameworkAgreement } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function Ramavtal() {
  const { data, fel, laddar, ladda } = useApi<FrameworkAgreement[]>("/market/framework-agreements");

  if (fel) return <ErrorBox error={fel} onRetry={ladda} />;
  if (laddar || !data) return <Spinner />;

  return (
    <>
      <PageHeader
        title="Ramavtal"
        description="Avtal med giltighetstid och eventuell förlängningsoption. Ett avtal som löper ut är en upphandling som kommer."
      />

      {data.length === 0 && (
        <div className="mb-4">
          <Note>
            Inga ramavtal är registrerade. Avtalen läggs in via manuell import eller från Avropa.se
            och Kammarkollegiets publicerade förteckningar – se Administration för vilka källor som
            är i drift.
          </Note>
        </div>
      )}

      <Card title={`${visaTal(data.length)} ramavtal`}>
        <Table>
          <thead>
            <tr>
              <Th>Avtal</Th>
              <Th>Område</Th>
              <Th className="w-32">Från</Th>
              <Th className="w-32">Till</Th>
              <Th className="w-28">Förlängning</Th>
              <Th className="w-28">Dagar kvar</Th>
            </tr>
          </thead>
          <tbody>
            {data.length === 0 && <Empty colSpan={6}>Inga ramavtal registrerade</Empty>}
            {data.map((r) => {
              const snart = r.days_left !== null && r.days_left <= 365;
              return (
                <tr key={r.id} className="hover:bg-surface">
                  <Td className="font-medium">
                    {r.url ? <ExternalLink href={r.url}>{r.name}</ExternalLink> : r.name}
                    {r.agreement_number && (
                      <p className="mt-0.5 font-mono text-[0.75rem] text-muted">
                        {r.agreement_number}
                      </p>
                    )}
                  </Td>
                  <Td className="text-muted">{r.area ?? "–"}</Td>
                  <Td className="whitespace-nowrap">{visaDatum(r.valid_from)}</Td>
                  <Td className="whitespace-nowrap">{visaDatum(r.valid_to)}</Td>
                  <Td className="text-muted">
                    {r.extension_months ? `${r.extension_months} mån` : "–"}
                  </Td>
                  <Td>
                    {r.days_left === null ? (
                      <span className="text-muted">–</span>
                    ) : (
                      <Badge tone={snart ? "review" : "neutral"}>{r.days_left}</Badge>
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
