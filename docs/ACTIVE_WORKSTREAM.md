# Active workstream

## Public SEC statements - integrated acceptance (2026-11-15)

Extend the existing [PR #39](https://github.com/paulzwecker/portfolio-app/pull/39),
branch `codex/financial-refresh-slice`, based on main `866723e`. Main includes
PR #37 recovery tooling and PR #38 investor UI. Independent investment intelligence
remains preserved at `33cedff`; owner edits, worktrees and stash are intact.

Frozen outcome: verified issuer -> official SEC observations -> existing durable
manual/scheduled ingestion -> isolated PostgreSQL -> Financials charts/tables,
source evidence and filing history. **MSCI and Microsoft now pass this journey.**
No new application code, financial method, source contract, schema, API, service or
paid dependency was needed for the Microsoft extension. Only test expectations and
the private replay's Nasdaq/NASDAQ spelling comparison changed.

| Isolated source coverage | Facts | Filing references | Independent verification                                                                                              |
| ------------------------ | ----: | ----------------: | --------------------------------------------------------------------------------------------------------------------- |
| MSCI, CIK0001408198      | 1,596 |               310 | Original annual/quarterly values, timestamps and accessions; desktop/mobile regression                                |
| Microsoft, CIK0000789019 | 1,909 |               428 | 14 annual/quarterly samples against actual 10-K/10-Q statement contexts; all ten existing metric families represented |

Microsoft's CIK, legal registrant, jurisdiction/registration identifiers and common
stock MSFT/Nasdaq context agree across the official filing covers and submissions.
Ticker similarity alone was not used. The private mapping proposal is
**REVIEW_REQUIRED**, not a production approval. Empty former-name metadata does not
establish historical continuity. Exact canonical IDs, proposals and source bytes
stay private.

Six bounded official requests captured Microsoft: facts, submissions, two indexed
history files, one annual filing and one quarterly filing. Four JSON responses are
replayed unchanged; filing bodies are comparison evidence, not imported content.
Prior MSCI captures were reused without another provider request. The isolated
portfolio quantities/targets are explicitly fictional. Original source capture
and later job/recorded timestamps remain distinct; a pre-capture knowledge cutoff
returns no reported periods.

FY2026 Microsoft annual statements end June 30; September 2026 is **FY2027 Q1**.
Revenue, gross profit, operating/net income, cash, OCF and capex samples agree with
filing values and USD units. Positive source capex is retained without an inferred
FCF. Both domains remain PARTIAL: Microsoft retains 32 changed historical
comparatives, 549 unmapped concepts, 448 YTD/unclassified duration exclusions,
142 unsupported-form facts and 4,118 unsupported filing rows. Debt observations
cover selected components, excluding separately disclosed leases. Later cash-flow
quarters may be unavailable when SEC supplies only YTD facts. Do not infer quarters,
ratios, restatement conclusions, total debt or complete filing coverage.

Manual requests survive navigation/reload, completed facts refresh existing views,
and Operations submits both bounded domains. A three-day-late scheduled pass
preserves counts; same-day replay makes no new transport call. Microsoft browser
runs each make seven offline transport calls, not seven extra SEC requests.
All tables outside ingestion/jobs retain identical content hashes. Failures and
synthetic conflict/new-period handling remain covered by the original rehearsals.

Verification: 12 focused backend checks pass (11 with MSCI, one Microsoft source
replay); all four MSCI/Microsoft desktop/mobile journeys pass. Types, lint,
formatting, contracts and schema/deployment gates are checked at integration;
latest-head CI results are maintained in PR #39. Independent accounting/identity
and visual reviews found no A-class blocker. [Reproduction](testing.md#recorded-official-sec-responses-through-the-investor-ui).
CI exposed two existing same-day scheduler tests crossing midnight when they added
one minute to the wall clock. Their fixture timestamps are now fixed at UTC noon;
production day-boundary/retry behavior is unchanged. All 21 recurring-operations
checks and the existing explicit next-day SEC integration check pass.
Screenshots: [annual desktop](design/screenshots/microsoft-annual-desktop.png),
[quarterly mobile](design/screenshots/microsoft-quarterly-mobile.png),
[filing history](design/screenshots/microsoft-filings-desktop.png).

## Release and operational boundary

**CONFIGURATION_REQUIRED.** Schema attestation remains `b59f16c8a203`, zero pending
migrations and unchanged migration bytes; no new API dependency. Current hosted
commits/deployment controls are not newly attested. Freeze this completed scope for
owner review. No merge, deployment, cloud change, production query/write or
scheduler activation occurred in this extension.

Production remains **NOT STARTED**. Last recorded November 14 read-only inventory:
22 positions, two cash rows, one target revision; zero prices/FX/facts/filings or
consensus. This is historical evidence, not a new production readback. No approved
current-state production backup has been executed. The old Neon branch expires
November 15 at 14:18 CET and is not durable recovery.

Smallest operator sequence:

1. Approve an encrypted off-provider destination, key custody and isolated restore
   target; execute the existing [backup/restore procedure](encrypted-production-recovery.md)
   with its required confirmations.
2. Review the private exact MSCI/Microsoft mapping proposals and authorize a bounded
   issuer scope; verify hosted SEC contact/configuration. Run the existing
   target-bound preview and guarded filings/facts checkpoints, then reconcile and
   verify authenticated live UI readback.
3. Prove a controlled incremental refresh before separately activating the
   [existing-host SEC schedule](recurring-operations.md#zero-cost-sec-scheduling-proposal).

No broad universe, international feed, new metric/ratio, Sheets, recovery framework
or UI redesign is required to ship this slice. Additional issuer coverage follows
this same reviewed workflow. Free equity/consensus access remains unverified;
[official ECB FX](financial-data-provider-decision.md) remains an independent next
capability, without a paid fallback or new infrastructure.
