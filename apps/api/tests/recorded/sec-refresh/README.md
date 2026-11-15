# Recorded fictional SEC responses

These fixed JSON responses are **synthetic test data**, not downloaded SEC records
or facts about an actual issuer. They reuse the existing fictional CIK `0000000001`
and SEC-format bootstrap fixtures. No network access or provider entitlement is
implied. The refresh rehearsal passes these bytes through the real SEC adapter,
validation, immutable raw receipts, PostgreSQL and financial-statement APIs.

`facts-initial.json` contains one annual revenue and a legitimate zero cash value.
`facts-updated.json` adds a later annual revenue observation.
`facts-partial.json` includes a separate EUR disclosure and an unmapped metric to verify partial
coverage without currency substitution.
`submissions.json` contains two fictional filing records. The outage mode raises
a transport error instead of returning bytes, preserving the previously stored facts.
