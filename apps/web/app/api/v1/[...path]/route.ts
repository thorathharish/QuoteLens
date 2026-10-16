/**
 * Backend-for-frontend proxy: /api/v1/* → API service. Streams bodies both ways so SSE
 * (copilot) and file downloads (XLSX) pass through untouched.
 *
 * On Cloud Run the API is private; when API_AUDIENCE is set, requests carry a Google ID
 * token for this service's account, fetched from the metadata server and cached.
 */

export const dynamic = "force-dynamic";

// 127.0.0.1, not "localhost": other local services (Docker/WSL) may own [::1]:8080.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8080";
const API_AUDIENCE = process.env.API_AUDIENCE;
const FORWARDED_REQUEST_HEADERS = ["content-type", "accept", "x-demo-role", "x-request-id", "idempotency-key"];
const FORWARDED_RESPONSE_HEADERS = ["content-type", "content-disposition", "x-request-id", "cache-control"];

let cachedToken: { value: string; expires: number } | null = null;

async function identityToken(): Promise<string | null> {
  if (!API_AUDIENCE) return null;
  if (cachedToken && cachedToken.expires > Date.now()) return cachedToken.value;
  const url =
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity" +
    `?audience=${encodeURIComponent(API_AUDIENCE)}`;
  const response = await fetch(url, { headers: { "Metadata-Flavor": "Google" }, cache: "no-store" });
  if (!response.ok) throw new Error(`Identity token request failed: ${response.status}`);
  const value = await response.text();
  cachedToken = { value, expires: Date.now() + 45 * 60 * 1000 }; // tokens live 60 minutes
  return value;
}

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const incoming = new URL(request.url);
  const target = `${API_BASE_URL}/api/v1/${path.map(encodeURIComponent).join("/")}${incoming.search}`;

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const token = await identityToken();
    if (token) headers.set("authorization", `Bearer ${token}`);
  } catch {
    return Response.json(
      { error: { code: "UPSTREAM_UNAVAILABLE", message: "Could not authenticate to the API", details: {} } },
      { status: 503 },
    );
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // Required by Node's fetch to stream a request body.
      ...(hasBody ? { duplex: "half" } : {}),
      cache: "no-store",
    } as RequestInit);
  } catch {
    return Response.json(
      { error: { code: "UPSTREAM_UNAVAILABLE", message: "The API service is not reachable", details: {} } },
      { status: 503 },
    );
  }

  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export { proxy as DELETE, proxy as GET, proxy as PATCH, proxy as POST, proxy as PUT };
