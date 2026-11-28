# Reviewing portfolio earnings

Open **Research → Earnings inbox** and select the portfolio. The inbox uses positive quantities in its latest complete snapshot. An issuerless ETF remains in coverage. A filing or earnings release without an assessment appears as awaiting assessment. A holding without a publication appears in the coverage list. The snapshot date and model coverage are shown above the list.

For each publication, the research agent compares the issuer's figures and comparable period with the accepted DCF's base Year 1 driver. Record CHANGE, RETAIN or INSUFFICIENT_EVIDENCE. Cite the issuer passage and explain the accounting basis and period. When the comparison supports a change, use the existing inputs-only model proposal referencing the published research revision. The company reviewer controls preview, acceptance and refusal. The inbox ranks open comparisons that cross 15% first and then by absolute enterprise IRR change. Figures come from the stored reviewer preview and require the same fresh observation on both sides.

## Preparing a publication

Export the accepted financial model from the company financial-model endpoint. Run the packet builder from the repository root. For Booking the supplied assessment requires revision 2 and base Year 1 revenue growth of 8.7%.

```sh
uv run --project apps/api python -m portfolio_api.earnings_review_packet \
  /private/accepted-model.json docs/examples/booking-q3-revenue-assessment.json \
  > /private/earnings-packet.json
```

The output is a ResearchRevisionContractV1 v1.2 packet for the existing research-revisions publication endpoint. Replaying the same packet returns the existing revision. To correct a published packet, reference its ID as supersedes_revision_id and use a new external_revision_id. Publishing an assessment preserves the accepted model. Additional holdings need their own cited publication, and an accepted DCF before a model comparison.

## Release

The nullable earnings_review column requires the additive Alembic step from 7d390bce2851 to 63ad18f0e52b. Follow the guarded production migration and schema-attestation procedure before deploying the API and web release. Verify the holdings count, the prior Booking decision, and the cited revenue assessment after its authorized publication.

## Publish an approved batch

Run the API module `portfolio_api.holding_earnings_publication` from a private
operator environment with the standard verified database target. Supply
`--portfolio UUID --snapshot UUID` and repeat `--assessment PATH` for each
reviewed assessment in the packet-builder format. Preview is read-only. Check
the count and retain its SHA-256 privately. To apply, repeat the command with
the same files in the same order, the process-scoped production write
authorization and `--apply-digest SHA256`. The digest binds the portfolio,
snapshot, evidence, conclusions and accepted model revision IDs.

The publisher uses the research service in a single transaction, reads the
portfolio inbox before commit, and prints revision IDs after commit. Replaying
the same approved batch returns the original IDs. A changed baseline requires
a new review. The command accepts no model revisions, price refreshes or trades.

Use `--pending` in place of assessment files to enumerate issuer publications
already present in the inbox that still need an assessment for a modeled
holding. Each row identifies the listing, accepted revision number, source URL
and period. Fetch the referenced issuer publication and compare its accounting
basis and period with the accepted assumption before preparing the packet.
An empty result means no eligible sources are recorded.

In the signed-in app, open **Research → Earnings inbox → Publish earnings assessments**.
Choose the private JSON file (one assessment or an array), preview its assumptions and issuer
passages, then publish. The server checks the snapshot, revision and preview digest again and
commits the batch together. Replaying the same packet returns its existing research revision.
The inbox uses the existing reviewer credentials. No GitHub environment is involved.

## Check new issuer releases

Under Research → Earnings inbox, choose **Check for new releases**. Each issuer gets its own result. The check selects positive holdings in the latest complete snapshot with an accepted UFCF model. Initial coverage is NASDAQ:BKNG, NASDAQ:GOOGL, NASDAQ:AMZN, NYSE:MA and NASDAQ:MSFT. It verifies each ticker and exchange against SEC submissions and checks Item 2.02 filings and amendments from the five launch releases onward. It processes the oldest unseen release per issuer per check. An issuer-site launch assessment and its SEC accession refer to the same reviewed event.

A new release goes to the configured OpenAI model with the three accepted base Year 1 ratios, the prior assessment rationale and primary exhibit text. Configure SEC_USER_AGENT with an operator contact, EARNINGS_AGENT_MODEL with a JSON-capable model, and EARNINGS_AGENT_API_KEY as a server secret. Verify the primary exhibit, quote, annual comparability and accounting basis before publishing. Each draft is bound to the listing, accession and accepted revision. Publishing a CHANGE creates a separate one-input proposal. Open its reviewer preview for same-price enterprise IRR and the 15% hurdle, then accept or reject. Publishing RETAIN or INSUFFICIENT_EVIDENCE completes the review.

### Rollout and scheduled operation

Review the additive migration from 63ad18f0e52b to 29c47aaa5d71 under the existing release process. Verify populated recovery and the live head before deploying the dependent API and web code. Downgrading this migration drops stored drafts and their proposal links. Preserve the table or restore from the verified backup if rollback after use is necessary.

First run the signed-in manual check. After operator approval, configure the **Held issuer earnings releases** Actions workflow using the repository variables and secrets named in its YAML. Give its dedicated database role read access to the necessary portfolio/model tables, the row-lock privileges required on portfolios and financial_models, draft INSERT access, and the existing target-audit privileges. Avoid granting UPDATE on accepted model values or INSERT on revisions or proposals. Configure the SEC contact, model and provider secret in the job as well. The workflow uses the same discovery function as the app and runs weekdays at 18:15 New York time only when the repository variable EARNINGS_RELEASE_CHECKS_ENABLED is true. Workflow dispatch permits a supervised first run. Per-issuer failures yield a failed job and preserve successful drafts for other issuers.
