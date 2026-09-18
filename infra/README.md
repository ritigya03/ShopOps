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
./infra/scripts/06_run_migrations.sh
```

After this, `infra/outputs.env` has every resource id/endpoint you need
below. **This file contains the RDS master password in plaintext — it's
gitignored, keep it that way.**

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

## 6. Wire up GitHub Actions

In the GitHub repo settings → Secrets and variables → Actions, add:
- `EC2_HOST` = the Elastic IP (`$EC2_ELASTIC_IP` from `infra/outputs.env`)
- `EC2_SSH_KEY` = the full contents of `infra/shopops-prod.pem`

Push to `main` — the `deploy` job in `.github/workflows/ci.yml` will SSH
in and redeploy automatically from then on.
