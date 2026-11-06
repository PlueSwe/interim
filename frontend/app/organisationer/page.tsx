"use client";

import { useState } from "react";

import {
  Badge,
  Card,
  Empty,
  ErrorBox,
  ExternalLink,
  Input,
  PageHeader,
  Pagination,
  Select,
  Spinner,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { ORG_TEXT, visaTal } from "@/lib/format";
import type { OrgType, Organisation, Page } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function Organisationer() {
  const [q, setQ] = useState("");
  const [typ, setTyp] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, fel, laddar, ladda } = useApi<Page<Organisation>>("/organisations", {
    q: q || undefined,
    org_type: typ || undefined,
    limit: 100,
    offset,
  });

  return (
    <>
      <PageHeader
        title="Organisationer"
        description="Myndigheter, kommuner, regioner, lärosäten och bolag som förekommer i insamlade data. Varje organisationsnummer kommer från en källa."
      />

      <Card
        title={data ? `${visaTal(data.total)} organisationer` : "Organisationer"}
        action={
          <div className="flex gap-2">
            <Select
              value={typ}
              onChange={(e) => {
                setTyp(e.target.value);
                setOffset(0);
              }}
              className="w-48"
            >
              <option value="">Alla typer</option>
              {Object.entries(ORG_TEXT).map(([v, t]) => (
                <option key={v} value={v}>
                  {t}
                </option>
              ))}
            </Select>
            <Input
              placeholder="Sök namn"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setOffset(0);
              }}
              className="w-56"
            />
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
                  <Th>Namn</Th>
                  <Th className="w-56">Typ</Th>
                  <Th className="w-44">Organisationsnummer</Th>
                  <Th>Webbplats</Th>
                </tr>
              </thead>
              <tbody>
                {(data?.items.length ?? 0) === 0 && (
                  <Empty colSpan={4}>Inga organisationer matchar sökningen</Empty>
                )}
                {data?.items.map((o) => (
                  <tr key={o.id} className="hover:bg-surface">
                    <Td className="font-medium">{o.name}</Td>
                    <Td>
                      <Badge tone={o.org_type === "PRIVATE" ? "neutral" : "accent"}>
                        {ORG_TEXT[o.org_type as OrgType] ?? o.org_type}
                      </Badge>
                    </Td>
                    <Td className="font-mono text-[0.8125rem]">{o.org_number ?? "–"}</Td>
                    <Td>
                      {o.website ? (
                        <ExternalLink href={o.website}>
                          {o.website.replace(/^https?:[/][/]/, "")}
                        </ExternalLink>
                      ) : (
                        <span className="text-muted">–</span>
                      )}
                    </Td>
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
