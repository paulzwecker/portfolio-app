import { timingSafeEqual } from "node:crypto";

const challengeHeaders = {
  "Cache-Control": "no-store",
  "WWW-Authenticate": 'Basic realm="Portfolio Research", charset="UTF-8"',
};

/** Enforce the shared development/preview gate inside route handlers too. */
export function webAccessRejection(request: Request): Response | null {
  if (process.env.NODE_ENV !== "production") return null;

  const username = process.env.WEB_ACCESS_USERNAME;
  const password = process.env.WEB_ACCESS_PASSWORD;
  if (!username || !password) {
    return new Response("Remote access protection is not configured.", {
      status: 503,
      headers: { "Cache-Control": "no-store" },
    });
  }

  const match = request.headers
    .get("authorization")
    ?.match(/^Basic\s+([A-Za-z0-9+/]+={0,2})$/i);
  const supplied = match?.[1] ?? "";
  const expected = Buffer.from(`${username}:${password}`, "utf8").toString(
    "base64",
  );
  const suppliedBytes = Buffer.from(supplied, "ascii");
  const expectedBytes = Buffer.from(expected, "ascii");
  const authenticated =
    suppliedBytes.length === expectedBytes.length &&
    timingSafeEqual(suppliedBytes, expectedBytes);

  if (authenticated) return null;
  return new Response("Authentication required.", {
    status: 401,
    headers: challengeHeaders,
  });
}
