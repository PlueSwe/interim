// Sidomeny. De tio posterna i bestallningens avsnitt 10, i samma ordning.

"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { User } from "@/lib/types";

const MENY: Array<{ href: string; etikett: string; grupp?: string }> = [
  { href: "/", etikett: "Översikt" },
  { href: "/uppdrag", etikett: "Uppdrag", grupp: "Bevakning" },
  { href: "/myndighetstjanster", etikett: "Myndighetstjänster" },
  { href: "/tillsattningar", etikett: "Tillsättningar" },
  { href: "/marknadsanalys", etikett: "Marknadsanalys", grupp: "Analys" },
  { href: "/organisationer", etikett: "Organisationer" },
  { href: "/ramavtal", etikett: "Ramavtal" },
  { href: "/formedlare", etikett: "Förmedlare" },
  { href: "/exkluderade", etikett: "Exkluderade uppdrag", grupp: "Kontroll" },
  { href: "/administration", etikett: "Administration" },
];

export function Nav() {
  const sokvag = usePathname();
  const router = useRouter();
  const [anvandare, setAnvandare] = useState<User | null>(null);

  useEffect(() => {
    api.get<User>("/auth/me").then(setAnvandare).catch(() => setAnvandare(null));
  }, [sokvag]);

  async function loggaUt() {
    try {
      await api.post("/auth/logout");
    } finally {
      router.push("/login");
    }
  }

  return (
    <nav className="flex h-full w-60 shrink-0 flex-col border-r border-line bg-white">
      <div className="border-b border-line px-5 py-4">
        <p className="text-[0.9375rem] font-semibold tracking-[-0.01em] text-ink">Interim Radar</p>
        <p className="mt-0.5 text-[0.75rem] text-muted">Chefsuppdrag i offentlig sektor</p>
      </div>

      <ul className="flex-1 overflow-y-auto px-2 py-3">
        {MENY.map((post) => {
          const aktiv = post.href === "/" ? sokvag === "/" : sokvag.startsWith(post.href);
          return (
            <li key={post.href}>
              {post.grupp && (
                <p className="mb-1 mt-4 px-3 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted/80">
                  {post.grupp}
                </p>
              )}
              <Link
                href={post.href}
                className={clsx(
                  "block rounded-md px-3 py-1.5 text-[0.875rem] transition-colors",
                  aktiv
                    ? "bg-accent-soft font-medium text-accent"
                    : "text-ink/85 hover:bg-surface hover:text-ink",
                )}
              >
                {post.etikett}
              </Link>
            </li>
          );
        })}
      </ul>

      <div className="border-t border-line px-5 py-3">
        {anvandare ? (
          <>
            <p className="truncate text-[0.8125rem] text-ink" title={anvandare.email}>
              {anvandare.email}
            </p>
            <p className="text-[0.75rem] text-muted">{anvandare.role}</p>
            <button
              onClick={loggaUt}
              className="mt-2 text-[0.8125rem] text-accent hover:underline"
            >
              Logga ut
            </button>
          </>
        ) : (
          <Link href="/login" className="text-[0.8125rem] text-accent hover:underline">
            Logga in
          </Link>
        )}
      </div>
    </nav>
  );
}
