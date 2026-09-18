#!/usr/bin/env bash
set -euo pipefail

IP="${1:?Usage: generate-self-signed-cert.sh <elastic-ip>}"
CERT_DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -days 365 \
  -newkey rsa:2048 \
  -keyout "$CERT_DIR/privkey.pem" \
  -out "$CERT_DIR/fullchain.pem" \
  -subj "/CN=$IP"

echo "Certificate written to $CERT_DIR"
