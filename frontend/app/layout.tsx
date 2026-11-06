import type { Metadata } from "next";

import { Shell } from "@/components/shell";

import "./globals.css";

export const metadata: Metadata = {
  title: "Interim Radar",
  description:
    "Privat bevakning av svenska chefsrekryteringar, interimuppdrag och offentliga upphandlingar.",
  // Privat verktyg. Ska inte indexeras ens om det nagon gang ligger oppet.
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="sv">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
