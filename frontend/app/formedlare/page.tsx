"use client";

import Link from "next/link";

import {
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
import { visaTal } from "@/lib/format";
import { useApi } from "@/lib/useApi";

interface FormedlareRad {
  id: string;
  name: string;
  org_number: string | null;
  website: string | null;
  assignment_count: number;
  note: string | null;
}

export default function Formedlare() {
  const { data, fel, laddar, ladda } = useApi<FormedlareRad[]>("/providers");

  if (fel) return <ErrorBox error={fel} onRetry={ladda} />;
  if (laddar || !data) return <Spinner />;

  return (
    <>
      <PageHeader
        title="Förmedlare"
        description="Konsultmäklare, bemanningsföretag och rekryteringsföretag som förekommer som avsändare i insamlade annonser."
      />

      <div className="mb-4">
        <Note>
          Antalet räknas på annonser systemet har läst in, inte på förmedlarens totala volym. Flera
          mäklares egna portaler kräver inloggning eller tillåter inte automatisk insamling – vilka,
          och varför, framgår under Administration.
        </Note>
      </div>

      <Card title={`${visaTal(data.length)} förmedlare`}>
        <Table>
          <thead>
            <tr>
              <Th>Namn</Th>
              <Th className="w-44">Organisationsnummer</Th>
              <Th>Webbplats</Th>
              <Th className="w-28">Annonser</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {data.length === 0 && <Empty colSpan={5}>Inga förmedlare registrerade</Empty>}
            {data.map((f) => (
              <tr key={f.id} className="hover:bg-surface">
                <Td className="font-medium">
                  {f.name}
                  {f.note && <p className="mt-0.5 text-[0.75rem] text-muted">{f.note}</p>}
                </Td>
                <Td className="font-mono text-[0.8125rem]">{f.org_number ?? "–"}</Td>
                <Td>
                  {f.website ? (
                    <ExternalLink href={f.website}>
                      {f.website.replace(/^https?:[/][/]/, "")}
                    </ExternalLink>
                  ) : (
                    <span className="text-muted">–</span>
                  )}
                </Td>
                <Td className="font-mono tabular-nums">{visaTal(f.assignment_count)}</Td>
                <Td>
                  <Link
                    href={`/uppdrag?recruiter_id=${f.id}`}
                    className="text-[0.8125rem] text-accent hover:underline"
                  >
                    Visa uppdrag
                  </Link>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </>
  );
}
