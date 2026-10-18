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
