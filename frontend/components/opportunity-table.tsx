// Uppdragslista. Anvands pa Uppdrag och pa Myndighetstjanster, som ar samma
// tabell med olika forval.

"use client";

import Link from "next/link";

import { Badge, Empty, ScoreBadge, Table, Td, Th, VerdictBadge } from "./ui";
import { EMPLOYMENT_TEXT, KIND_TEXT, dagarKvar, visaDatum, visaKronor } from "@/lib/format";
import type { Opportunity } from "@/lib/types";

export function OpportunityTable({
  poster,
  visaTyp = true,
  visaArvode = true,
}: {
  poster: Opportunity[];
  visaTyp?: boolean;
  visaArvode?: boolean;
}) {
  const kolumner = 5 + (visaTyp ? 1 : 0) + (visaArvode ? 1 : 0);
  return (
    <Table>
      <thead>
        <tr>
          <Th className="w-28">Poäng</Th>
          <Th>Befattning</Th>
          <Th>Organisation</Th>
          {visaTyp && <Th>Typ</Th>}
          <Th>Plats</Th>
          {visaArvode && <Th>Längd / arvode</Th>}
          <Th>Sista dag</Th>
        </tr>
      </thead>
      <tbody>
        {poster.length === 0 && (
          <Empty colSpan={kolumner}>
            Inga uppdrag matchar sökningen. Är databasen tom körs ingen insamling ännu.
          </Empty>
        )}
        {poster.map((u) => {
          const kvar = dagarKvar(u.job_ad?.application_deadline);
          const brannande =
            u.job_ad?.application_deadline != null &&
            new Date(u.job_ad.application_deadline).getTime() - Date.now() < 7 * 86_400_000 &&
            new Date(u.job_ad.application_deadline).getTime() > Date.now();
          return (
            <tr key={u.id} className="hover:bg-surface">
              <Td>
                <ScoreBadge score={u.match_score} />
              </Td>
              <Td>
                <Link href={`/uppdrag/${u.id}`} className="font-medium text-accent hover:underline">
                  {u.job_ad?.title ?? "Uppdrag"}
                </Link>
                {u.exclusion_status !== "PASS" && (
                  <span className="ml-2">
                    <VerdictBadge verdict={u.exclusion_status} />
                  </span>
                )}
                {u.job_ad?.occupation_label && (
                  <p className="mt-0.5 text-[0.75rem] text-muted">{u.job_ad.occupation_label}</p>
                )}
              </Td>
              <Td className="text-muted">{u.job_ad?.organisation_name ?? "–"}</Td>
              {visaTyp && (
                <Td>
                  <Badge>{KIND_TEXT[u.kind]}</Badge>
                  {u.job_ad?.employment_type && u.job_ad.employment_type !== "UNKNOWN" && (
                    <span className="ml-1">
                      <Badge>{EMPLOYMENT_TEXT[u.job_ad.employment_type]}</Badge>
                    </span>
                  )}
                </Td>
              )}
              <Td className="whitespace-nowrap text-muted">
                {u.job_ad?.workplace_municipality ?? u.job_ad?.workplace_region ?? "–"}
              </Td>
              {visaArvode && (
                <Td className="whitespace-nowrap text-muted">
                  {u.duration_months ? `${u.duration_months} mån` : "–"}
                  {u.fee_sek_per_hour ? ` · ${visaKronor(u.fee_sek_per_hour)}/tim` : ""}
                </Td>
              )}
              <Td className="whitespace-nowrap">
                {visaDatum(u.job_ad?.application_deadline)}
                {kvar && (
                  <span className="ml-2">
                    <Badge tone={brannande ? "review" : "neutral"}>{kvar}</Badge>
                  </span>
                )}
              </Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}
