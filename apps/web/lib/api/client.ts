import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

export type Role = "SOURCING" | "QUOTE_ENGINEER" | "ENGINEERING" | "MANAGER" | "VIEWER";

const ROLE_KEY = "quotelens.role";

export function getRole(): Role {
  if (typeof window === "undefined") return "VIEWER";
  try {
    return (window.localStorage.getItem(ROLE_KEY) as Role | null) ?? "QUOTE_ENGINEER";
  } catch {
    return "QUOTE_ENGINEER";
  }
}

export function setRole(role: Role): void {
  try {
    window.localStorage.setItem(ROLE_KEY, role);
  } catch {
    /* storage unavailable: the role falls back per request */
  }
}

/** Error raised for non-2xx responses, carrying the API's error envelope. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

const roleHeader: Middleware = {
  onRequest({ request }) {
    request.headers.set("X-Demo-Role", getRole());
    return request;
  },
};

/** Same-origin client: the Next.js route handler proxies /api/v1/* to the API service. */
export const api = createClient<paths>({ baseUrl: "" });
api.use(roleHeader);

type Envelope = { error?: { code?: string; message?: string; details?: Record<string, unknown> } };

/** Unwrap an openapi-fetch result: return data or throw ApiError with the API's message. */
export async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await promise;
  if (response.ok && data !== undefined) return data;
  if (response.ok && response.status === 204) return undefined as T;
  const envelope = (error ?? {}) as Envelope;
  throw new ApiError(
    response.status,
    envelope.error?.code ?? "ERROR",
    envelope.error?.message ?? `Request failed (${response.status})`,
    envelope.error?.details ?? {},
  );
}
