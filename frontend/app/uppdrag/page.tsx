"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Filters, type Filter, filterFranUrl } from "@/components/filters";
import { OpportunityTable } from "@/components/opportunity-table";
import { Card, ErrorBox, PageHeader, Pagination, Spinner } from "@/components/ui";
import { visaTal } from "@/lib/format";
import type { Opportunity, Page } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const PER_SIDA = 50;

function Innehall() {
  const params = useSearchParams();
  const [filter, setFilter] = useState<Filter>(() => filterFranUrl(params));
  const [offset, setOffset] = useState(0);

  const { data, fel, laddar, ladda } = useApi<Page<Opportunity>>("/opportunities", {
    ...filter,
    limit: PER_SIDA,
    offset,
  });

  return (
    <>
      <PageHeader
        title="Uppdrag"
        description="Interim- och konsultuppdrag, avrop och upphandlingar. Exkluderade uppdrag ligger i en egen vy och blandas inte in här."
      />

      <Filters
        varde={filter}
        onChange={(f) => {
          setFilter(f);
          setOffset(0);
        }}
      />

      {fel && <ErrorBox error={fel} onRetry={ladda} />}

      {!fel && (
        <Card
          title={data ? `${visaTal(data.total)} uppdrag` : "Uppdrag"}
          description="Poängen är en uppskattning mot din profil. Den säger inget om att kraven är uppfyllda."
        >
          {laddar && !data ? (
            <Spinner />
          ) : (
            <>
              <OpportunityTable poster={data?.items ?? []} />
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
      )}
    </>
  );
}

export default function Uppdrag() {
  return (
    <Suspense fallback={<Spinner />}>
      <Innehall />
    </Suspense>
  );
}
