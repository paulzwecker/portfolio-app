## Change summary

<!-- Explain the user-visible or operational change and its domain boundary. -->

## Verification

- [ ] `npm run check:environment`
- [ ] `npm run check`
- [ ] `npm run test:integration` (when PostgreSQL-dependent behavior changed)
- [ ] Browser checks run or intentionally not applicable

## Safety

- [ ] No production/Neon database was used by tests or setup
- [ ] No credentials or personal portfolio state are committed
- [ ] Migrations include a reviewed rollback/reconciliation plan
- [ ] Missing, stale and unavailable states remain explicit

## Owner review before merging

- [ ] I reviewed the complete diff and the effect on production behavior.
- [ ] I reviewed required CI and any Vercel Preview evidence.
- [ ] I checked migration compatibility, target guards and recovery implications.
- [ ] Any production migration/deployment step remains separately authorized.
- [ ] At this integration boundary I ran `node scripts/deployment/schema-gate.mjs review` and reviewed its pending range.
- [ ] For a schema-dependent release, provider freezes, fresh populated-state recovery and the guarded migration have explicit operator gates. The production schema attestation advances only after live read-only verification and owner review.
