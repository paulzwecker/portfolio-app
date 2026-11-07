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
