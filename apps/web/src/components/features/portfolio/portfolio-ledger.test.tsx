import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { GET, POST } from "@/app/api/research/[...path]/route";
import {
  isPortfolioLedgerAnchor,
  isPortfolioLedgerPreview,
} from "@/lib/domain-contracts";
import {
  ledgerAnchor,
  ledgerPacket,
  ledgerPortfolioId,
  ledgerReport,
} from "../../../../e2e/fixtures/ledger";
import { inspectLedgerFile, ledgerFileLimit } from "./portfolio-ledger-data";
import { PortfolioLedgerResults } from "./portfolio-ledger-results";

beforeEach(() => {
  vi.stubEnv("API_BASE_URL", "http://127.0.0.1:8000");
  vi.stubEnv("NODE_ENV", "test");
  vi.stubEnv("API_ACCESS_TOKEN", "");
  vi.stubEnv("WEB_ACCESS_USERNAME", "");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "");
});

it("accepts explicit v2 income packets and their matching projection contract", () => {
  const packet = ledgerPacket();
  packet.contract_version = "portfolio-ledger-preview-v2";
  const text = JSON.stringify(packet);
  expect(inspectLedgerFile(text, "income.json").text).toBe(text);
  const report = ledgerReport();
  report.contract_version = "portfolio-ledger-preview-v2";
  report.projection_version = "settled-booking-v2";
  expect(isPortfolioLedgerPreview(report)).toBe(true);
  report.projection_version = "settled-booking-v1";
  expect(isPortfolioLedgerPreview(report)).toBe(false);
  report.contract_version = "portfolio-ledger-preview-v1";
  report.projection_version = "settled-booking-v2";
  expect(isPortfolioLedgerPreview(report)).toBe(false);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

it("validates complete hash-bound anchors and ending reports", () => {
  expect(isPortfolioLedgerAnchor(ledgerAnchor)).toBe(true);
  expect(isPortfolioLedgerPreview(ledgerReport())).toBe(true);
  expect(
    isPortfolioLedgerAnchor({ ...ledgerAnchor, portfolio_id: "bad" }),
  ).toBe(false);
  expect(isPortfolioLedgerAnchor({ ...ledgerAnchor, listings: [] })).toBe(
    false,
  );
  expect(
    isPortfolioLedgerAnchor({
      ...ledgerAnchor,
      snapshot: { ...ledgerAnchor.snapshot, completeness: "PARTIAL" },
    }),
  ).toBe(false);
});
it.each([
  { preview_only: false },
  { status: "ACCEPTED" },
  { input_sha256: "bad" },
  { ending_status: "NOT_PROVIDED" },
  {
    ending_reconciliation: [
      {
        domain: "CASH",
        key: "EUR",
        projected: 0,
        observed: "0",
        difference: "0",
        status: "MATCH",
        account_id: null,
      },
    ],
  },
  { consumed_listings: undefined },
  {
    issues: [
      {
        code: "ENDING_MISMATCH",
        activity_id: null,
        account_id: null,
        asset_key: "USD",
      },
    ],
  },
])("rejects unverifiable preview metadata or decimals %j", (change) => {
  expect(isPortfolioLedgerPreview({ ...ledgerReport(), ...change })).toBe(
    false,
  );
});
it("retains raw financial text while inspecting only labels and identities", () => {
  const original = JSON.stringify(ledgerPacket()).replace(
    '"2.5000000000"',
    "9007199254740993",
  );
  const file = inspectLedgerFile(original, "private.json");
  expect(file.text).toBe(original);
  expect(file.text).toContain("9007199254740993");
  expect(file.evidence).toHaveLength(2);
  expect(file.accountNames).toEqual({
    "11111111-1111-4111-8111-111111111111": "Synthetic broker account",
  });
});
it("normalizes UUID metadata while preserving original source text", () => {
  const packet = ledgerPacket();
  packet.anchor_snapshot_id =
    "abcdefab-cdef-4abc-8def-abcdefabcdef".toUpperCase();
  packet.accounts[0].account_id =
    "abcdefab-cdef-4abc-8def-abcdefabcdef".toUpperCase();
  packet.ending_statement.accounts[0].account_id =
    packet.accounts[0].account_id;
  const text = JSON.stringify(packet);
  const file = inspectLedgerFile(text, "uppercase.json");
  expect(file.text).toBe(text);
  expect(file.anchorSnapshotId).toBe(packet.anchor_snapshot_id.toLowerCase());
  expect(Object.keys(file.accountNames)).toEqual([
    packet.accounts[0].account_id.toLowerCase(),
  ]);
  expect(
    file.evidence.every(
      (row) => row.accountId === packet.accounts[0].account_id.toLowerCase(),
    ),
  ).toBe(true);
});
it.each(["opening", "ending", "unevaluated"])(
  "rejects contradictory ready/row states %s",
  (scope) => {
    const report = ledgerReport();
    if (scope === "opening")
      report.opening_reconciliation[0].status = "DIFFERENCE";
    if (scope === "ending")
      report.ending_reconciliation[0].status = "MISSING_OBSERVATION";
    if (scope === "unevaluated") {
      report.status = "BLOCKED";
      report.ending_status = "NOT_EVALUATED";
      report.issues = [
        {
          code: "OPENING_MISMATCH",
          activity_id: null,
          account_id: null,
          asset_key: null,
        },
      ];
    }
    expect(isPortfolioLedgerPreview(report)).toBe(false);
  },
);
it.each([
  "{private-invalid",
  "null",
  "[]",
  JSON.stringify({ ...ledgerPacket(), contract_version: "unknown" }),
  " ".repeat(ledgerFileLimit + 1),
])("rejects invalid input without exposing its contents", (text) => {
  expect(() => inspectLedgerFile(text, "private.json")).toThrow(
    /ledger|contract/,
  );
});
it("shows independent ending/acceptance state and exact source evidence", () => {
  const html = renderToStaticMarkup(
    <PortfolioLedgerResults
      report={ledgerReport()}
      file={inspectLedgerFile(JSON.stringify(ledgerPacket()), "private.json")}
    />,
  );
  expect(html).toContain("Ending statement reconciled");
  expect(html).toContain("source authenticity require review");
  expect(html).toContain("Inspect source evidence");
  expect(html).not.toContain("Accept model");
  expect(html).not.toContain("Apply ledger");
});
it("keeps missing observation distinct from explicit zero", () => {
  const report = ledgerReport();
  report.status = "BLOCKED";
  report.ending_status = "MISMATCH";
  report.issues = [
    {
      code: "ENDING_MISMATCH",
      account_id: null,
      activity_id: null,
      asset_key: "EUR",
    },
  ];
  report.ending_reconciliation = [
    {
      domain: "CASH",
      key: "EUR",
      account_id: null,
      projected: "0",
      observed: null,
      difference: null,
      status: "MISSING_OBSERVATION",
    },
  ];
  const html = renderToStaticMarkup(
    <PortfolioLedgerResults
      report={report}
      file={inspectLedgerFile(JSON.stringify(ledgerPacket()), "private.json")}
    />,
  );
  expect(html).toContain("Review blocked");
  expect(html).toContain("Missing");
  expect(html).toContain("MISSING OBSERVATION");
});
it("proxies only anchor reads and preview requests, preserving financial request text", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json(ledgerAnchor))
    .mockResolvedValue(Response.json(ledgerReport()));
  vi.stubGlobal("fetch", fetch);
  const root = ["portfolios", ledgerPortfolioId, "ledger"];
  const url = `http://localhost/api/research/${root.join("/")}`;
  const context = (path: string[]) => ({ params: Promise.resolve({ path }) });
  expect(
    (await GET(new Request(`${url}/anchor`), context([...root, "anchor"])))
      .status,
  ).toBe(200);
  const body = JSON.stringify(ledgerPacket()).replace(
    '"2.5000000000"',
    "9007199254740993",
  );
  const response = await POST(
    new Request(`${url}/preview`, { method: "POST", body }),
    context([...root, "preview"]),
  );
  expect(response.status).toBe(200);
  expect(fetch.mock.calls[1][1].body).toBe(body);
  expect(response.headers.get("cache-control")).toBe("no-store");
  expect(
    (
      await POST(
        new Request(`${url}/apply`, { method: "POST", body }),
        context([...root, "apply"]),
      )
    ).status,
  ).toBe(404);
  expect(
    (
      await POST(
        new Request(`${url}/anchor`, { method: "POST", body }),
        context([...root, "anchor"]),
      )
    ).status,
  ).toBe(404);
  expect(fetch).toHaveBeenCalledTimes(2);
});
it("bounds ledger UTF-8 payload bytes while retaining same-origin checks", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const path = ["portfolios", ledgerPortfolioId, "ledger", "preview"];
  const url = `http://localhost/api/research/${path.join("/")}`;
  const context = { params: Promise.resolve({ path }) };
  const tooLarge = JSON.stringify({ name: "€".repeat(340_000) });
  expect(
    (await POST(new Request(url, { method: "POST", body: tooLarge }), context))
      .status,
  ).toBe(413);
  expect(
    (
      await POST(
        new Request(url, {
          method: "POST",
          body: "{}",
          headers: { origin: "https://outside.invalid" },
        }),
        context,
      )
    ).status,
  ).toBe(403);
  expect(fetch).not.toHaveBeenCalled();
});
