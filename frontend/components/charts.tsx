// De sex diagrammen i bestallningens avsnitt 10.
//
// Alla ar envariata: en kategori och ett antal. Darfor anvands en farg och
// inte en palett -- olika farger pa staplar som matar samma sak later som en
// skillnad som inte finns. Paletten nedan anvands bara dar kategorierna
// verkligen ar olika saker (organisationstyp).

"use client";

import type { ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ORG_TEXT } from "@/lib/format";
import type { ChartPoint, OrgType } from "@/lib/types";

const ACCENT = "#13506b";
const LINJE = "#e3e8ee";
const TEXT = "#5b6672";

// Kategorisk palett: urskiljbar i gratonad utskrift och for de vanligaste
// formerna av fargblindhet, tack vare att ljusheten skiljer sig stegvis.
const KATEGORI = ["#13506b", "#4d8ba6", "#8ab6c7", "#b9916a", "#7c6f9b", "#9aa5ae"];

const axel = { stroke: LINJE, tick: { fill: TEXT, fontSize: 11 }, tickLine: false };

function Verktygstips() {
  return (
    <Tooltip
      cursor={{ fill: "rgba(19,80,107,0.06)" }}
      contentStyle={{
        border: `1px solid ${LINJE}`,
        borderRadius: 6,
        fontSize: 12,
        boxShadow: "0 2px 10px rgba(21,25,30,0.08)",
        background: "#ffffff",
        color: "#15191e",
      }}
      labelStyle={{ color: TEXT, fontWeight: 500 }}
    />
  );
}

function Ram({
  titel,
  beskrivning,
  data,
  children,
  hojd = 220,
}: {
  titel: string;
  beskrivning?: string;
  data: unknown[];
  children: ReactNode;
  hojd?: number;
}) {
  return (
    <section className="rounded-lg border border-line bg-white p-4 shadow-card">
      <h3 className="text-[0.875rem] font-semibold text-ink">{titel}</h3>
      {beskrivning && <p className="mt-0.5 text-[0.75rem] text-muted">{beskrivning}</p>}
      <div className="mt-3" style={{ height: hojd }}>
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center rounded border border-dashed border-line text-[0.8125rem] text-muted">
            Inga data insamlade ännu
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            {children as React.ReactElement}
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}

/** Kapar langa myndighetsnamn sa att de inte tranger ut diagrammet. */
function kort(s: string | undefined, max = 26): string {
  if (!s) return "–";
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

export function AnnonserPerVecka({ data }: { data: ChartPoint[] }) {
  return (
    <Ram
      titel="Annonser per vecka"
      beskrivning="Insamlade annonser, grupperade på publiceringsvecka"
      data={data}
    >
      <AreaChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="gradAnnonser" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={ACCENT} stopOpacity={0.22} />
            <stop offset="100%" stopColor={ACCENT} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={LINJE} vertical={false} />
        <XAxis dataKey="period" {...axel} />
        <YAxis allowDecimals={false} {...axel} />
        <Verktygstips />
        <Area
          type="monotone"
          dataKey="count"
          name="Annonser"
          stroke={ACCENT}
          strokeWidth={2}
          fill="url(#gradAnnonser)"
        />
      </AreaChart>
    </Ram>
  );
}

export function PerOrganisationstyp({ data }: { data: ChartPoint[] }) {
  // Backend lamnar ut enum-vardet (STATE_AGENCY). Oversattningen hor hemma i
  // granssnittet, inte i ett diagram som visar "MUNICIPALITY" for en anvandare.
  const oversatt = data.map((d) => ({
    ...d,
    label: ORG_TEXT[d.label as OrgType] ?? d.label,
  }));
  return (
    <Ram
      titel="Fördelning per organisationstyp"
      beskrivning="Statlig myndighet, kommun, region, lärosäte"
      data={oversatt}
    >
      <PieChart>
        <Pie
          data={oversatt}
          dataKey="count"
          nameKey="label"
          innerRadius={44}
          outerRadius={78}
          paddingAngle={2}
          label={({ name, value }: { name?: string; value?: number }) => `${kort(name, 14)} ${value}`}
          labelLine={false}
          style={{ fontSize: 11 }}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={KATEGORI[i % KATEGORI.length]} stroke="#ffffff" strokeWidth={1.5} />
          ))}
        </Pie>
        <Verktygstips />
      </PieChart>
    </Ram>
  );
}

function LiggandeStaplar({
  titel,
  beskrivning,
  data,
  hojd,
}: {
  titel: string;
  beskrivning?: string;
  data: ChartPoint[];
  hojd?: number;
}) {
  const kapad = data.slice(0, 10).map((d) => ({ ...d, label: kort(d.label) }));
  return (
    <Ram
      titel={titel}
      beskrivning={beskrivning}
      data={kapad}
      hojd={hojd ?? Math.max(180, kapad.length * 26 + 30)}
    >
      <BarChart data={kapad} layout="vertical" margin={{ top: 0, right: 24, left: 4, bottom: 0 }}>
        <CartesianGrid stroke={LINJE} horizontal={false} />
        <XAxis type="number" allowDecimals={false} {...axel} />
        <YAxis type="category" dataKey="label" width={150} {...axel} />
        <Verktygstips />
        <Bar dataKey="count" name="Antal" fill={ACCENT} radius={[0, 3, 3, 0]} maxBarSize={16} />
      </BarChart>
    </Ram>
  );
}

export function RekryteringarPerMyndighet({ data }: { data: ChartPoint[] }) {
  return (
    <LiggandeStaplar
      titel="Rekryteringar per myndighet"
      beskrivning="De tio organisationer som annonserat flest chefstjänster"
      data={data}
    />
  );
}

export function PerFormedlare({ data }: { data: ChartPoint[] }) {
  return (
    <LiggandeStaplar
      titel="Uppdrag per förmedlare"
      beskrivning="Annonser där en förmedlare står som avsändare"
      data={data}
    />
  );
}

export function PerRegion({ data }: { data: ChartPoint[] }) {
  return (
    <LiggandeStaplar
      titel="Geografisk fördelning"
      beskrivning="Annonser per län"
      data={data}
    />
  );
}

export function TillsattningarOverTid({ data }: { data: ChartPoint[] }) {
  return (
    <Ram
      titel="Tillsättningar över tid"
      beskrivning="Verifierade tillsättningar per månad, räknat på beslutsdatum"
      data={data}
    >
      <BarChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={LINJE} vertical={false} />
        <XAxis dataKey="period" {...axel} />
        <YAxis allowDecimals={false} {...axel} />
        <Verktygstips />
        <Bar dataKey="count" name="Tillsättningar" fill={ACCENT} radius={[3, 3, 0, 0]} maxBarSize={28} />
      </BarChart>
    </Ram>
  );
}
