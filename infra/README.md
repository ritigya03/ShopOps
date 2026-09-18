# ShopOps production provisioning runbook

Run these in order. Everything after step 2 is scripted; steps 1-2 are
manual because a brand-new AWS account has no IAM user yet (and the
root account should never get access keys).

## 1. Create an IAM admin user (console, one-time)

1. Log into the AWS Console as the root user (the account you just created).
2. IAM → Users → Create user → name it e.g. `shopops-admin`.
3. Attach the `AdministratorAccess` policy directly (fine for a personal
   project; tightening this to least-privilege is a later hardening
   pass, not required to get to production).
4. Create an access key for this user (IAM → Users → shopops-admin →
   Security credentials → Create access key → "Command Line Interface (CLI)").
5. Save the Access Key ID and Secret Access Key somewhere safe — AWS
   only shows the secret once.

## 2. Configure the AWS CLI

```bash
aws configure
# AWS Access Key ID: <from step 1>
# AWS Secret Access Key: <from step 1>
# Default region name: ap-south-1
# Default output format: json
```

## 3. Run the provisioning scripts, in order

```bash
./infra/scripts/00_check_prereqs.sh
./infra/scripts/01_create_key_pair.sh
./infra/scripts/02_create_security_groups.sh
./infra/scripts/03_create_ec2.sh        # takes a minute or two
./infra/scripts/04_create_rds.sh        # takes several minutes
./infra/scripts/05_create_cognito.sh
```

After this, `infra/outputs.env` has every resource id/endpoint you need
below. **This file contains the RDS master password in plaintext — it's
gitignored, keep it that way.**

Note: `06_run_migrations.sh` is deliberately *not* run here. RDS is
`--no-publicly-accessible` — it's only reachable from the EC2 box's
security group, not from your laptop. Migrations run from the EC2 box
itself in step 5, after the compose stack is up.

## 4. Create Cognito test users

For each of the three roles, create a user and add them to the matching
group (repeat with real emails/passwords):

```bash
source infra/outputs.env

aws cognito-idp admin-create-user --region ap-south-1 \
  --user-pool-id "$COGNITO_USER_POOL_ID" \
  --username "manager@example.com" \
  --user-attributes Name=email,Value=manager@example.com Name=email_verified,Value=true \
  --message-action SUPPRESS \
  --temporary-password "TempPass123!"

aws cognito-idp admin-set-user-password --region ap-south-1 \
  --user-pool-id "$COGNITO_USER_POOL_ID" \
  --username "manager@example.com" \
  --password "RealPass123!" --permanent

aws cognito-idp admin-add-user-to-group --region ap-south-1 \
  --user-pool-id "$COGNITO_USER_POOL_ID" \
  --username "manager@example.com" \
  --group-name OperationsManager
```

Repeat for a `SupportAgent` and a `Viewer` user.

## 5. SSH in and bring the app up

```bash
source infra/outputs.env
ssh -i infra/shopops-prod.pem ubuntu@"$EC2_ELASTIC_IP"
```

On the EC2 box:

```bash
sudo apt-get update && sudo apt-get install -y git
curl -fsSL https://get.docker.com | sudo sh   # installs Docker Engine + the `docker compose` v2 plugin together; Ubuntu's own apt repos don't reliably ship the compose plugin
sudo usermod -aG docker ubuntu   # log out/in again for this to take effect
sudo mkdir -p /opt/shopops && sudo chown ubuntu:ubuntu /opt/shopops
cd /opt/shopops
git clone <this-repo-url> .
cp .env.prod.example .env.prod
# edit .env.prod: fill in LOCAL_DATABASE_URL (use RDS_ENDPOINT/RDS_MASTER_PASSWORD
# from infra/outputs.env), COGNITO_USER_POOL_ID, COGNITO_APP_CLIENT_ID,
# GEMINI_API_KEY, and CORS_ORIGINS=https://<this box's Elastic IP>
./nginx/generate-self-signed-cert.sh <this box's Elastic IP>
docker compose -f docker-compose.prod.yml up -d --build
```

Verify: `curl -k https://localhost/openapi.json` returns the OpenAPI
schema.

## 5b. Run migrations (from the EC2 box, not your laptop)

RDS is only reachable from inside the EC2 box's security group, so
`06_run_migrations.sh` has to run there — not from your laptop where you
ran the other provisioning scripts. `infra/outputs.env` already has
everything the script needs (`RDS_ENDPOINT`, `RDS_MASTER_USER`,
`RDS_MASTER_PASSWORD`, `RDS_DB_NAME`), so just copy it over and run the
script on the box (Docker is already installed there from step 5):

```bash
# from your laptop, in the repo root:
source infra/outputs.env
scp -i infra/shopops-prod.pem infra/outputs.env ubuntu@"$EC2_ELASTIC_IP":/opt/shopops/infra/outputs.env

# then on the EC2 box:
ssh -i infra/shopops-prod.pem ubuntu@"$EC2_ELASTIC_IP"
cd /opt/shopops
./infra/scripts/06_run_migrations.sh
```

Expected: each `db/migrations/*.sql` file prints as it's applied with no
`psql` errors, ending in `All migrations applied to <RDS_ENDPOINT>`.

## 5c. Seed production data (ingestion)

A freshly-migrated database has schemas but no rows, and Qdrant has no
`shopops_policy` collection yet — every read endpoint and `/policy/search`
will return empty until this runs. `data/raw/*.csv` and `data/policy/*.md`
are committed to the repo, so they're already on the EC2 box after
`git clone`, and the `Dockerfile` copies both `scripts/` and `data/` into
the `app` image. Run these once, from the EC2 box, with the compose stack
already up:

```bash
cd /opt/shopops
docker compose -f docker-compose.prod.yml exec app python scripts/ingest.py
docker compose -f docker-compose.prod.yml exec app python scripts/register_policy_docs.py
docker compose -f docker-compose.prod.yml exec app python scripts/ingest_policy_to_qdrant.py
```

These mirror the local-dev commands documented in `README.md`'s "Policy
documents" and "Qdrant (policy retrieval)" sections — `ingest.py` loads the
Olist CSVs into `shopops_data`, `register_policy_docs.py` syncs
`data/policy/*.md` metadata into `shopops_ops.policy_documents`, and
`ingest_policy_to_qdrant.py` chunks/embeds those same files into the
`shopops_policy` Qdrant collection. All three are safe to re-run.

## 6. Wire up GitHub Actions

The `deploy` job needs to open port 22 on the EC2 security group
temporarily for each deploy (GitHub's hosted runners connect from
arbitrary IPs, not a fixed one the security group could allow up front),
then close it again afterwards. That needs a narrowly-scoped IAM user and
a couple more secrets, on top of the two you'd expect for SSH.

### One-time IAM setup for the deploy user

1. IAM → Users → Create user, e.g. `shopops-deploy-ci`. No console access
   needed — programmatic access only.
2. Attach an inline policy scoped to exactly this one security group (get
   `EC2_SG_ID` from `infra/outputs.env`):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "ec2:AuthorizeSecurityGroupIngress",
           "ec2:RevokeSecurityGroupIngress"
         ],
         "Resource": "arn:aws:ec2:ap-south-1:<YOUR_ACCOUNT_ID>:security-group/<EC2_SG_ID>"
       }
     ]
   }
   ```

3. Create an access key for this user (Security credentials → Create
   access key → "Application running outside AWS" or "CLI"). Save both
   values — this is the only time the secret is shown.

This user can do nothing but open/close port 22 on the one security group
ShopOps uses — it cannot read data, start/stop instances, or touch RDS.

### GitHub repo secrets

In the GitHub repo settings → Secrets and variables → Actions, add:
- `EC2_HOST` = the Elastic IP (`$EC2_ELASTIC_IP` from `infra/outputs.env`)
- `EC2_SSH_KEY` = the full contents of `infra/shopops-prod.pem`
- `EC2_SG_ID` = the EC2 security group id (`$EC2_SG_ID` from
  `infra/outputs.env`)
- `AWS_REGION` = `ap-south-1`
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` = the access key pair for
  the `shopops-deploy-ci` IAM user created above

Push to `main` — the `deploy` job in `.github/workflows/ci.yml` will
authorize the runner's current IP on `EC2_SG_ID`, SSH in and redeploy, then
revoke that IP again (via an `if: always()` step, so it happens even if
the deploy step fails) from then on.

## Known limitation: browser CORS + self-signed cert

Because the API has no real domain yet and uses a self-signed cert (see
the design spec, §6), a browser frontend running on a *different* origin
(e.g. the Next.js app in `shop-ops-ai-frontend/`, hosted on Vercel or
similar) will have its `fetch()`/XHR calls to this API silently rejected
by the browser — self-signed certs aren't trusted cross-origin the way a
same-origin/no-CORS page load is. This isn't just a warning banner; it's a
hard browser refusal.

Until a real domain + a trusted cert (Let's Encrypt) replaces the
self-signed one, there are two workarounds:
1. Have each user manually visit the API's `https://<EC2_ELASTIC_IP>/`
   URL once in their browser and click through the certificate warning to
   accept the exception, before using the frontend.
2. Swap in Let's Encrypt once a real domain exists — flagged as a future
   follow-up in the design spec (§6, §11), same Nginx config structure,
   just a different cert source.
