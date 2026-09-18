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
