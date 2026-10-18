# Milestone 13B — Neon Provisioning & Cloud Deployment Activation

This document carries forward the Milestone 13A deployment foundation and a
Milestone 13B status snapshot dated 2026-10-17. That snapshot records Neon as
connected to the existing `portfolio-research` project and `production` branch,
with Render and Vercel then unprovisioned and scheduled ingestion inactive. The
Milestone 14B-R task context says Render and Vercel have since been deployed; no
live cloud check was made during this review, so confirm the present service
settings in their consoles before relying on deployment steps below.

## Milestone 13B activation status — 2026-10-17

The official Neon CLI `8.8.0` is installed and its current command syntax was verified. The existing project and branch were reused; no duplicate project was created. Because this CLI's one-shot initializer can pull environment variables into `.env`, the safe initialization sequence used here separates linking from policy generation:

```powershell
neon link -y --org-id org-muddy-snow-88568392 --project-id delicate-heart-04560404 --branch production --no-env-pull --no-config
neon config init --project-id delicate-heart-04560404 --branch production --from-branch --no-install
neon config plan --project-id delicate-heart-04560404 --branch production
neon deploy --project-id delicate-heart-04560404 --branch production --no-env-pull
```

Neon activation is **COMPLETE**. The authenticated CLI linked `.neon` to project `delicate-heart-04560404` and branch `production` (`br-morning-truth-b96361yh`) with environment pulling disabled. The generated [neon.ts](../neon.ts) policy declares no optional services and uses `auth: false`; `neon config plan` and `neon deploy --no-env-pull` both reported no changes and PostgreSQL as the only utilized service. No Neon Auth, Data API, Functions, Object Storage, AI Gateway or Realtime service was enabled.

The production branch was empty before migration (`0` public tables and no
`alembic_version`). The checked-in Alembic chain was applied through head
`12a6f0d9c3e1`; readiness now reports `database=connected` and
`schema=current`, with 84 public tables. A transaction-local numeric
round-trip preserved `123.456789012345678901`, and rollback removed the probe
without persistent writes. A post-migration read-only size query reported a
13 MB database, 600 kB of table/TOAST data and 2.5 MB of indexes; Neon reports
approximately 31.7 MB logical branch size, well below the 1 GB Free allowance.

The local ignored `.env` was backed up before this check and remains configured for the local PostgreSQL endpoint (`127.0.0.1`). No Neon variables were written into it.

The temporary local FastAPI process connected to Neon successfully: `/health/live`
returned `200`, `/health/ready` returned `200` with a current schema, an
unauthenticated `/v1/universe` request returned `401`, and the same request with
the server token returned `200` with the expected empty-universe response.
The process was stopped after verification.

Local repository verification is green: the Next.js production build, full
frontend/backend lint, formatting, type checks, contract checks, frontend tests
and all 381 API tests passed. Render/Vercel remote checks remain pending because
those services have not been connected or deployed.

## Deployment shape

```text
Browser -- Basic Auth --> Vercel Next.js
                              | server-side API proxy + API_ACCESS_TOKEN
                              v
                         Render FastAPI -- SQLAlchemy pool --> Neon PostgreSQL

Optional hourly Render Cron -- one bounded cycle --> same Neon database
```

The web app calls only its same-origin `/api/research/*` and `/api/health` handlers. Those handlers call FastAPI from the server using `API_BASE_URL` and the server-only `API_ACCESS_TOKEN`. The API rejects all non-health requests without that token. The web app also requires HTTP Basic credentials in production and preview, including on its API route handlers. Same-origin writes must include an `Origin` header. Keep Vercel Deployment Protection enabled as an additional gate, but it does not replace the Render API token.

This is a single shared developer login, suitable for a private preview. It does not identify individual users or provide roles. Do not invite other people to a shared writable deployment; multi-user access needs account authentication, authorization and auditable user identities.

`/health/live` checks only that FastAPI is serving. Render uses it as its process health check so the initial deploy can start before an operator runs migrations. `/health/ready` checks database connectivity and Alembic heads. The web app's `/api/health` returns this readiness status without exposing connection details. The API never runs Alembic at startup.

On Render Free, the API sleeps after 15 minutes without traffic and may take about a minute to wake. The web readiness proxy intentionally gives its health request 5 seconds, so it can show a temporary 503 during wake-up. Visit the Render `/health/live` URL directly, wait for it to answer, then reload the web app.

## Files prepared

- [`render.yaml`](../render.yaml): native Python web service on Render Free, pinned to `main`, with ingestion disabled.
- [`apps/web/vercel.json`](../apps/web/vercel.json): Next.js framework and npm workspace commands from the monorepo root.
- [`apps/web/src/proxy.ts`](../apps/web/src/proxy.ts) and [`server-access.ts`](../apps/web/src/lib/server-access.ts): fail-closed shared-password gate for production and preview requests.
- [`cloud_cron.py`](../apps/api/src/portfolio_api/cloud_cron.py): one bounded market refresh plus one recurring-operations cycle. It exits when complete, reuses the existing services and PostgreSQL advisory locks, and is inert until `CLOUD_INGESTION_ENABLED=true`.

There is no Docker requirement. Render uses its native Python runtime and `uv`; Vercel builds the Next.js npm workspace.

## Environment variables

### Render API service

| Variable                             | Required | Value / purpose                                                                                                                       |
| ------------------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `APP_ENV`                            | Yes      | `production` for the main API or `preview` for an isolated preview API. Both modes fail startup without a 32+ character token.        |
| `PYTHON_VERSION`                     | Yes      | `3.13.16`; pinned within the API's `>=3.12,<3.14` supported range.                                                                    |
| `DATABASE_URL`                       | Yes      | Neon **direct** connection URL using `postgresql+psycopg://...?...sslmode=require`. Use the non-pooler hostname.                      |
| `API_ACCESS_TOKEN`                   | Yes      | Random secret of at least 32 characters. Copy the same value to Vercel's matching environment scope. Never use a `NEXT_PUBLIC_` name. |
| `CLOUD_INGESTION_ENABLED`            | No       | `false` initially. Set `true` only on an explicitly approved cron service.                                                            |
| `RECURRING_OPERATIONS_ENABLED`       | No       | `false` initially; set `true` on the API and cron services only when the cron is activated.                                           |
| `GOOGLE_SHEETS_POLL_SECONDS`         | No       | `0` initially. Use `3600` for hourly checks after Sheets credentials and access are approved.                                         |
| `FMP_CONSENSUS_INGESTION_ENABLED`    | No       | Keep `false` until provider terms allow raw storage and display.                                                                      |
| `SEC_USER_AGENT`                     | Optional | App name and monitored contact for SEC requests. Set only on a worker service that needs SEC access.                                  |
| `FMP_API_KEY`                        | Optional | Secret; leave unset while FMP rights are unconfirmed.                                                                                 |
| `GOOGLE_SHEETS_SPREADSHEET_ID`       | Optional | Spreadsheet ID, not a URL.                                                                                                            |
| `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` | Optional | Render Secret File path, for example `/etc/secrets/google-service-account.json`. Never put the JSON key in Git or Vercel.             |
| `GOOGLE_SHEETS_SYNC_TAB`             | Optional | Defaults to `Application Model Sync Inbox`.                                                                                           |

`render.yaml` prompts for `DATABASE_URL` and `API_ACCESS_TOKEN` when the Blueprint is first created. Add optional provider settings later through Render's **Environment** page. Upload a Google service-account key under Render **Environment → Secret Files**, name it `google-service-account.json`, then set `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` to `/etc/secrets/google-service-account.json`. The account needs Viewer access for read-only inbox checks. Work-feed publication writes to fixed tabs, so grant Editor only if that outbound sync is separately approved.

Generate a token locally in PowerShell and paste it into Render and the matching Vercel environment scope. Generate separate values for the API token and each shared web login password; keep them in a password manager:

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$secret = [Convert]::ToBase64String($bytes)
$secret
$rng.Dispose()
```

### Vercel

Set these in **Project → Settings → Environment Variables**. Add production values to **Production** and isolated values to **Preview**:

| Variable              | Production                                                               | Preview                                                                               |
| --------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| `API_BASE_URL`        | Main Render API origin, for example `https://portfolio-api.onrender.com` | Separate preview Render API origin. Leave unset until an isolated preview API exists. |
| `API_ACCESS_TOKEN`    | Same secret as the Render production API                                 | Different secret from the preview API. Leave unset until that service exists.         |
| `WEB_ACCESS_USERNAME` | Private developer login name                                             | Preview login name; may be distinct.                                                  |
| `WEB_ACCESS_PASSWORD` | Long, random shared password                                             | Separate long, random password.                                                       |

The API fails startup if a remote `DATABASE_URL` is missing, is not TLS-protected, uses a transaction-pooler host, or if `API_ACCESS_TOKEN` is missing/short. The API proxy returns 503 if its token is missing in production or if `API_BASE_URL` is not HTTPS. The Basic Auth gate returns 503 if either `WEB_ACCESS_*` value is missing. This keeps a misconfigured deployment closed. The backend token is only added to server-to-server requests and is never returned to the browser.

Do not point Preview at the production API/database. Until a separate preview Render API and Neon branch are set up, Vercel can still build branch previews, but those previews have no API access. For an interactive preview, create a second Render service from the same repo on a preview branch with its own `APP_ENV=preview`, Neon branch URL, API token and separate Basic Auth values.

### Local `.env`

Local development defaults to `APP_ENV=development`, where the remote auth gates are not applied. The root `.env.example` documents the cloud-only names; put real values only in ignored `.env` or provider secret settings.

## Neon connection, TLS and pooling

Create a Neon project in the same region as Render when possible (Frankfurt is configured in the Blueprint). Choose PostgreSQL 18 to match the major version verified by the repository's existing PostgreSQL setup. In Neon, copy the **Direct connection** URL. Replace the URI scheme `postgresql://` with `postgresql+psycopg://` and retain `sslmode=require`, for example:

```text
postgresql+psycopg://<role>:<url-encoded-password>@<direct-endpoint>:5432/<database>?sslmode=require
```

The password must be URL-encoded. Never put the real URL in this guide, Git, Vercel client variables or a browser request. Existing SQLAlchemy settings use `pool_pre_ping`, a 3-second connection timeout and a bounded pool of 2 connections plus at most 2 overflow connections per process.

Use Neon's direct endpoint for this application. The market and recurring workers acquire session-scoped PostgreSQL advisory locks with `pg_try_advisory_lock`; transaction-pooler connections do not preserve the session semantics these locks require. SQLAlchemy provides the small persistent application-side pool, and `sslmode=require` encrypts each database connection. Alembic reads the same `DATABASE_URL` as the API.

## Migrations and safe database migration

For the current cloud-native recovery assessment and counts-only bootstrap
rehearsal, follow [cloud-native-bootstrap-readiness.md](cloud-native-bootstrap-readiness.md).
That runbook treats a rebuild as a current-state reconstruction and lists the
historical domains that require preservation or explicit omission approval.

Deploying the API does not change the database. For a **new empty Neon database**, apply the checked-in Alembic chain from a trusted workstation after setting its `DATABASE_URL` for that PowerShell session:

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://<role>:<url-encoded-password>@<direct-endpoint>:5432/<database>?sslmode=require'
npm run db:migrate
npm run db:check
Remove-Item Env:DATABASE_URL
```

Then check `https://<your-vercel-domain>/api/health`; it should report `database=connected` and `schema=current`. If the URL or database is wrong, stop and correct it before applying anything. Do not run the command against an existing or unknown cloud database.

### Backup-first procedure for any later data transfer

No portfolio data was copied or transferred by this milestone. A read-only sizing check against the local PostgreSQL database reported 289 MB total database size, 178 MB table/TOAST size and 100 MB index size (278 MB total relation size). The measured database is below Neon Free's current 1 GB project allowance, but the final transfer decision still requires a backup and explicit approval.

When the local database is reachable, use an approved, read-only account to measure database and user-table/index sizes:

```powershell
psql "$env:LOCAL_DATABASE_URL" -X -v ON_ERROR_STOP=1 -c "SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;"
psql "$env:LOCAL_DATABASE_URL" -X -v ON_ERROR_STOP=1 -c "SELECT pg_size_pretty(COALESCE(SUM(pg_table_size(c.oid)),0)) AS table_and_toast_size, pg_size_pretty(COALESCE(SUM(pg_indexes_size(c.oid)),0)) AS index_size, pg_size_pretty(COALESCE(SUM(pg_total_relation_size(c.oid)),0)) AS total_relation_size FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND c.relkind IN ('r','m');"
```

Only after explicit approval to transfer personal portfolio data:

1. Put source and destination PostgreSQL URLs into temporary shell environment variables; use standard `postgresql://` URLs for `pg_dump`/`pg_restore`.
2. Save an encrypted custom-format backup outside the repository. Keep its credentials out of command text and logs.
3. Check the archive with `pg_restore --list <backup-file>` and record measured database, table and index sizes.
4. Restore only to a newly created, empty Neon project/database or disposable Neon branch. Do not use `--clean`, `--if-exists`, `--replace-demo`, `DROP`, or restore over existing cloud records.
5. Verify the restored schema and counts, compare size with the 1 GB Free limit, and test a separately backed-up disposable branch before switching the app.

Example backup and restore commands (placeholders only):

```powershell
pg_dump --format=custom --no-owner --no-acl --file <secure-backup-file> "$env:PG_DUMP_SOURCE_URL"
pg_restore --list <secure-backup-file>
pg_restore --no-owner --no-acl --exit-on-error --single-transaction --dbname "$env:PG_RESTORE_EMPTY_TARGET_URL" <secure-backup-file>
```

If approval to move legacy workbook state is not given, create only the empty schema with Alembic. Any state import must use the existing dry-run/reconcile workflows in [workbook-import.md](workbook-import.md), [model-output-ingestion.md](model-output-ingestion.md), and [native-model-input-migration.md](native-model-input-migration.md). Do not use ad-hoc SQL or change canonical investment state.

Neon Free currently includes 100 CU-hours and 1 GB storage per project; watch both limits. Free-plan instant restore is a short recovery window, not a substitute for a separate logical backup.

## Optional background ingestion

The Render web service starts only `uvicorn`; it never starts either worker in the web process. The API's existing local `npm run dev` worker behavior remains unchanged.

Do not add a Cron service until scheduled ingestion is explicitly approved. When approved, create it from Render **New → Cron Job** with:

- Repository: this GitHub repo; Branch: `main`
- Runtime: Python; Root Directory: `apps/api`
- Build Command: `uv sync --locked --no-dev`
- Schedule: `0 * * * *` (once hourly, UTC)
- Command: `uv run --locked --no-dev python -m portfolio_api.cloud_cron`
- Plan: smallest Cron plan available
- `PYTHON_VERSION=3.13.16`
- `APP_ENV=production`
- `DATABASE_URL`: same Neon direct URL as the API
- `API_ACCESS_TOKEN`: same token as the API service; the shared remote settings validator requires it for the worker process
- `CLOUD_INGESTION_ENABLED=true`
- `RECURRING_OPERATIONS_ENABLED=true`
- `GOOGLE_SHEETS_POLL_SECONDS=3600` only if Sheets polling was approved
- Provider credentials only when each data source and its terms are approved

Set `RECURRING_OPERATIONS_ENABLED=true` on the API service at the same time if the UI should accept manual jobs. Keep FMP consensus off unless storage/display rights are confirmed. The entrypoint runs one market refresh and one due-jobs cycle, prints sanitized status and exits; existing PostgreSQL advisory locks and idempotent domain services remain authoritative. It is safe to rerun after a transient failure. Render guarantees one active run per Cron service, while the database locks also coordinate with other worker processes.

## Setup guide: exact dashboard fields

### 1. Neon

1. Create a project named `portfolio-research` and select PostgreSQL 18, Frankfurt, and a project/branch dedicated to this environment.
2. Open **Connect**, select **Direct connection**, and copy the URL. Use the direct endpoint, set TLS with `sslmode=require`, URL-encode the password, and change the driver prefix to `postgresql+psycopg://` for application settings.
3. Keep the URL in a password manager until entering it in Render. Do not create a second database containing real data unless its transfer is approved.

### 2. Render

1. Open Render Dashboard → **New → Blueprint** and connect this GitHub repo.
2. Select the repository's `main` branch. Render reads root `render.yaml` and shows a Python **Web Service** named `portfolio-api`, region **Frankfurt**, plan **Free**, root directory `apps/api`.
3. Confirm Build Command `uv sync --locked --no-dev`, Start Command `uv run --locked --no-dev uvicorn portfolio_api.main:app --host 0.0.0.0 --port $PORT`, Health Check Path `/health/live`, and `PYTHON_VERSION=3.13.16`.
4. Enter the Neon direct URL for `DATABASE_URL`. Generate a random `API_ACCESS_TOKEN` of at least 32 characters and use the same value later in Vercel Production. Leave provider keys blank. Confirm ingestion variables remain `false` and `GOOGLE_SHEETS_POLL_SECONDS` remains `0`.
5. Apply the Blueprint and wait for the deploy. The Render service URL will be `https://portfolio-api.onrender.com` unless Render reports a naming conflict.
6. Apply Alembic to the empty Neon database using the PowerShell command above. Check Render `https://portfolio-api.onrender.com/health/live` for `200`, then `/health/ready` for `schema=current`.

For an always-on API, change only its compute plan to `0.5c-512mb` (the Render Starter plan) in **Service → Settings → Instance Type**. Do not add persistent disk storage; PostgreSQL lives in Neon.

### 3. Vercel

1. Open Vercel Dashboard → **Add New → Project**, import this repo, then set **Root Directory** to `apps/web`. Keep **Include source files outside of the Root Directory** enabled because the build consumes `packages/contracts` and the root npm workspace. Framework Preset: **Next.js**; Node.js Version: **24.x**.
2. `apps/web/vercel.json` sets Install Command `npm ci --prefix ../..` and Build Command `npm run build --workspace @portfolio/web --prefix ../..`.
3. In **Settings → Git**, set **Production Branch** to `main`; leave Preview Deployments enabled for other GitHub branches and pull requests.
4. In **Settings → Environment Variables**, add `API_BASE_URL`, `API_ACCESS_TOKEN`, `WEB_ACCESS_USERNAME` and `WEB_ACCESS_PASSWORD` for the **Production** scope. Values are server-side; never add `NEXT_PUBLIC_`.
5. Add separate `WEB_ACCESS_*` values for **Preview**. Leave preview API values unset until a separate preview Render service and Neon branch are available.
6. Redeploy after changing environment variables. Vercel production follows `main`; branch and pull-request commits create preview builds.

Vercel Hobby is limited to personal, non-commercial use. Use the plan allowed by the actual purpose of this deployment.

## Verification and known limits

Local verification for this milestone is recorded above. The Neon project and
production branch were verified live, including migrations, readiness and a
temporary FastAPI connection. Render and Vercel have not been connected or
deployed. Before enabling a remote write flow, verify:

1. An unauthenticated Vercel page and `/api/research/*` request return `401`.
2. Authenticated Vercel requests use the server-side token; browser source and responses do not contain it.
3. A direct Render `/v1/*` request without `X-API-Access-Token` returns `401`; direct health checks remain available.
4. `/api/health` reports database connection and current Alembic schema.
5. Preview uses an isolated Neon branch/API before enabling its API token.
6. An optional cron is absent until approved; when later created, its disabled gate is tested before setting `CLOUD_INGESTION_ENABLED=true`.

The local database sizing check is recorded above. The root `.env` remains a local-development configuration and must not be replaced with a Neon URL during normal local work.

## Estimated monthly costs

| Configuration                                 | Estimated recurring cost | Notes                                                                                                                                                                  |
| --------------------------------------------- | -----------------------: | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Vercel Hobby + Render Free API + Neon Free    |                     `$0` | Render Free sleeps after 15 minutes idle; the first request can take about a minute to wake. Neon Free currently includes 1 GB/project and 100 CU-hours/project/month. |
| Vercel Hobby + Render Starter API + Neon Free |               `$7/month` | Always-on 0.5 CPU / 512 MB Render API.                                                                                                                                 |
| Previous row + one Render Cron service        | `about $8/month minimum` | Render Cron has a $1/month minimum plus billed runtime. Additional usage, bandwidth or taxes can raise totals.                                                         |

Vercel Hobby is $0 but is for personal, non-commercial use. Render's current smallest always-on web service is $7/month; Cron charges have a $1/month service minimum. Neon Free is $0 within its limits. See [Vercel pricing](https://vercel.com/pricing), [Render pricing](https://render.com/pricing), [Render Free limits](https://render.com/docs/free), [Render Cron billing](https://render.com/docs/cronjobs), and [Neon pricing](https://neon.com/pricing) for current terms.

At the Neon inspection, project CPU usage and branch active time were both
reported as `0`. The project defaults reported autoscaling from 0.25 to 8 CU
and `suspend_timeout_seconds=0`; confirm the desired autosuspend behavior in the
Neon console before relying on a free-plan cost estimate.
