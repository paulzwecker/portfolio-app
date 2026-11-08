import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { GET, POST } from "@/app/api/research/[...path]/route";
import { isLedgerCandidate } from "@/lib/domain-contracts";
import {
  isLedgerOwnership,
  isLedgerPublication,
  isLedgerPublicationPlan,
  publicationMatchesCandidate,
} from "@/lib/ledger-publication-contracts";
import {
  acceptedLedgerCandidate,
  ledgerPublicationPlan,
  ledgerPublicationReceipt,
} from "../../../../e2e/fixtures/ledger-publication";

beforeEach(() => {
  vi.stubEnv("NODE_ENV", "test");
  vi.stubEnv("API_BASE_URL", "http://127.0.0.1:8000");
  vi.stubEnv("WEB_ACCESS_USERNAME", "");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "");
  vi.stubEnv("API_ACCESS_TOKEN", "synthetic-secret");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
it("verifies plan, accepted candidate, exact receipt and ownership without Number coercion", () => {
  const row = acceptedLedgerCandidate(),
    plan = ledgerPublicationPlan(),
    receipt = ledgerPublicationReceipt();
  expect(isLedgerCandidate(row)).toBe(true);
  expect(isLedgerPublicationPlan(plan)).toBe(true);
  expect(publicationMatchesCandidate(plan, row)).toBe(true);
  receipt.snapshot.positions[0].quantity = "2.50000000000000";
  expect(isLedgerPublication(receipt)).toBe(true);
  expect(
    isLedgerOwnership({
      portfolio_id: plan.portfolio_id,
      source: "ACCEPTED_LEDGER",
      scope: "WHOLE_PORTFOLIO",
      latest_publication: receipt,
    }),
  ).toBe(true);
  expect(
    isLedgerOwnership({
      portfolio_id: plan.portfolio_id,
      source: "OBSERVED_SNAPSHOT",
      scope: "WHOLE_PORTFOLIO",
      latest_publication: receipt,
    }),
  ).toBe(false);
});
it.each([
  "status",
  "confirmation",
  "snapshot",
  "decimal",
  "duplicate",
  "accounts",
  "cutoff",
  "owner",
  "currency",
  "negative",
])("rejects contradictory plan %s", (kind) => {
  const p = structuredClone(ledgerPublicationPlan());
  if (kind === "status") p.status = "ALREADY_PUBLISHED";
  if (kind === "confirmation") p.confirmation_phrase += " ";
  if (kind === "snapshot") p.current_snapshot.portfolio_id = p.candidate_id;
  if (kind === "decimal") Object.assign(p.cash[0], { balance: 0 });
  if (kind === "duplicate") p.positions.push(p.positions[0]);
  if (kind === "accounts") p.account_ids.push(p.account_ids[0]);
  if (kind === "cutoff") p.effective_at = p.current_snapshot.effective_at;
  if (kind === "owner") p.previous_publication_id = p.candidate_id;
  if (kind === "currency") p.cash[0].currency = "usd";
  if (kind === "negative") p.positions[0].quantity = "-1";
  expect(isLedgerPublicationPlan(p)).toBe(false);
});
it.each(["input", "review", "quantity", "cash", "account", "effective"])(
  "binds plan to candidate %s",
  (kind) => {
    const row = acceptedLedgerCandidate(),
      p = structuredClone(ledgerPublicationPlan());
    if (kind === "input") p.candidate_input_sha256 = "a".repeat(64);
    if (kind === "review") p.review_id = p.candidate_id;
    if (kind === "quantity") p.positions[0].quantity = "2.5000000001";
    if (kind === "cash") p.cash[0].balance = "100.0000000001";
    if (kind === "account") p.account_ids = [p.candidate_id];
    if (kind === "effective") p.effective_at = "2026-01-04T00:00:00Z";
    expect(publicationMatchesCandidate(p, row)).toBe(false);
  },
);
it.each([
  "snapshot",
  "reason",
  "quantity",
  "zero",
  "hash",
  "recovery",
  "previous",
  "time",
  "sequence",
  "actor",
])("rejects inconsistent publication receipt %s", (kind) => {
  const r = structuredClone(ledgerPublicationReceipt());
  if (kind === "snapshot") r.snapshot.source = "observed-snapshot";
  if (kind === "reason") r.snapshot.reason = "different";
  if (kind === "quantity")
    r.snapshot.positions = [
      { ...r.snapshot.positions[0], quantity: "2.5000000001" },
    ];
  if (kind === "zero")
    r.snapshot.cash_positions = r.snapshot.cash_positions.filter(
      (x) => x.currency !== "EUR",
    );
  if (kind === "hash") r.command.expected_plan_sha256 = "a".repeat(64);
  if (kind === "recovery")
    Object.assign(r.command, { current_state_recovery_verified: false });
  if (kind === "previous") r.previous_publication_id = r.id;
  if (kind === "time") r.snapshot.recorded_at = "2026-01-04T00:00:00Z";
  if (kind === "sequence") r.sequence = 2;
  if (kind === "actor") Object.assign(r, { published_by: "AGENT" });
  expect(isLedgerPublication(r)).toBe(false);
});
function route(suffix: string) {
  const p = ledgerPublicationPlan();
  return [
    "portfolios",
    p.portfolio_id,
    "ledger",
    "candidates",
    p.candidate_id,
    suffix,
  ];
}
it.each(["publication-preview", "ownership"])(
  "proxies only verified scoped %s reads",
  async (suffix) => {
    const p = ledgerPublicationPlan();
    const path =
      suffix === "ownership"
        ? ["portfolios", p.portfolio_id, "ledger", suffix]
        : route(suffix);
    const data =
      suffix === "ownership"
        ? {
            portfolio_id: p.portfolio_id,
            source: "OBSERVED_SNAPSHOT",
            scope: "WHOLE_PORTFOLIO",
            latest_publication: null,
          }
        : p;
    const upstream = vi.fn().mockResolvedValue(Response.json(data));
    vi.stubGlobal("fetch", upstream);
    const response = await GET(
      new Request(`http://localhost/api/research/${path.join("/")}`),
      { params: Promise.resolve({ path }) },
    );
    expect(response.status).toBe(200);
    data.portfolio_id = p.candidate_id;
    upstream.mockResolvedValueOnce(Response.json(data));
    expect(
      (
        await GET(new Request("http://localhost/api/research"), {
          params: Promise.resolve({ path }),
        })
      ).status,
    ).toBe(503);
  },
);
it("forwards one hash-bound publication command with server token and origin protection", async () => {
  const r = ledgerPublicationReceipt(),
    path = route("publish");
  const upstream = vi.fn().mockResolvedValue(Response.json(r));
  vi.stubGlobal("fetch", upstream);
  const body = JSON.stringify(r.command);
  const request = (origin: string) =>
    new Request("http://localhost/api/research/" + path.join("/"), {
      method: "POST",
      headers: { Origin: origin, "Content-Type": "application/json" },
      body,
    });
  expect(
    (
      await POST(request("https://foreign.test"), {
        params: Promise.resolve({ path }),
      })
    ).status,
  ).toBe(403);
  expect(upstream).not.toHaveBeenCalled();
  expect(
    (
      await POST(request("http://localhost"), {
        params: Promise.resolve({ path }),
      })
    ).status,
  ).toBe(200);
  expect(upstream).toHaveBeenCalledTimes(1);
  expect(upstream.mock.calls[0][1].body).toBe(body);
  expect(upstream.mock.calls[0][1].headers["X-API-Access-Token"]).toBe(
    "synthetic-secret",
  );
  r.candidate_id = r.id;
  upstream.mockResolvedValueOnce(Response.json(r));
  expect(
    (
      await POST(request("http://localhost"), {
        params: Promise.resolve({ path }),
      })
    ).status,
  ).toBe(503);
});
it.each([403, 409, 422, 500])(
  "sanitizes publication failure %s and never retries",
  async (status) => {
    const path = route("publish");
    const upstream = vi
      .fn()
      .mockResolvedValue(
        Response.json({ detail: "private upstream diagnostic" }, { status }),
      );
    vi.stubGlobal("fetch", upstream);
    const response = await POST(
      new Request("http://localhost/api/research/" + path.join("/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ledgerPublicationReceipt().command),
      }),
      { params: Promise.resolve({ path }) },
    );
    expect(response.status).toBe(status === 500 ? 503 : status);
    expect(await response.text()).not.toContain("private upstream");
    expect(upstream).toHaveBeenCalledTimes(1);
  },
);
