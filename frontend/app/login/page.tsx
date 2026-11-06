"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, ErrorBox, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction } from "@/lib/useApi";

export default function Login() {
  const router = useRouter();
  const { kor, arbetar, fel } = useAction();
  const [epost, setEpost] = useState("");
  const [losenord, setLosenord] = useState("");

  async function skicka(e: React.FormEvent) {
    e.preventDefault();
    const resultat = await kor(() =>
      api.post("/auth/login", { email: epost, password: losenord }),
    );
    if (resultat !== null) {
      router.push("/");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6">
          <h1 className="text-[1.25rem] font-semibold tracking-[-0.01em] text-ink">Interim Radar</h1>
          <p className="mt-1 text-[0.875rem] text-muted">
            Privat verktyg. Ingen registrering – konton läggs upp av administratör.
          </p>
        </div>

        <form
          onSubmit={skicka}
          className="space-y-4 rounded-lg border border-line bg-white p-5 shadow-card"
        >
          <Field label="E-postadress">
            <Input
              type="email"
              value={epost}
              onChange={(e) => setEpost(e.target.value)}
              autoComplete="username"
              required
              autoFocus
            />
          </Field>

          <Field label="Lösenord">
            <Input
              type="password"
              value={losenord}
              onChange={(e) => setLosenord(e.target.value)}
              autoComplete="current-password"
              required
            />
          </Field>

          {fel && <ErrorBox error={fel} />}

          <Button type="submit" variant="primary" disabled={arbetar} className="w-full justify-center">
            {arbetar ? "Loggar in…" : "Logga in"}
          </Button>
        </form>

        <p className="mt-4 text-[0.75rem] leading-relaxed text-muted">
          Sessionen hålls i en httpOnly-cookie. Den går inte att läsa från JavaScript och lagras
          inte i webbläsarens localStorage.
        </p>
      </div>
    </div>
  );
}
