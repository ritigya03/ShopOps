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
