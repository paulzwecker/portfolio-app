import { isHealthResponse } from "@/lib/health";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const headers = { "Cache-Control": "no-store" };

/** Keep the backend address and any connection errors on the server. */
export async function GET() {
  try {
    const baseUrl = process.env.API_BASE_URL;
    if (!baseUrl) throw new Error("API_BASE_URL is missing.");
    const endpoint = new URL("health/ready", `${baseUrl.replace(/\/$/, "")}/`);
    if (!["http:", "https:"].includes(endpoint.protocol)) {
      throw new Error("Invalid API protocol.");
    }
    const upstream = await fetch(endpoint, {
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
      redirect: "error",
    });
    const health: unknown = await upstream.json();
    if (
      !isHealthResponse(health) ||
      (health.status === "ok"
        ? upstream.status !== 200
        : upstream.status !== 503)
    ) {
      throw new Error("Invalid health response.");
    }
    return Response.json(
      {
        status: health.status,
        database: health.database,
        schema: health.schema,
        checked_at: health.checked_at,
      },
      { status: upstream.status, headers },
    );
  } catch {
    return Response.json(
      {
        detail:
          "The API is unavailable. Check the development services and retry.",
      },
      { status: 503, headers },
    );
  }
}
