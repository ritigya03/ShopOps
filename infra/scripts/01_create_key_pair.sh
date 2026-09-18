#!/usr/bin/env bash
set -euo pipefail

REGION="ap-south-1"
KEY_NAME="shopops-prod"
INFRA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PEM_FILE="$INFRA_DIR/$KEY_NAME.pem"

if [ -f "$PEM_FILE" ]; then
  echo "ERROR: $PEM_FILE already exists. AWS never re-exports private key" >&2
  echo "material, so this script refuses to overwrite it (a failed AWS call" >&2
  echo "would otherwise destroy your only copy)." >&2
  echo "" >&2
  echo "If you really want to regenerate the key pair:" >&2
  echo "  1. aws ec2 delete-key-pair --region $REGION --key-name $KEY_NAME" >&2
  echo "  2. rm $PEM_FILE" >&2
  echo "  3. re-run this script" >&2
  exit 1
fi

TMP_FILE="$(mktemp "$INFRA_DIR/.$KEY_NAME.pem.XXXXXX")"
trap 'rm -f "$TMP_FILE"' EXIT

aws ec2 create-key-pair \
  --region "$REGION" \
  --key-name "$KEY_NAME" \
  --query 'KeyMaterial' \
  --output text > "$TMP_FILE"

chmod 400 "$TMP_FILE"
mv "$TMP_FILE" "$PEM_FILE"
trap - EXIT
echo "Key pair saved to $PEM_FILE"
