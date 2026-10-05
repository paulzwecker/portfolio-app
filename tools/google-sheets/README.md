# Google Sheets model authoring adapter

This folder provides a manual, reviewable file workflow for canonical model
contracts: `FinancialModelContractV1` (`1.0.0`) for DCF and
`AdditionalModelPortableContractV2` (`2.0.0`) for owner-cash-flow and residual-income
models. PostgreSQL and the application remain canonical. The script does not call
the application, use the Google Sheets API, recalculate outputs or write to Drive.
It translates method-specific assumptions into spreadsheet input tabs and serializes
edits back to the JSON contract.

## Set up a workbook

1. In the Company Explorer's external-authoring section, select **Export Sheets
   contract** for an accepted DCF, owner-cash-flow or residual-income model.
2. Create or open a Google Sheet.
3. Open **Extensions → Apps Script**, paste
   [`CanonicalModelContract.gs`](CanonicalModelContract.gs), save, then reload the
   spreadsheet. The script needs only the active spreadsheet's edit permission.
4. Choose **Portfolio model → Load exported contract JSON** and paste the downloaded
   file's contents into the dialog. The adapter stores a compact copy in
   `Contract!A1` without splitting its lines across cells.
5. Use **Portfolio model → Build editable input tabs**. The adapter creates
   `Base Inputs`, `Scenario Inputs`, and `Revision`; it also creates `Year Inputs`
   for owner-cash-flow models (30 scenario/year rows). Residual-income models have
   no editable year table because the application derives the ten-year ROE fade
   from starting and mature ROE. The `Contract` sheet retains the exported base.
6. Edit only the candidate input and revision cells. Keep decimal values in plain
   decimal notation and leave them as text; do not add formulas or currency
   conversions. The sheet stores assumptions, not accepted calculations.
7. Use **Portfolio model → Write edits back to contract JSON**. Copy the updated
   JSON from `Contract!A1` into a local `.json` file.
8. Upload that file in the matching Company Explorer model. Select **Preview edited
   contract** for DCF or **Preview external update** for owner-cash-flow and
   residual-income models. Review every assumption change and server recalculation
   difference, then accept only when the preview is `READY`.

The API rejects invalid ranges, invalid scenario probability totals, malformed years,
missing rationale for changed assumptions and contracts based on a superseded
application revision. DCF v1 also checks the exported base-calculation snapshot. A
conflict requires a fresh export and deliberate reapplication of external edits.
Re-importing the exact accepted JSON is idempotent. After acceptance, export again
before another Sheets edit so the next candidate has a new external revision
identity.

Apps Script is optional development tooling. The application remains usable without
Google accounts, Apps Script permissions, a live Sheets connection or network access
to Google services.
