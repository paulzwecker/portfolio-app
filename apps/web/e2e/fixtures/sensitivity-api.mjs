import { readFileSync } from "node:fs";
import { createServer } from "node:https";
import path from "node:path";
import {
  modelId,
  malformedModelId,
  revisionId,
  sensitivityFixture,
} from "./dcf-sensitivity.mjs";

const directory = process.env.E2E_TLS_DIRECTORY;
const token = process.env.API_ACCESS_TOKEN;
const port = process.env.E2E_FIXTURE_API_PORT;
if (
  process.env.E2E_MANAGED_PRODUCTION_SERVER !== "1" ||
  !directory ||
  !token ||
  !port ||
  !/^\d{4,5}$/.test(port)
)
  throw new Error("Start this synthetic fixture with --managed-production.");

const server = createServer(
  {
    key: readFileSync(path.join(directory, "server.key")),
    cert: readFileSync(path.join(directory, "server.pem")),
  },
  (request, response) => {
    const url = new URL(request.url ?? "/", `https://127.0.0.1:${port}`);
    response.setHeader("content-type", "application/json");
    response.setHeader("cache-control", "no-store");
    const reply = (status, body) => {
      response.writeHead(status);
      response.end(JSON.stringify(body));
    };
    if (request.method !== "GET")
      return reply(405, { detail: "Read-only synthetic fixture" });
    if (url.pathname === "/health/live") return reply(200, { status: "ok" });
    if (
      request.headers["x-api-access-token"] !== token ||
      request.headers.authorization
    )
      return reply(401, {
        detail: "Synthetic backend authentication required",
      });
    if (url.pathname === `/v1/financial-models/${modelId}/sensitivity`) {
      if (url.searchParams.get("base_revision_id") !== revisionId)
        return reply(409, { detail: "Synthetic revision changed" });
      return reply(200, sensitivityFixture());
    }
    if (
      url.pathname === `/v1/financial-models/${malformedModelId}/sensitivity`
    ) {
      const malformed = sensitivityFixture();
      malformed.model_id = malformedModelId;
      malformed.cells.pop();
      return reply(200, malformed);
    }
    return reply(404, { detail: "Unknown synthetic read" });
  },
);
server.listen(Number(port), "127.0.0.1");
