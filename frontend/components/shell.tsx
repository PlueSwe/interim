// Ramen runt sidorna. Inloggningssidan far ingen sidomeny, eftersom det inte
// finns nagot att navigera till innan man ar inloggad.

"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Nav } from "./nav";

export function Shell({ children }: { children: ReactNode }) {
  const sokvag = usePathname();

  if (sokvag === "/login") {
    return <main className="min-h-screen">{children}</main>;
  }

  return (
    <div className="flex min-h-screen">
      <div className="sticky top-0 h-screen">
        <Nav />
      </div>
      <main className="min-w-0 flex-1 px-8 py-7">
        <div className="mx-auto max-w-[1400px]">{children}</div>
      </main>
    </div>
  );
}
