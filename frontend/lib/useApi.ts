// Datahamtning.
//
// Avsiktligt litet: en hook som halls i react-state, utan react-query. Sidorna
// hamtar en resurs var och behover ingen delad cache. Det som daremot behovs
// ar att ett 401 alltid leder till inloggningssidan, i stallet for ett tomt
// grannsnitt, och det sker pa ett stalle har.

"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "./api";

export interface Resultat<T> {
  data: T | null;
  fel: string | null;
  laddar: boolean;
  ladda: () => void;
}

export function useApi<T>(
  sokvag: string | null,
  params?: Record<string, unknown>,
): Resultat<T> {
  const router = useRouter();
  const [data, setData] = useState<T | null>(null);
  const [fel, setFel] = useState<string | null>(null);
  const [laddar, setLaddar] = useState(sokvag !== null);

  // Nyckeln gor att hooken kor om nar ett filtervarde andras, utan att
  // params-objektets identitet spelar in.
  const nyckel = params ? JSON.stringify(params) : "";

  const ladda = useCallback(() => {
    if (sokvag === null) return;
    setLaddar(true);
    setFel(null);
    api
      .get<T>(sokvag, nyckel ? (JSON.parse(nyckel) as Record<string, unknown>) : undefined)
      .then((d) => setData(d))
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 401) {
          router.push("/login");
          return;
        }
        setFel(e instanceof Error ? e.message : "okänt fel");
      })
      .finally(() => setLaddar(false));
  }, [sokvag, nyckel, router]);

  useEffect(ladda, [ladda]);

  return { data, fel, laddar, ladda };
}

/** Mutation med fel som gar att visa i granssnittet. */
export function useAction() {
  const router = useRouter();
  const [arbetar, setArbetar] = useState(false);
  const [fel, setFel] = useState<string | null>(null);

  const kor = useCallback(
    async <T,>(arbete: () => Promise<T>): Promise<T | null> => {
      setArbetar(true);
      setFel(null);
      try {
        return await arbete();
      } catch (e: unknown) {
        if (e instanceof ApiError && e.status === 401) {
          router.push("/login");
          return null;
        }
        setFel(e instanceof Error ? e.message : "okänt fel");
        return null;
      } finally {
        setArbetar(false);
      }
    },
    [router],
  );

  return { kor, arbetar, fel, rensaFel: () => setFel(null) };
}
