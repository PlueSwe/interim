"use client";

import { useState } from "react";

import {
  Badge,
  Card,
  Caveat,
  Empty,
  ErrorBox,
  ExternalLink,
  PageHeader,
  Select,
  Spinner,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { ORG_TEXT, visaDatum, visaKronor, visaTal } from "@/lib/format";
import type { MarketIntelligence, OrgType } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function Lista({
  titel,
  beskrivning,
  kolumner,
  rader,
  tomText,
}: {
  titel: string;
  beskrivning: string;
  kolumner: string[];
  rader: Array<React.ReactNode[]>;
  tomText: string;
}) {
  return (
    <Card title={titel} description={beskrivning}>
      <Table>
        <thead>
          <tr>
            {kolumner.map((k, i) => (
              <Th key={i} className={i > 0 ? "w-32" : undefined}>
                {k}
              </Th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rader.length === 0 && <Empty colSpan={kolumner.length}>{tomText}</Empty>}
          {rader.map((rad, i) => (
            <tr key={i} className="hover:bg-surface">
              {rad.map((c, j) => (
                <Td key={j} className={j > 0 ? "font-mono tabular-nums" : "font-medium"}>
                  {c}
                </Td>
              ))}
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

export default function Marknadsanalys() {
  const [manader, setManader] = useState("24");
  const { data, fel, laddar, ladda } = useApi<MarketIntelligence>("/market/intelligence", {
    months: manader,
  });

  if (fel) return <ErrorBox error={fel} onRetry={ladda} />;
  if (laddar || !data) return <Spinner />;

  return (
    <>
      <PageHeader
        title="Marknadsanalys"
        description="Vem köper interimtjänster, vem rekryterar IT-chefer, vilka förmedlare förekommer och vilka ramavtal löper ut."
      >
        <Select value={manader} onChange={(e) => setManader(e.target.value)} className="w-44">
          <option value="12">Senaste 12 månaderna</option>
          <option value="24">Senaste 24 månaderna</option>
          <option value="48">Senaste 48 månaderna</option>
        </Select>
      </PageHeader>

      <div className="mb-5">
        <Caveat>{data.caveat}</Caveat>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Lista
          titel="Återkommande interimköpare"
          beskrivning="Organisationer som annonserat minst två interim- eller konsultuppdrag"
          kolumner={["Organisation", "Typ", "Uppdrag"]}
          tomText="Inga återkommande köpare i perioden"
          rader={data.recurring_interim_buyers.map((r) => [
            r.organisation,
            <Badge key="t">{ORG_TEXT[r.org_type as OrgType] ?? r.org_type}</Badge>,
            visaTal(r.assignments),
          ])}
        />

        <Lista
          titel="Rekryterar ofta chefer"
          beskrivning="Organisationer med minst två annonserade chefstjänster"
          kolumner={["Organisation", "Typ", "Tjänster"]}
          tomText="Inga återkommande rekryterare i perioden"
          rader={data.frequent_recruiters.map((r) => [
            r.organisation,
            <Badge key="t">{ORG_TEXT[r.org_type as OrgType] ?? r.org_type}</Badge>,
            visaTal(r.positions),
          ])}
        />

        <Lista
          titel="Förmedlare efter volym"
          beskrivning="Annonser där en förmedlare står som avsändare"
          kolumner={["Förmedlare", "Annonser"]}
          tomText="Inga förmedlare registrerade"
          rader={data.brokers_by_volume.map((r) => [r.provider, visaTal(r.assignments)])}
        />

        <Lista
          titel="Leverantörer som vinner avrop"
          beskrivning="Avrop med registrerad vinnande leverantör"
          kolumner={["Leverantör", "Avrop", "Värde"]}
          tomText="Inga avrop med vinnare registrerade"
          rader={data.suppliers_winning_call_offs.map((r) => [
            r.provider,
            visaTal(r.call_offs),
            visaKronor(r.total_value_sek),
          ])}
        />

        <Lista
          titel="Organisationer med chefsbyten"
          beskrivning="Minst två tillsättningsärenden"
          kolumner={["Organisation", "Rekryteringar"]}
          tomText="Inga organisationer med flera chefsbyten"
          rader={data.organisations_with_leadership_turnover.map((r) => [
            r.organisation,
            visaTal(r.recruitments),
          ])}
        />

        <Card
          title="Ramavtal som löper ut"
          description="Inom 18 månader. En förnyad konkurrensutsättning brukar föregås av marknadsdialog."
        >
          <Table>
            <thead>
              <tr>
                <Th>Avtal</Th>
                <Th>Område</Th>
                <Th className="w-32">Giltigt till</Th>
                <Th className="w-24">Dagar</Th>
              </tr>
            </thead>
            <tbody>
              {data.expiring_agreements.length === 0 && (
                <Empty colSpan={4}>Inga ramavtal registrerade</Empty>
              )}
              {data.expiring_agreements.map((r) => (
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
                  <Td className="whitespace-nowrap">{visaDatum(r.valid_to)}</Td>
                  <Td className="font-mono tabular-nums">{r.days_left ?? "–"}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      </div>
    </>
  );
}
