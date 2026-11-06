// Avancerad sokning. Filtren i bestallningens avsnitt 11, mot
// GET /api/v1/opportunities.
//
// Filtren ligger i URL:ens query, inte bara i react-state. Det gor en sokning
// delbar och overlever en omladdning, vilket ar vad man vill nar man har
// stallt in ett dussin falt.

"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Button, Field, Input, Select } from "./ui";
import {
  EMPLOYMENT_TEXT,
  KIND_TEXT,
  OPPORTUNITY_STATUS_TEXT,
  ORG_TEXT,
  ROLE_TEXT,
  VERDICT_TEXT,
} from "@/lib/format";
import { api } from "@/lib/api";
import type { Provider } from "@/lib/types";

export interface Filter {
  q?: string;
  kind?: string;
  status?: string;
  exclusion?: string;
  employment_type?: string;
  role_family?: string;
  org_type?: string;
  municipality?: string;
  region?: string;
  recruiter_id?: string;
  min_score?: string;
  max_score?: string;
  min_duration?: string;
  max_duration?: string;
  min_fee?: string;
  deadline_before?: string;
  deadline_after?: string;
  published_after?: string;
  include_excluded?: string;
  sort?: string;
}

export const TOMT_FILTER: Filter = { sort: "score" };

const FALT: Array<keyof Filter> = [
  "q",
  "kind",
  "status",
  "exclusion",
  "employment_type",
  "role_family",
  "org_type",
  "municipality",
  "region",
  "recruiter_id",
  "min_score",
  "max_score",
  "min_duration",
  "max_duration",
  "min_fee",
  "deadline_before",
  "deadline_after",
  "published_after",
  "include_excluded",
  "sort",
];

export function filterFranUrl(params: URLSearchParams): Filter {
  const f: Filter = {};
  for (const falt of FALT) {
    const v = params.get(falt);
    if (v) f[falt] = v;
  }
  return { ...TOMT_FILTER, ...f };
}

interface SparadSokning {
  id: string;
  name: string;
  filters: Record<string, string>;
}

export function Filters({
  varde,
  onChange,
  visaSparade = true,
}: {
  varde: Filter;
  onChange: (f: Filter) => void;
  visaSparade?: boolean;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const [utokad, setUtokad] = useState(false);
  const [formedlare, setFormedlare] = useState<Provider[]>([]);
  const [sparade, setSparade] = useState<SparadSokning[]>([]);
  const [nyttNamn, setNyttNamn] = useState("");

  useEffect(() => {
    api.get<Provider[]>("/providers").then(setFormedlare).catch(() => setFormedlare([]));
    if (visaSparade) {
      api.get<SparadSokning[]>("/saved-searches").then(setSparade).catch(() => setSparade([]));
    }
  }, [visaSparade]);

  const antalAktiva = useMemo(
    () => FALT.filter((f) => f !== "sort" && varde[f]).length,
    [varde],
  );

  function satt(falt: keyof Filter, v: string) {
    const nytt = { ...varde, [falt]: v || undefined };
    onChange(nytt);
    // Spegla i URL:en sa att sokningen gar att kopiera och dela.
    const q = new URLSearchParams();
    for (const f of FALT) {
      const x = nytt[f];
      if (x) q.set(f, x);
    }
    router.replace(q.toString() ? `?${q.toString()}` : "?", { scroll: false });
  }

  function nollstall() {
    onChange({ ...TOMT_FILTER });
    router.replace("?", { scroll: false });
  }

  async function spara() {
    const namn = nyttNamn.trim();
    if (!namn) return;
    const filters: Record<string, string> = {};
    for (const f of FALT) if (varde[f]) filters[f] = varde[f] as string;
    await api.post("/saved-searches", { name: namn, filters });
    setNyttNamn("");
    setSparade(await api.get<SparadSokning[]>("/saved-searches"));
  }

  function anvand(s: SparadSokning) {
    const f = { ...TOMT_FILTER, ...s.filters } as Filter;
    onChange(f);
    const q = new URLSearchParams(s.filters);
    router.replace(`?${q.toString()}`, { scroll: false });
  }

  async function taBort(id: string) {
    await api.del(`/saved-searches/${id}`);
    setSparade(await api.get<SparadSokning[]>("/saved-searches"));
  }

  // Lasning av params behovs for att komponenten ska rendera om vid
  // bakatnavigering; vardet anvands inte direkt.
  void params;

  return (
    <div className="mb-4 rounded-lg border border-line bg-white shadow-card">
      <div className="flex flex-wrap items-end gap-3 p-4">
        <div className="min-w-[16rem] flex-1">
          <Field label="Fritext">
            <Input
              placeholder="Titel, beskrivning eller organisation"
              value={varde.q ?? ""}
              onChange={(e) => satt("q", e.target.value)}
            />
          </Field>
        </div>

        <div className="w-44">
          <Field label="Roll">
            <Select value={varde.role_family ?? ""} onChange={(e) => satt("role_family", e.target.value)}>
              <option value="">Alla roller</option>
              {Object.entries(ROLE_TEXT).map(([v, t]) => (
                <option key={v} value={v}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="w-40">
          <Field label="Anställningsform">
            <Select
              value={varde.employment_type ?? ""}
              onChange={(e) => satt("employment_type", e.target.value)}
            >
              <option value="">Alla former</option>
              {Object.entries(EMPLOYMENT_TEXT).map(([v, t]) => (
                <option key={v} value={v}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="w-36">
          <Field label="Sortering">
            <Select value={varde.sort ?? "score"} onChange={(e) => satt("sort", e.target.value)}>
              <option value="score">Poäng</option>
              <option value="published">Publicerad</option>
              <option value="deadline">Sista dag</option>
              <option value="created">Inläst</option>
            </Select>
          </Field>
        </div>

        <Button onClick={() => setUtokad(!utokad)}>
          {utokad ? "Färre filter" : "Fler filter"}
          {antalAktiva > 0 && (
            <span className="ml-1 rounded bg-accent-soft px-1 text-[0.6875rem] text-accent">
              {antalAktiva}
            </span>
          )}
        </Button>
        {antalAktiva > 0 && (
          <Button variant="ghost" onClick={nollstall}>
            Nollställ
          </Button>
        )}
      </div>

      {utokad && (
        <div className="grid gap-3 border-t border-line bg-surface p-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Typ av uppdrag">
            <Select value={varde.kind ?? ""} onChange={(e) => satt("kind", e.target.value)}>
              <option value="">Alla typer</option>
              {Object.entries(KIND_TEXT).map(([v, t]) => (
                <option key={v} value={v}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Organisationstyp">
            <Select value={varde.org_type ?? ""} onChange={(e) => satt("org_type", e.target.value)}>
              <option value="">Alla</option>
              {Object.entries(ORG_TEXT).map(([v, t]) => (
                <option key={v} value={v}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Kommun">
            <Input
              value={varde.municipality ?? ""}
              onChange={(e) => satt("municipality", e.target.value)}
              placeholder="t.ex. Stockholm"
            />
          </Field>

          <Field label="Län">
            <Input
              value={varde.region ?? ""}
              onChange={(e) => satt("region", e.target.value)}
              placeholder="t.ex. Skåne län"
            />
          </Field>

          <Field label="Förmedlare">
            <Select
              value={varde.recruiter_id ?? ""}
              onChange={(e) => satt("recruiter_id", e.target.value)}
            >
              <option value="">Alla förmedlare</option>
              {formedlare.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Poäng, lägst">
            <Input
              type="number"
              min={0}
              max={100}
              value={varde.min_score ?? ""}
              onChange={(e) => satt("min_score", e.target.value)}
            />
          </Field>

          <Field label="Poäng, högst">
            <Input
              type="number"
              min={0}
              max={100}
              value={varde.max_score ?? ""}
              onChange={(e) => satt("max_score", e.target.value)}
            />
          </Field>

          <Field label="Arvode, lägst (kr/tim)">
            <Input
              type="number"
              min={0}
              value={varde.min_fee ?? ""}
              onChange={(e) => satt("min_fee", e.target.value)}
            />
          </Field>

          <Field label="Längd, minst (mån)">
            <Input
              type="number"
              min={0}
              value={varde.min_duration ?? ""}
              onChange={(e) => satt("min_duration", e.target.value)}
            />
          </Field>

          <Field label="Längd, högst (mån)">
            <Input
              type="number"
              min={0}
              value={varde.max_duration ?? ""}
              onChange={(e) => satt("max_duration", e.target.value)}
            />
          </Field>

          <Field label="Sista dag efter">
            <Input
              type="date"
              value={varde.deadline_after ?? ""}
              onChange={(e) => satt("deadline_after", e.target.value)}
            />
          </Field>

          <Field label="Sista dag före">
            <Input
              type="date"
              value={varde.deadline_before ?? ""}
              onChange={(e) => satt("deadline_before", e.target.value)}
            />
          </Field>

          <Field label="Publicerad efter">
            <Input
              type="date"
              value={varde.published_after ?? ""}
              onChange={(e) => satt("published_after", e.target.value)}
            />
          </Field>

          <Field label="Exkluderingsstatus">
            <Select value={varde.exclusion ?? ""} onChange={(e) => satt("exclusion", e.target.value)}>
              <option value="">Godkända och granskningsfall</option>
              {Object.entries(VERDICT_TEXT).map(([v, t]) => (
                <option key={v} value={v}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Status">
            <Select value={varde.status ?? ""} onChange={(e) => satt("status", e.target.value)}>
              <option value="">Alla</option>
              {Object.entries(OPPORTUNITY_STATUS_TEXT).map(([v, t]) => (
                <option key={v} value={v}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="Visa exkluderade"
            hint="Av som standard. Ett filter man inte kan se in i slutar man lita på."
          >
            <Select
              value={varde.include_excluded ?? ""}
              onChange={(e) => satt("include_excluded", e.target.value)}
            >
              <option value="">Nej</option>
              <option value="true">Ja</option>
            </Select>
          </Field>
        </div>
      )}

      {visaSparade && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3">
          <span className="text-[0.75rem] font-medium uppercase tracking-wide text-muted">
            Sparade sökningar
          </span>
          {sparade.length === 0 && <span className="text-[0.8125rem] text-muted">inga ännu</span>}
          {sparade.map((s) => (
            <span
              key={s.id}
              className="inline-flex items-center gap-1 rounded border border-line bg-surface pl-2 text-[0.8125rem]"
            >
              <button onClick={() => anvand(s)} className="py-1 text-accent hover:underline">
                {s.name}
              </button>
              <button
                onClick={() => taBort(s.id)}
                title="Ta bort"
                className="px-1.5 py-1 text-muted hover:text-excluded"
              >
                ×
              </button>
            </span>
          ))}
          <span className="ml-auto flex items-center gap-2">
            <Input
              placeholder="Namn på sökning"
              value={nyttNamn}
              onChange={(e) => setNyttNamn(e.target.value)}
              className="w-44"
            />
            <Button onClick={spara} disabled={!nyttNamn.trim()}>
              Spara
            </Button>
          </span>
        </div>
      )}
    </div>
  );
}
