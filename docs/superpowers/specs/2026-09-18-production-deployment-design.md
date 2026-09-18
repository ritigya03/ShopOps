# Production deployment & cloud infrastructure — design

## 1. Goal

Stand up a real production deployment of ShopOps on AWS per the TDD's §11
requirements: EC2 app host, managed Postgres, Qdrant, Cognito, a production
Docker Compose stack behind Nginx/SSL, and a GitHub Actions pipeline that
lints/tests on every push and deploys `main` to EC2. Carrier webhook
ingestion and the multi-agent supervisor split are explicitly out of scope —
this spec only covers getting the existing single-agent app running in
production.

## 2. Key decisions

| Decision | Choice | Rationale |
|---|---|---|
| Postgres | AWS RDS (`db.t3.micro`, Postgres 16) | Managed backups/patching, decouples DB lifecycle from the app box, free-tier eligible on a new AWS account. |
| Qdrant | Self-hosted container on the EC2 box | No new external account/dependency; matches the existing local Docker setup; cost is just EC2 disk/CPU. |
| Domain / SSL | None yet — self-signed cert against the raw EC2 IP | No domain currently owned. Browsers will show a warning; upgrading to a real domain + Let's Encrypt is a drop-in follow-up once one exists. |
| Background workers | Not provisioned | Nothing in `app/` needs an async worker yet (see `README.md`, `app/` has no worker/queue code). Compose is structured so a worker service can be added later without restructuring. |
| CI/CD deploy mechanism | GitHub Actions SSHes into EC2, `git pull` + `docker compose up -d --build` | Simplest mechanism for a single box; no container registry to provision or manage. |
| Secrets on EC2 | Plain `.env.prod`, created once by hand via SSH, never touched by the deploy pipeline | Matches project's existing `.env` pattern; avoids standing up SSM/IAM-role plumbing for a single-box deployment. |
| Region | `ap-south-1` (Mumbai) | Matches the region already referenced in `.env.example` for Cognito. |
| EC2 instance size | `t3.micro` | Free-tier eligible; only running app + Qdrant + Nginx (Postgres is offloaded to RDS). |

## 3. Architecture

```
                        ┌─────────────────────────────┐
   GitHub Actions ─SSH─▶│  EC2 (t3.micro, ap-south-1) │
   (on push to main)    │  ┌────────┐  ┌────────────┐ │
                        │  │ nginx  │─▶│  app        │ │
                        │  │ :80/443│  │  (FastAPI)  │ │
                        │  └────────┘  └─────┬──────┘ │
                        │                     │        │
                        │              ┌──────▼──────┐ │
                        │              │   qdrant     │ │
                        │              │ (container)  │ │
                        │              └─────────────┘ │
                        └─────────────────┬────────────┘
                                          │ (SG-restricted, 5432)
                                   ┌──────▼───────┐
                                   │  RDS Postgres │
                                   │  db.t3.micro  │
                                   └───────────────┘

   Cognito User Pool (ap-south-1) — used by app/auth.py, no network path
   from EC2 needed beyond outbound HTTPS to the Cognito API.
```

- `app` calls out to RDS (Postgres) and the local `qdrant` container exactly
  as it does today against local Docker Postgres/Qdrant — only the
  connection strings in `.env.prod` differ from `.env`.
- `nginx` is the only container exposed to the internet (80/443). `app` and
  `qdrant` are only reachable from `nginx`/each other on the Docker network.

## 4. AWS resources (first-time provisioning)

Since the AWS account was just created for this project, provisioning starts
from scratch:

1. **IAM user** for CLI/console work — do not use the root account
   day-to-day. Broad permissions for now (EC2/RDS/Cognito/VPC); tightening to
   least-privilege is a later hardening pass, not in scope here.
2. **EC2 key pair** (`shopops-prod.pem`) in `ap-south-1`.
3. **Security groups**:
   - `shopops-ec2-sg`: inbound 22/tcp from your IP only, 80/tcp + 443/tcp
     from `0.0.0.0/0`. Outbound unrestricted.
   - `shopops-rds-sg`: inbound 5432/tcp from `shopops-ec2-sg` only — never
     public.
4. **EC2 instance**: `t3.micro`, Ubuntu 22.04 LTS, `shopops-ec2-sg`, with an
   Elastic IP attached so the address survives stop/start.
5. **RDS instance**: `db.t3.micro`, Postgres 16, `shopops-rds-sg`, not
   publicly accessible, automated backups on (default retention).
6. **Cognito User Pool** + app client in `ap-south-1`, replacing the
   placeholder `COGNITO_USER_POOL_ID`/`COGNITO_APP_CLIENT_ID` values in
   `.env.example`. Same role-based setup already coded against in
   `app/auth.py` — just a real pool instead of a not-yet-created one.

## 5. Production Docker Compose

New file `docker-compose.prod.yml`, separate from the existing
`docker-compose.yml` (which stays as the local dev stack with local
Postgres + Qdrant, untouched):

- **`app`** — built from a new `Dockerfile` (none exists yet). Runs
  `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Reads `.env.prod`.
- **`qdrant`** — same image as local (`qdrant/qdrant:latest`), with a named
  volume for storage persistence across restarts.
- **`nginx`** — reverse proxy; terminates TLS with the self-signed cert;
  proxies `/` to `app:8000`.
- No `postgres` service (RDS instead) and no worker service (§2).

`Dockerfile` (new, at repo root): standard Python slim base, installs
`requirements.txt`, copies `app/`, runs as a non-root user.

## 6. Nginx

- Self-signed cert generated once on the EC2 box (`openssl req -x509 ...`,
  CN = the Elastic IP), mounted read-only into the `nginx` container.
- Config: HTTP (80) redirects to HTTPS; HTTPS (443) proxies to `app:8000`
  with standard `proxy_set_header` forwarding (`Host`,
  `X-Forwarded-For`, `X-Forwarded-Proto`).
- Follow-up (out of scope now, noted for later): once a domain exists, swap
  the self-signed cert for Certbot/Let's Encrypt — same Nginx config
  structure, just a different cert source.

## 7. Secrets

- `.env.prod` lives only on the EC2 box, created once by hand over SSH
  (RDS endpoint/credentials, real Cognito ids, `GEMINI_API_KEY`, etc.). Not
  committed to git, not written or read by the deploy pipeline.
- GitHub Actions needs exactly two repo secrets: `EC2_SSH_KEY` (the private
  key contents) and `EC2_HOST` (the Elastic IP), used only to SSH in and run
  the deploy command.

## 8. CI/CD

Extend `.github/workflows/ci.yml` with a `deploy` job:

- Trigger: `push` to `main`, `needs: lint-and-test` (so a failing
  lint/test run blocks deploy — no change to the existing job).
- Steps: SSH into `EC2_HOST` using `EC2_SSH_KEY`
  (`appleboy/ssh-action` or equivalent), run:
  ```
  cd /opt/shopops && git pull && docker compose -f docker-compose.prod.yml up -d --build
  ```
- No new AWS resource needed for this (no ECR, no CodeDeploy).

## 9. Database migrations against RDS

`db/migrations/*.sql` currently runs automatically via Postgres's
`docker-entrypoint-initdb.d` mechanism, which only fires on a fresh
container's first startup — RDS doesn't support this. One-time manual step
documented in the implementation plan: run the migration SQL files against
the RDS endpoint with `psql` after the instance is created. No migration
tool (Alembic etc.) introduced — out of scope, same as the local setup
today.

## 10. Testing / verification

- CI's existing `pytest -m "not integration"` run is unaffected by any of
  this — no test changes required.
- Manual verification after first deploy: hit `https://<elastic-ip>/` (with
  the self-signed cert warning accepted) and confirm the existing
  auth/agent endpoints respond, same as they do locally against
  `localhost:8000`.
- No new automated tests are introduced by this spec — it's infrastructure,
  not application code.

## 11. Explicitly out of scope

- Carrier webhook ingestion (FedEx/UPS/DHL) — separate follow-on spec.
- Multi-agent supervisor split (Logistics/Compensation/Policy agents) —
  separate follow-on spec, and per prior discussion, deferred until
  production logging/metrics show the single-agent design straining.
- Real domain name + Let's Encrypt (noted as a future swap-in, §6).
- SSM Parameter Store / IAM-role-based secrets injection.
- ECR / build-once-deploy-artifact pipeline.
- Least-privilege IAM policy tightening for the provisioning IAM user.
- Alembic or any DB migration tooling.
- Auto-scaling, load balancing, multi-AZ RDS, or any HA concerns — this is
  a single-box deployment.
