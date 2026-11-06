"use client";

import Link from "next/link";

import {
  AnnonserPerVecka,
  PerFormedlare,
  PerOrganisationstyp,
  PerRegion,
  RekryteringarPerMyndighet,
  TillsattningarOverTid,
} from "@/components/charts";
import {
  Badge,
  Card,
  Empty,
  ErrorBox,
  ExternalLink,
  Kpi,
  Note,
  PageHeader,
  ScoreBadge,
  Spinner,
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { dagarKvar, visaDatum, visaDatumTid, visaTal } from "@/lib/format";
import type { Dashboard } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function Oversikt() {
  const { data, fel, laddar, ladda } = useApi<Dashboard>("/dashboard");

  if (fel) return <ErrorBox error={fel} onRetry={ladda} />;
  if (laddar || !data) return <Spinner />;

  const tomtSystem =
    data.new_opportunities_7d === 0 &&
    data.active_interim === 0 &&
    data.permanent_positions === 0 &&
    data.charts.ads_per_week.length === 0;

  return (
    <>
      <PageHeader
        title="Översikt"
        description="Alla tal är räknade på insamlade data, inte på hela marknaden. Täckningen framgår under Administration."
      />

      {tomtSystem && (
        <div className="mb-6">
          <Note>
            Databasen är tom. Kör en insamling under{" "}
            <Link href="/administration" className="text-accent underline underline-offset-2">
              Administration
            </Link>{" "}
            eller importera annonser manuellt. Inga exempeldata läggs in automatiskt – siffrorna här
            ska aldrig vara något annat än det som faktiskt samlats in.
          </Note>
        </div>
      )}

      {/* --- Nyckeltal --- */}
      <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <Kpi
          label="Nya uppdrag (7 dagar)"
          value={visaTal(data.new_opportunities_7d)}
          href="/uppdrag"
        />
        <Kpi label="Aktiva interimuppdrag" value={visaTal(data.active_interim)} href="/uppdrag" />
        <Kpi
          label="Fasta myndighetstjänster"
          value={visaTal(data.permanent_positions)}
          href="/myndighetstjanster"
        />
        <Kpi
          label="Stängda rekryteringar"
          value={visaTal(data.recruitments_closed)}
          hint="Ansökan stängd, tillsättning ännu inte klar"
          href="/tillsattningar"
        />
        <Kpi
          label="Verifierade tillsättningar"
          value={visaTal(data.appointments_verified)}
          hint="Nivå 1–3. Lägre nivåer räknas inte som verifierade"
          href="/tillsattningar"
        />
      </div>

      <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <Kpi
          label="Identifierade, ej verifierade"
          value={visaTal(data.appointments_identified)}
          tone="review"
          href="/tillsattningar?status=APPOINTMENT_IDENTIFIED"
        />
        <Kpi
          label="Olösta tillsättningar"
          value={visaTal(data.appointments_unresolved)}
          hint="Annonsen är borta men beslutet är inte hittat"
          tone="review"
          href="/tillsattningar"
        />
        <Kpi
          label="Begäranden att godkänna"
          value={visaTal(data.requests_awaiting_approval)}
          hint="Skickas aldrig utan ditt godkännande"
          tone="review"
          href="/tillsattningar"
        />
        <Kpi
          label="Kräver granskning"
          value={visaTal(data.review_required_count)}
          hint="Osäkert om personkontroll krävs"
          tone="review"
          href="/exkluderade"
        />
        <Kpi
          label="Exkluderade"
          value={visaTal(data.excluded_count)}
          hint="Kräver säkerhetsprövning eller registerkontroll"
          tone="excluded"
          href="/exkluderade"
        />
      </div>

      {/* --- Diagram --- */}
      <div className="mb-8 grid gap-4 lg:grid-cols-2">
        <AnnonserPerVecka data={data.charts.ads_per_week} />
        <PerOrganisationstyp data={data.charts.by_org_type} />
        <RekryteringarPerMyndighet data={data.charts.recruitments_per_authority} />
        <TillsattningarOverTid data={data.charts.appointments_over_time} />
        <PerFormedlare data={data.charts.by_recruiter} />
        <PerRegion data={data.charts.by_region} />
      </div>

      {/* --- Listor --- */}
      <div className="grid gap-4 xl:grid-cols-2">
        <Card
          title="Högst matchning"
          description="Poängen är en uppskattning mot din profil, inte ett omdöme om kraven är uppfyllda"
        >
          <Table>
            <thead>
              <tr>
                <Th>Poäng</Th>
                <Th>Uppdrag</Th>
                <Th>Organisation</Th>
                <Th>Sista dag</Th>
              </tr>
            </thead>
            <tbody>
              {data.top_matches.length === 0 && <Empty colSpan={4}>Inga matchningar ännu</Empty>}
              {data.top_matches.map((u) => (
                <tr key={u.id} className="hover:bg-surface">
                  <Td>
                    <ScoreBadge score={u.match_score} />
                  </Td>
                  <Td>
                    <Link href={`/uppdrag/${u.id}`} className="font-medium text-accent hover:underline">
                      {u.job_ad?.title ?? "Uppdrag"}
                    </Link>
                  </Td>
                  <Td className="text-muted">{u.job_ad?.organisation_name ?? "–"}</Td>
                  <Td className="whitespace-nowrap text-muted">
                    {visaDatum(u.job_ad?.application_deadline)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>

        <Card title="Deadline närmar sig">
          <Table>
            <thead>
              <tr>
                <Th>Uppdrag</Th>
                <Th>Organisation</Th>
                <Th>Kvar</Th>
              </tr>
            </thead>
            <tbody>
              {data.upcoming_deadlines.length === 0 && (
                <Empty colSpan={3}>Inga deadlines inom kort</Empty>
              )}
              {data.upcoming_deadlines.map((u) => (
                <tr key={u.id} className="hover:bg-surface">
                  <Td>
                    <Link href={`/uppdrag/${u.id}`} className="font-medium text-accent hover:underline">
                      {u.job_ad?.title ?? "Uppdrag"}
                    </Link>
                  </Td>
                  <Td className="text-muted">{u.job_ad?.organisation_name ?? "–"}</Td>
                  <Td className="whitespace-nowrap">
                    <Badge tone="review">{dagarKvar(u.job_ad?.application_deadline) ?? "–"}</Badge>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>

        <Card
          title="Senast verifierade tillsättningar"
          description="Endast nivå 1–3. Pågående ärenden finns under Tillsättningar."
        >
          <Table>
            <thead>
              <tr>
                <Th>Befattning</Th>
                <Th>Myndighet</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {data.recent_appointments.length === 0 && (
                <Empty colSpan={3}>Ingen tillsättning är verifierad ännu</Empty>
              )}
              {data.recent_appointments.map((a) => (
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
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>

        <Card title="Ramavtal som löper ut">
          <Table>
            <thead>
              <tr>
                <Th>Avtal</Th>
                <Th>Område</Th>
                <Th>Giltigt till</Th>
              </tr>
            </thead>
            <tbody>
              {data.expiring_agreements.length === 0 && (
                <Empty colSpan={3}>Inga ramavtal registrerade</Empty>
              )}
              {data.expiring_agreements.map((r) => (
                <tr key={r.id} className="hover:bg-surface">
                  <Td>
                    {r.url ? <ExternalLink href={r.url}>{r.name}</ExternalLink> : r.name}
                  </Td>
                  <Td className="text-muted">{r.area ?? "–"}</Td>
                  <Td className="whitespace-nowrap">
                    {visaDatum(r.valid_to)}
                    {r.days_left !== null && (
                      <span className="ml-2 text-[0.75rem] text-muted">{r.days_left} d</span>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      </div>

      {data.failing_sources.length > 0 && (
        <div className="mt-4">
          <Card
            title="Källor med fel"
            description="En källa som slutat svara ska syna, inte tystna"
          >
            <Table>
              <thead>
                <tr>
                  <Th>Källa</Th>
                  <Th>Senast lyckad</Th>
                  <Th>Fel i rad</Th>
                  <Th>Senaste fel</Th>
                </tr>
              </thead>
              <tbody>
                {data.failing_sources.map((k) => (
                  <tr key={k.key}>
                    <Td className="font-medium">{k.name}</Td>
                    <Td className="whitespace-nowrap text-muted">{visaDatumTid(k.last_success_at)}</Td>
                    <Td className="tabular-nums">{k.consecutive_failures}</Td>
                    <Td className="max-w-md truncate text-[0.8125rem] text-excluded" title={k.last_error ?? ""}>
                      {k.last_error ?? "–"}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}
