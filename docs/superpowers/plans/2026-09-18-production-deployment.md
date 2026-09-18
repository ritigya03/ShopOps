# Production Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get ShopOps running in production on AWS — EC2 app host behind Nginx/SSL, RDS Postgres, self-hosted Qdrant, a real Cognito pool, and a GitHub Actions pipeline that deploys `main` on push.

**Architecture:** A single EC2 box runs `app` + `qdrant` + `nginx` via `docker-compose.prod.yml`; Postgres lives on RDS; Cognito is a separate managed service. AWS resources are provisioned with numbered, idempotent-order shell scripts under `infra/scripts/` that chain their outputs through `infra/outputs.env`, rather than clicked through the console.

**Tech Stack:** Docker, Docker Compose, Nginx, AWS CLI v2, GitHub Actions, existing FastAPI app (Python 3.11, `requirements.txt`).

**Spec:** `docs/superpowers/specs/2026-09-18-production-deployment-design.md`

## Global Constraints

- Postgres: AWS RDS, `db.t3.micro`, Postgres 16, not publicly accessible.
- Qdrant: self-hosted container on the EC2 box, not a managed service.
- No domain name yet — Nginx uses a self-signed cert against the Elastic IP.
- No background worker service is provisioned.
- Region: `ap-south-1` for every resource (EC2, RDS, Cognito).
- EC2 instance: `t3.micro`.
- Deploy mechanism: GitHub Actions SSHes into EC2 and runs `git pull && docker compose -f docker-compose.prod.yml up -d --build`. No container registry.
- Secrets live only in `.env.prod` on the EC2 box, created by hand, never read or written by the deploy pipeline, never committed.
- The app reads `LOCAL_DATABASE_URL` (not `DATABASE_URL`) for its Postgres connection string, per `app/config.py:10` — this is the existing variable name and must be reused as-is for the RDS connection string in production.
- Cognito auth requires `cognito:groups` to contain one of exactly `OperationsManager`, `SupportAgent`, `Viewer` (`app/auth.py:12`) — the user pool must have these three groups.
- `verify_cognito_tokens.py` calls `initiate_auth` with `AuthFlow="USER_PASSWORD_AUTH"` and no `SECRET_HASH` — the app client must be created with `--no-generate-secret`.

---

### Task 1: Dockerfile for the app

**Files:**
- Create: `Dockerfile`

**Interfaces:**
- Produces: an image that runs `uvicorn app.main:app` on port 8000, consumed by `docker-compose.prod.yml` (Task 2) via `build: .`.

- [ ] **Step 1: Write the Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Build the image locally to verify it works**

Run: `docker build -t shopops-app:test .`
Expected: build completes with exit code 0, ending in
`=> naming to docker.io/library/shopops-app:test`.

- [ ] **Step 3: Verify the container actually starts and serves traffic**

Run:
```bash
docker run --rm -d --name shopops-app-test \
  -e LOCAL_DATABASE_URL="postgresql+psycopg2://dummy:dummy@localhost/dummy" \
  -e COGNITO_REGION="ap-south-1" \
  -e COGNITO_USER_POOL_ID="dummy" \
  -e COGNITO_APP_CLIENT_ID="dummy" \
  -e GEMINI_API_KEY="dummy" \
  -p 18000:8000 \
  shopops-app:test
sleep 2
curl -sf http://localhost:18000/openapi.json > /dev/null && echo "OK"
docker stop shopops-app-test
```
Expected: prints `OK` (the container serves FastAPI's auto-generated
OpenAPI schema without needing real Postgres/Cognito connections, since
that route doesn't touch either).

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "feat: add production Dockerfile for the FastAPI app"
```

---

### Task 2: Production Docker Compose stack

**Files:**
- Create: `docker-compose.prod.yml`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `Dockerfile` (Task 1), `nginx/nginx.conf` + `nginx/certs/` (Task 4), `.env.prod` (Task 3, not committed).
- Produces: three services (`app`, `qdrant`, `nginx`) on one Docker network, referenced by the deploy step in Task 5 and the runbook in Task 12.

- [ ] **Step 1: Write `docker-compose.prod.yml`**

```yaml
services:
  app:
    build: .
    container_name: shopops_app
    restart: unless-stopped
    env_file:
      - .env.prod
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/openapi.json')"]
      interval: 10s
      timeout: 5s
      retries: 5
    expose:
      - "8000"

  qdrant:
    image: qdrant/qdrant:latest
    container_name: shopops_qdrant
    restart: unless-stopped
    volumes:
      - shopops_qdrant_storage:/qdrant/storage
    expose:
      - "6333"
      - "6334"

  nginx:
    image: nginx:1.27-alpine
    container_name: shopops_nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro
    depends_on:
      - app

volumes:
  shopops_qdrant_storage:
    name: shopops_qdrant_storage
```

- [ ] **Step 2: Add `.env.prod` to `.gitignore`**

In `.gitignore`, add a line after the existing `.env` entry:
```
.env.prod
```

- [ ] **Step 3: Validate the compose file syntax**

Run:
```bash
echo "GEMINI_API_KEY=dummy" > .env.prod
docker compose -f docker-compose.prod.yml config --quiet && echo "VALID"
rm .env.prod
```
Expected: prints `VALID` with no errors (this only checks YAML/schema
validity and that `.env.prod` exists — it does not build or start
anything, since `nginx/nginx.conf` and `nginx/certs/` don't exist until
Task 4).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.prod.yml .gitignore
git commit -m "feat: add production docker-compose stack (app, qdrant, nginx)"
```

---

### Task 3: `.env.prod.example` template

**Files:**
- Create: `.env.prod.example`

**Interfaces:**
- Produces: the documented list of env vars `docker-compose.prod.yml`'s `app` service needs via `.env.prod` — consumed by whoever creates the real `.env.prod` on the EC2 box in Task 12.

- [ ] **Step 1: Write the template**

```bash
# Production environment for ShopOps — copy to .env.prod on the EC2 box
# and fill in real values. This file itself is NOT the real secrets file
# and is safe to commit (see .env.prod in .gitignore).

# RDS Postgres endpoint. NOTE: the app reads LOCAL_DATABASE_URL (not
# DATABASE_URL) for this — see app/config.py.
LOCAL_DATABASE_URL=postgresql+psycopg2://shopops_admin:<RDS_MASTER_PASSWORD>@<RDS_ENDPOINT>:5432/shopops

# Qdrant runs as the `qdrant` service on the same Docker network.
QDRANT_URL=http://qdrant:6333

# AWS Cognito (from infra/scripts/05_create_cognito.sh output)
COGNITO_REGION=ap-south-1
COGNITO_USER_POOL_ID=<COGNITO_USER_POOL_ID>
COGNITO_APP_CLIENT_ID=<COGNITO_APP_CLIENT_ID>

# Google Gemini (LiteLLM) - agent orchestrator
GEMINI_API_KEY=<your-gemini-api-key>
AGENT_MODEL=gemini/gemini-3.1-flash-lite

# Frontend origin allowed to call this API. Update once the frontend has
# a real deployed origin; for now this is the EC2 Elastic IP itself.
CORS_ORIGINS=https://<EC2_ELASTIC_IP>

LOG_LEVEL=INFO
```

- [ ] **Step 2: Verify every var `app/config.py` requires is present**

Run:
```bash
grep -oE 'os\.environ(\.get)?\["?[A-Z_]+"?' app/config.py | grep -oE '[A-Z_]+$' | sort -u
grep -oE '^[A-Z_]+=' .env.prod.example | sed 's/=$//' | sort -u
```
Expected: every name from the first command's output appears in the
second command's output (`LOCAL_DATABASE_URL`, `COGNITO_REGION`,
`COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID`, `GEMINI_API_KEY`) —
`QDRANT_URL`, `AGENT_MODEL`, `CORS_ORIGINS`, `LOG_LEVEL` are optional
with defaults in `config.py` but are included anyway for explicitness.

- [ ] **Step 3: Commit**

```bash
git add .env.prod.example
git commit -m "docs: add .env.prod.example template for production config"
```

---

### Task 4: Nginx reverse proxy + self-signed cert

**Files:**
- Create: `nginx/nginx.conf`
- Create: `nginx/generate-self-signed-cert.sh`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing (runs standalone on the EC2 box before first `docker compose up`).
- Produces: `nginx/certs/selfsigned.crt` + `nginx/certs/selfsigned.key`, mounted into the `nginx` service in `docker-compose.prod.yml` (Task 2).

- [ ] **Step 1: Write `nginx/nginx.conf`**

```nginx
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/nginx/certs/selfsigned.crt;
    ssl_certificate_key /etc/nginx/certs/selfsigned.key;

    location / {
        proxy_pass http://app:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

- [ ] **Step 2: Write `nginx/generate-self-signed-cert.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

IP="${1:?Usage: generate-self-signed-cert.sh <elastic-ip>}"
CERT_DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -days 365 \
  -newkey rsa:2048 \
  -keyout "$CERT_DIR/selfsigned.key" \
  -out "$CERT_DIR/selfsigned.crt" \
  -subj "/CN=$IP"

echo "Certificate written to $CERT_DIR"
```

```bash
chmod +x nginx/generate-self-signed-cert.sh
```

- [ ] **Step 3: Add generated certs to `.gitignore`**

In `.gitignore`, add:
```
nginx/certs/
```

- [ ] **Step 4: Verify the script produces a cert Nginx actually accepts**

Run:
```bash
./nginx/generate-self-signed-cert.sh 127.0.0.1
docker run --rm \
  -v "$(pwd)/nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v "$(pwd)/nginx/certs:/etc/nginx/certs:ro" \
  nginx:1.27-alpine nginx -t
rm -rf nginx/certs
```
Expected: `nginx: configuration file /etc/nginx/nginx.conf test is
successful`. The `rm -rf` cleans up the test cert — the real one gets
generated on the EC2 box in Task 12, not committed.

- [ ] **Step 5: Commit**

```bash
git add nginx/nginx.conf nginx/generate-self-signed-cert.sh .gitignore
git commit -m "feat: add nginx reverse proxy config and self-signed cert script"
```

---

### Task 5: GitHub Actions deploy job

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: GitHub repo secrets `EC2_HOST`, `EC2_SSH_KEY` (set by hand in the GitHub UI in Task 12 — not something a script can create).
- Produces: an automatic deploy to EC2 on every push to `main` that passes `lint-and-test`.

- [ ] **Step 1: Add the `deploy` job to `.github/workflows/ci.yml`**

Append after the existing `lint-and-test` job (keep that job exactly as
it is):

```yaml
  deploy:
    needs: lint-and-test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to EC2
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ubuntu
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /opt/shopops
            git pull
            docker compose -f docker-compose.prod.yml up -d --build
```

- [ ] **Step 2: Validate the workflow YAML is well-formed**

Run: `source .venv/bin/activate && python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('VALID')"`
Expected: prints `VALID` with no exception.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat: add GitHub Actions deploy job (SSH + compose up on push to main)"
```

---

### Task 6: AWS CLI prereq check + EC2 key pair script

**Files:**
- Create: `infra/scripts/00_check_prereqs.sh`
- Create: `infra/scripts/01_create_key_pair.sh`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `aws configure` having already been run by hand with a real
  IAM user's access key (documented as the one unavoidable manual
  console step in Task 12 — a brand-new AWS account's first IAM user
  cannot be created via CLI without root credentials, which should never
  be turned into access keys).
- Produces: `infra/shopops-prod.pem`, the key pair every later EC2 script
  references by name (`shopops-prod`).

**Note on testability:** none of the `infra/scripts/*.sh` files in this
plan can be run to completion in this environment — there's no AWS CLI
installed here and no AWS credentials. Each script's test step is a
syntax check (`bash -n`); full functional verification happens when the
user runs them for real in Task 12, per the runbook written in Task 11.

- [ ] **Step 1: Write `infra/scripts/00_check_prereqs.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

command -v aws >/dev/null 2>&1 || {
  echo "aws CLI not found. Install it: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
  exit 1
}

aws sts get-caller-identity --output table
echo "AWS CLI is configured. Region: $(aws configure get region)"
```

- [ ] **Step 2: Write `infra/scripts/01_create_key_pair.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

REGION="ap-south-1"
KEY_NAME="shopops-prod"
INFRA_DIR="$(cd "$(dirname "$0")/.." && pwd)"

aws ec2 create-key-pair \
  --region "$REGION" \
  --key-name "$KEY_NAME" \
  --query 'KeyMaterial' \
  --output text > "$INFRA_DIR/$KEY_NAME.pem"

chmod 400 "$INFRA_DIR/$KEY_NAME.pem"
echo "Key pair saved to $INFRA_DIR/$KEY_NAME.pem"
```

```bash
chmod +x infra/scripts/00_check_prereqs.sh infra/scripts/01_create_key_pair.sh
```

- [ ] **Step 3: Gitignore the key pair and the outputs file these scripts will produce**

In `.gitignore`, add:
```
infra/*.pem
infra/outputs.env
```

- [ ] **Step 4: Syntax-check both scripts**

Run: `bash -n infra/scripts/00_check_prereqs.sh && bash -n infra/scripts/01_create_key_pair.sh && echo "SYNTAX OK"`
Expected: prints `SYNTAX OK`.

- [ ] **Step 5: Commit**

```bash
git add infra/scripts/00_check_prereqs.sh infra/scripts/01_create_key_pair.sh .gitignore
git commit -m "feat: add AWS prereq check and EC2 key pair provisioning script"
```

---

### Task 7: Security groups script

**Files:**
- Create: `infra/scripts/02_create_security_groups.sh`

**Interfaces:**
- Consumes: nothing (looks up the account's default VPC itself).
- Produces: appends `VPC_ID`, `EC2_SG_ID`, `RDS_SG_ID` to `infra/outputs.env`, consumed by Task 8 and Task 9's scripts.

- [ ] **Step 1: Write `infra/scripts/02_create_security_groups.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

REGION="ap-south-1"
INFRA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_FILE="$INFRA_DIR/outputs.env"
MY_IP="$(curl -s https://checkip.amazonaws.com)/32"

VPC_ID="$(aws ec2 describe-vpcs --region "$REGION" \
  --filters Name=is-default,Values=true \
  --query 'Vpcs[0].VpcId' --output text)"

EC2_SG_ID="$(aws ec2 create-security-group --region "$REGION" \
  --group-name shopops-ec2-sg \
  --description "ShopOps EC2 app host" \
  --vpc-id "$VPC_ID" \
  --query 'GroupId' --output text)"

aws ec2 authorize-security-group-ingress --region "$REGION" \
  --group-id "$EC2_SG_ID" --protocol tcp --port 22 --cidr "$MY_IP" >/dev/null
aws ec2 authorize-security-group-ingress --region "$REGION" \
  --group-id "$EC2_SG_ID" --protocol tcp --port 80 --cidr 0.0.0.0/0 >/dev/null
aws ec2 authorize-security-group-ingress --region "$REGION" \
  --group-id "$EC2_SG_ID" --protocol tcp --port 443 --cidr 0.0.0.0/0 >/dev/null

RDS_SG_ID="$(aws ec2 create-security-group --region "$REGION" \
  --group-name shopops-rds-sg \
  --description "ShopOps RDS Postgres" \
  --vpc-id "$VPC_ID" \
  --query 'GroupId' --output text)"

aws ec2 authorize-security-group-ingress --region "$REGION" \
  --group-id "$RDS_SG_ID" --protocol tcp --port 5432 \
  --source-group "$EC2_SG_ID" >/dev/null

{
  echo "VPC_ID=$VPC_ID"
  echo "EC2_SG_ID=$EC2_SG_ID"
  echo "RDS_SG_ID=$RDS_SG_ID"
} >> "$OUT_FILE"

echo "Security groups created and written to $OUT_FILE"
```

```bash
chmod +x infra/scripts/02_create_security_groups.sh
```

- [ ] **Step 2: Syntax-check**

Run: `bash -n infra/scripts/02_create_security_groups.sh && echo "SYNTAX OK"`
Expected: prints `SYNTAX OK`.

- [ ] **Step 3: Commit**

```bash
git add infra/scripts/02_create_security_groups.sh
git commit -m "feat: add security groups provisioning script"
```

---

### Task 8: EC2 instance script

**Files:**
- Create: `infra/scripts/03_create_ec2.sh`

**Interfaces:**
- Consumes: `VPC_ID`, `EC2_SG_ID` from `infra/outputs.env` (Task 7); key
  pair name `shopops-prod` (Task 6).
- Produces: appends `EC2_INSTANCE_ID`, `EC2_ELASTIC_IP` to
  `infra/outputs.env`, consumed by Task 12's manual SSH/runbook steps.

- [ ] **Step 1: Write `infra/scripts/03_create_ec2.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

REGION="ap-south-1"
KEY_NAME="shopops-prod"
INSTANCE_TYPE="t3.micro"
INFRA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_FILE="$INFRA_DIR/outputs.env"

# shellcheck source=/dev/null
source "$OUT_FILE"

AMI_ID="$(aws ec2 describe-images --region "$REGION" \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
            "Name=state,Values=available" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text)"

SUBNET_ID="$(aws ec2 describe-subnets --region "$REGION" \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=default-for-az,Values=true" \
  --query 'Subnets[0].SubnetId' --output text)"

INSTANCE_ID="$(aws ec2 run-instances --region "$REGION" \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$EC2_SG_ID" \
  --subnet-id "$SUBNET_ID" \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=shopops-prod}]' \
  --query 'Instances[0].InstanceId' --output text)"

echo "Waiting for instance $INSTANCE_ID to enter running state..."
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"

ALLOC_ID="$(aws ec2 allocate-address --region "$REGION" --domain vpc \
  --query 'AllocationId' --output text)"
aws ec2 associate-address --region "$REGION" \
  --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" >/dev/null

ELASTIC_IP="$(aws ec2 describe-addresses --region "$REGION" \
  --allocation-ids "$ALLOC_ID" --query 'Addresses[0].PublicIp' --output text)"

{
  echo "EC2_INSTANCE_ID=$INSTANCE_ID"
  echo "EC2_ELASTIC_IP=$ELASTIC_IP"
} >> "$OUT_FILE"

echo "EC2 instance $INSTANCE_ID running at $ELASTIC_IP"
```

```bash
chmod +x infra/scripts/03_create_ec2.sh
```

- [ ] **Step 2: Syntax-check**

Run: `bash -n infra/scripts/03_create_ec2.sh && echo "SYNTAX OK"`
Expected: prints `SYNTAX OK`.

- [ ] **Step 3: Commit**

```bash
git add infra/scripts/03_create_ec2.sh
git commit -m "feat: add EC2 instance provisioning script"
```

---

### Task 9: RDS instance script

**Files:**
- Create: `infra/scripts/04_create_rds.sh`

**Interfaces:**
- Consumes: `RDS_SG_ID` from `infra/outputs.env` (Task 7).
- Produces: appends `RDS_ENDPOINT`, `RDS_MASTER_USER`,
  `RDS_MASTER_PASSWORD`, `RDS_DB_NAME` to `infra/outputs.env`, consumed
  by Task 10 (migrations) and Task 12 (`.env.prod`).

- [ ] **Step 1: Write `infra/scripts/04_create_rds.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

REGION="ap-south-1"
DB_INSTANCE_ID="shopops-prod"
DB_NAME="shopops"
MASTER_USER="shopops_admin"
INFRA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_FILE="$INFRA_DIR/outputs.env"

# shellcheck source=/dev/null
source "$OUT_FILE"

MASTER_PASSWORD="$(openssl rand -base64 24 | tr -d '=+/')"

aws rds create-db-instance --region "$REGION" \
  --db-instance-identifier "$DB_INSTANCE_ID" \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 16 \
  --master-username "$MASTER_USER" \
  --master-user-password "$MASTER_PASSWORD" \
  --allocated-storage 20 \
  --db-name "$DB_NAME" \
  --vpc-security-group-ids "$RDS_SG_ID" \
  --no-publicly-accessible \
  --backup-retention-period 7 >/dev/null

echo "Waiting for RDS instance to become available (several minutes)..."
aws rds wait db-instance-available --region "$REGION" \
  --db-instance-identifier "$DB_INSTANCE_ID"

RDS_ENDPOINT="$(aws rds describe-db-instances --region "$REGION" \
  --db-instance-identifier "$DB_INSTANCE_ID" \
  --query 'DBInstances[0].Endpoint.Address' --output text)"

{
  echo "RDS_ENDPOINT=$RDS_ENDPOINT"
  echo "RDS_MASTER_USER=$MASTER_USER"
  echo "RDS_MASTER_PASSWORD=$MASTER_PASSWORD"
  echo "RDS_DB_NAME=$DB_NAME"
} >> "$OUT_FILE"

echo "RDS available at $RDS_ENDPOINT"
```

```bash
chmod +x infra/scripts/04_create_rds.sh
```

- [ ] **Step 2: Syntax-check**

Run: `bash -n infra/scripts/04_create_rds.sh && echo "SYNTAX OK"`
Expected: prints `SYNTAX OK`.

- [ ] **Step 3: Commit**

```bash
git add infra/scripts/04_create_rds.sh
git commit -m "feat: add RDS Postgres provisioning script"
```

---

### Task 10: Cognito user pool script

**Files:**
- Create: `infra/scripts/05_create_cognito.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: appends `COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID` to
  `infra/outputs.env`, consumed by Task 12 (`.env.prod`); creates the
  `OperationsManager`/`SupportAgent`/`Viewer` groups required by
  `app/auth.py:12,27-31`; creates the app client with
  `--no-generate-secret` and `ALLOW_USER_PASSWORD_AUTH`, matching how
  `scripts/verify_cognito_tokens.py` calls `initiate_auth`.

- [ ] **Step 1: Write `infra/scripts/05_create_cognito.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

REGION="ap-south-1"
POOL_NAME="shopops-prod"
CLIENT_NAME="shopops-app-client"
INFRA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_FILE="$INFRA_DIR/outputs.env"

USER_POOL_ID="$(aws cognito-idp create-user-pool --region "$REGION" \
  --pool-name "$POOL_NAME" \
  --username-attributes email \
  --auto-verified-attributes email \
  --policies '{"PasswordPolicy":{"MinimumLength":8,"RequireUppercase":true,"RequireLowercase":true,"RequireNumbers":true,"RequireSymbols":false}}' \
  --query 'UserPool.Id' --output text)"

APP_CLIENT_ID="$(aws cognito-idp create-user-pool-client --region "$REGION" \
  --user-pool-id "$USER_POOL_ID" \
  --client-name "$CLIENT_NAME" \
  --no-generate-secret \
  --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH \
  --query 'UserPoolClient.ClientId' --output text)"

for GROUP in OperationsManager SupportAgent Viewer; do
  aws cognito-idp create-group --region "$REGION" \
    --user-pool-id "$USER_POOL_ID" --group-name "$GROUP" >/dev/null
done

{
  echo "COGNITO_USER_POOL_ID=$USER_POOL_ID"
  echo "COGNITO_APP_CLIENT_ID=$APP_CLIENT_ID"
} >> "$OUT_FILE"

echo "Cognito pool $USER_POOL_ID / client $APP_CLIENT_ID created with groups OperationsManager, SupportAgent, Viewer"
```

```bash
chmod +x infra/scripts/05_create_cognito.sh
```

- [ ] **Step 2: Syntax-check**

Run: `bash -n infra/scripts/05_create_cognito.sh && echo "SYNTAX OK"`
Expected: prints `SYNTAX OK`.

- [ ] **Step 3: Commit**

```bash
git add infra/scripts/05_create_cognito.sh
git commit -m "feat: add Cognito user pool provisioning script"
```

---

### Task 11: Migrations script (testable against local Postgres)

**Files:**
- Create: `infra/scripts/06_run_migrations.sh`

**Interfaces:**
- Consumes: `RDS_ENDPOINT`, `RDS_MASTER_USER`, `RDS_MASTER_PASSWORD`,
  `RDS_DB_NAME` from `infra/outputs.env` (Task 9); `db/migrations/*.sql`
  (existing, unmodified).
- Produces: the `shopops_data`/`shopops_views`/`shopops_ops` schemas
  applied to RDS, since `docker-entrypoint-initdb.d` (used for local dev
  in `docker-compose.yml`) only runs on a fresh container's first boot
  and RDS doesn't support it.

Unlike Tasks 6-10, this script's logic can be fully exercised right now
against the project's existing local Postgres — no AWS needed.

- [ ] **Step 1: Write `infra/scripts/06_run_migrations.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$INFRA_DIR/.." && pwd)"
OUT_FILE="$INFRA_DIR/outputs.env"

# shellcheck source=/dev/null
source "$OUT_FILE"

for FILE in "$REPO_ROOT"/db/migrations/*.sql; do
  echo "Applying $(basename "$FILE")..."
  docker run --rm -i \
    -e PGPASSWORD="$RDS_MASTER_PASSWORD" \
    postgres:16-alpine \
    psql -h "$RDS_ENDPOINT" -U "$RDS_MASTER_USER" -d "$RDS_DB_NAME" -v ON_ERROR_STOP=1 \
    < "$FILE"
done

echo "All migrations applied to $RDS_ENDPOINT"
```

```bash
chmod +x infra/scripts/06_run_migrations.sh
```

- [ ] **Step 2: Exercise it end-to-end against the existing local Postgres**

This proves the docker-run-psql approach actually applies the real
migration files correctly, using the project's own local Postgres
(`docker-compose.yml`) as a stand-in for RDS.

Run:
```bash
docker compose up -d postgres
sleep 3
mkdir -p infra
cat > infra/outputs.env <<'EOF'
RDS_ENDPOINT=host.docker.internal
RDS_MASTER_USER=shopops_admin
RDS_MASTER_PASSWORD=changeme
RDS_DB_NAME=shopops_migration_test
EOF
docker exec shopops_postgres psql -U shopops_admin -d shopops -c "CREATE DATABASE shopops_migration_test;"
./infra/scripts/06_run_migrations.sh
docker exec shopops_postgres psql -U shopops_admin -d shopops_migration_test -c "\dt shopops_data.*" | grep -q customers && echo "MIGRATIONS APPLIED"
docker exec shopops_postgres psql -U shopops_admin -d shopops -c "DROP DATABASE shopops_migration_test;"
rm infra/outputs.env
```
Expected: each migration file prints as it's applied with no `psql`
errors, and the final line prints `MIGRATIONS APPLIED`. (`outputs.env`
here is a throwaway test fixture pointing at the local container via
Docker Desktop's `host.docker.internal`, not the real file Task 9's
script produces — it's removed at the end.)

- [ ] **Step 3: Commit**

```bash
git add infra/scripts/06_run_migrations.sh
git commit -m "feat: add RDS migration runner script, verified against local Postgres"
```

---

### Task 12: Infra runbook + manual execution

**Files:**
- Create: `infra/README.md`

**Interfaces:**
- Consumes: every script from Tasks 6-11 and every file from Tasks 1-5.
- Produces: nothing further in the repo — this is the checklist the
  user follows by hand, with real AWS credentials, to actually stand up
  production. This step cannot be completed by an agent: it requires
  the user's AWS console access, their own machine's `aws configure`,
  and SSH access to a not-yet-existing EC2 box.

- [ ] **Step 1: Write `infra/README.md`**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add infra/README.md
git commit -m "docs: add production provisioning runbook"
```

- [ ] **Step 3: Hand off to the user for manual execution**

Everything from here is real AWS/SSH work with real credentials that
only the user can perform. Tell the user: "All the code and scripts are
committed. Follow `infra/README.md` end to end — I can help debug any
step that errors, but steps 1-2 (IAM user, `aws configure`) and step 5
(SSH session) need to run on your machine with your credentials."
