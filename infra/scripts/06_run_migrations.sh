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
