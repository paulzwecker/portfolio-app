# API contracts

FastAPI's Pydantic response models are authoritative. `openapi.json` and
`schema.d.ts` are generated and committed so the frontend can typecheck without a
running API or database. Run `npm run contracts:generate` after changing a public
API schema, then `npm run contracts:check` to verify the committed artifacts.
Import TypeScript types from `@portfolio/contracts`; do not hand-edit generated files.
