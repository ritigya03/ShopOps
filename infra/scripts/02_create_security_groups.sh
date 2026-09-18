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
