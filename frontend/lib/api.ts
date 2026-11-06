// API-klient.
//
// Anropen gar till /api/v1/... pa samma origin; next.config.ts skickar vidare
// till FastAPI. Inloggningstoken ligger i en httpOnly-cookie som webblasaren
// satter sjalv, sa det finns ingen token i den har filen och ingenting att
// lagra i localStorage.

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

const BAS = "/api/v1";

async function anrop<T>(
  sokvag: string,
  init?: RequestInit & { params?: Record<string, unknown> },
): Promise<T> {
  const { params, ...rest } = init ?? {};
  let url = `${BAS}${sokvag}`;
  if (params) {
    const q = new URLSearchParams();
    for (const [nyckel, varde] of Object.entries(params)) {
      if (varde === undefined || varde === null || varde === "") continue;
      q.set(nyckel, String(varde));
    }
    const s = q.toString();
    if (s) url += `?${s}`;
  }

  const svar = await fetch(url, {
    ...rest,
    credentials: "same-origin",
    headers: {
      ...(rest.body ? { "Content-Type": "application/json" } : {}),
      ...(rest.headers ?? {}),
    },
  });

  if (svar.status === 204) return undefined as T;

  const text = await svar.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!svar.ok) {
    // FastAPI lagger felet i detail, antingen som strang eller som en lista
    // med valideringsfel. Bada ska bli en mening som gar att visa.
    const d = (data as { detail?: unknown })?.detail;
    let meddelande: string;
    if (typeof d === "string") {
      meddelande = d;
    } else if (Array.isArray(d)) {
      meddelande = d
        .map((f) => {
          const rad = f as { loc?: unknown[]; msg?: string };
          const falt = Array.isArray(rad.loc) ? rad.loc.slice(1).join(".") : "";
          return falt ? `${falt}: ${rad.msg}` : (rad.msg ?? "ogiltigt värde");
        })
        .join("; ");
    } else {
      meddelande = `fel ${svar.status}`;
    }
    throw new ApiError(svar.status, meddelande);
  }

  return data as T;
}

export const api = {
  get: <T>(sokvag: string, params?: Record<string, unknown>) =>
    anrop<T>(sokvag, { method: "GET", params }),

  post: <T>(sokvag: string, kropp?: unknown, params?: Record<string, unknown>) =>
    anrop<T>(sokvag, {
      method: "POST",
      params,
      body: kropp === undefined ? undefined : JSON.stringify(kropp),
    }),

  patch: <T>(sokvag: string, kropp: unknown) =>
    anrop<T>(sokvag, { method: "PATCH", body: JSON.stringify(kropp) }),

  del: <T>(sokvag: string, params?: Record<string, unknown>) =>
    anrop<T>(sokvag, { method: "DELETE", params }),
};
