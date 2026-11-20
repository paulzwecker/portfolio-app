# Isolated primary-source agent pilot — Uber Q3 2026

This pilot exercises the observation proposal contract against **publicly
disclosed figures**, in an isolated, migrated test database. It does not imply
approval of real canonical data, activate an agent or change a live portfolio.

Primary source: Uber investor-relations earnings release, **November 4, 2026**:
https://investor.uber.com/news-events/news/press-release-details/2026/Uber-Announces-Results-for-Third-Quarter-2026/default.aspx

## Explicit observations to investigate

| Data | Period | Exact numeric value | Scale | Currency / unit |
| --- | --- | ---: | ---: | --- |
| Trips | 2026 Q3 | 4061 | 1,000,000 | trips |
| Gross Bookings | 2026 Q3 | 59819 | 1,000,000 | USD currency |
| Gross Bookings guidance low | 2026 Q4 | 63250 | 1,000,000 | USD currency |
| Gross Bookings guidance high | 2026 Q4 | 65250 | 1,000,000 | USD currency |

Use strict `EQ` for reported exact actuals; `RANGE` for guidance.
Source reports millions for Q3 values. A $59.8-billion rounded headline
must **not** replace the $59,819-million tabulated observation. Likewise the
4.1-billion-trip headline is rounded; use 4,061 million.

The release supplies a **publication calendar date, not an exact UTC
publication time**. The proposal's `reported_at` and `issued_at` fields may be
null. Do not invent 00:00 as a release timestamp. The accepted database
`recorded_at` is tracked separately.

## Shadow acceptance workflow (test-only)

The isolated API test:
1. Creates a clearly labeled test-only company identity.
2. Submits company-scoped trip / Gross Bookings metric definitions.
3. Calls typed proposal submission, deterministic reviewer preview and
   test-only acceptance.
4. Replays exact KPI and Q4 guidance values from the cited release.
5. Reads `CompanyAgentContextV1` and verifies numeric units, source URL and
   future target guidance alongside Q3 actuals.

This is a source-backed **contract rehearsal**. It does not prove a production
agent autonomously discovered new evidence. The next live shadow experiment
must resolve a *real* company's canonical UUID, read its accepted context,
identify a gap, and prepare a proposal without enabling acceptance.

No provider license, paid subscription or unapproved source write is required.
