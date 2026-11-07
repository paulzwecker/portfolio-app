import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL(
    "../../tools/google-sheets/CanonicalModelContract.gs",
    import.meta.url,
  ),
  "utf8",
);
const context = vm.createContext({
  Utilities: {
    DigestAlgorithm: { SHA_256: "sha256" },
    Charset: { UTF_8: "utf8" },
    computeDigest(algorithm, value, encoding) {
      return Array.from(createHash(algorithm).update(value, encoding).digest());
    },
  },
});
vm.runInContext(source, context);

test("Apps Script freezes exact UTF-8 model text and decimal published values", () => {
  const contract = { contract_version: "1.2.0", rationale: "Synthetic café" };
  const fairValues = {
    bear_fv: "10.123456789012345678",
    base_fv: "20",
    bull_fv: "30",
    weighted_fv: "21",
  };
  const publication = context.modelPublication_(
    contract,
    fairValues,
    "2026-01-01T00:00:00Z",
  );
  assert.equal(publication.contract_type, "FinancialModelPublicationV1");
  assert.equal(publication.state, "PUBLISHED");
  assert.equal(publication.contract_json, JSON.stringify(contract));
  assert.equal(
    publication.contract_sha256,
    createHash("sha256").update(publication.contract_json).digest("hex"),
  );
  assert.equal(publication.published_fair_values.bear_fv, fairValues.bear_fv);
  const replay = context.modelPublication_(
    contract,
    fairValues,
    "2026-01-02T00:00:00Z",
  );
  assert.equal(
    context.sameModelPublication_(JSON.stringify(publication), replay),
    true,
  );
  replay.published_fair_values.bear_fv = "11";
  assert.equal(
    context.sameModelPublication_(JSON.stringify(publication), replay),
    false,
  );
});

test("Apps Script rejects legacy, blank, error and numeric publication fields", () => {
  const values = { bear_fv: "1", base_fv: "2", bull_fv: "3", weighted_fv: "2" };
  assert.throws(() =>
    context.modelPublication_({ contract_version: "1.1.0" }, values, "date"),
  );
  for (const invalid of ["", "#VALUE!", "1,000.5", 1.2, null]) {
    assert.throws(() =>
      context.modelPublication_(
        { contract_version: "1.2.0" },
        { ...values, bear_fv: invalid },
        "date",
      ),
    );
  }
});

test("independent model publications sharing a revision label replay by publish block", () => {
  const values = { bear_fv: "1", base_fv: "2", bull_fv: "3", weighted_fv: "2" };
  const first = context.modelPublication_(
    { contract_version: "1.2.0", model: { model_id: "model-a" } },
    values,
    "2026-01-01T00:00:00Z",
  );
  const second = context.modelPublication_(
    { contract_version: "2.1.0", model_id: "model-b" },
    values,
    "2026-01-01T00:00:00Z",
  );
  const rows = [];
  for (const [publishId, publication] of [
    ["a", first],
    ["b", second],
  ]) {
    const raw = JSON.stringify(publication);
    const middle = Math.floor(raw.length / 2);
    rows.push([publishId, "agent-r2", "1", "2", raw.slice(0, middle)]);
    rows.push([publishId, "agent-r2", "2", "2", raw.slice(middle)]);
  }
  assert.equal(context.hasModelPublication_(rows, "agent-r2", first), true);
  assert.equal(
    context.hasModelPublication_(rows.slice().reverse(), "agent-r2", second),
    true,
  );
  assert.equal(
    context.hasModelPublication_(rows.slice(1), "agent-r2", first),
    false,
  );
  assert.equal(context.hasModelPublication_(rows, "different", first), false);
  assert.equal(
    context.hasModelPublication_([...rows, rows[0]], "agent-r2", first),
    false,
  );
  const changed = structuredClone(first);
  changed.published_fair_values.weighted_fv = "3";
  assert.equal(context.hasModelPublication_(rows, "agent-r2", changed), false);
});
