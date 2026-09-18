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
