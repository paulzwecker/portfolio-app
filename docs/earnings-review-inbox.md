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
