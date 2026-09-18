#!/usr/bin/env bash
set -euo pipefail

# Free, trusted HTTPS cert with no domain purchase: nip.io resolves
# "<ip-with-dashes>.nip.io" to that IP itself, and Let's Encrypt only
# needs a real resolvable domain name to issue a cert via the HTTP-01
# challenge — nip.io satisfies that for free.
#
# Usage: ./nginx/generate-letsencrypt-cert.sh <elastic-ip> <your-email>
# Run this ON THE EC2 BOX, from /opt/shopops, with the compose stack
# already up (this script stops nginx briefly to free port 80 for the
# challenge, then leaves the stack down — bring it back up afterwards).

IP="${1:?Usage: generate-letsencrypt-cert.sh <elastic-ip> <email>}"
EMAIL="${2:?Usage: generate-letsencrypt-cert.sh <elastic-ip> <email>}"
DOMAIN="$(echo "$IP" | tr '.' '-').nip.io"
CERT_DIR="$(cd "$(dirname "$0")" && pwd)/certs"
COMPOSE_FILE="$(cd "$(dirname "$0")/.." && pwd)/docker-compose.prod.yml"

echo "Requesting a Let's Encrypt cert for $DOMAIN ..."

docker compose -f "$COMPOSE_FILE" stop nginx

docker run --rm \
  -p 80:80 \
  -v "$CERT_DIR/letsencrypt:/etc/letsencrypt" \
  certbot/certbot certonly --standalone \
  -d "$DOMAIN" \
  --non-interactive --agree-tos -m "$EMAIL"

# certbot's container writes these as root (privkey.pem is 0600, root-owned)
# since it runs as root inside its own container — sudo is required to read
# them back out on the host, and to restore normal ownership afterward so
# later re-runs of this script (as a non-root user) don't need sudo again.
sudo cp "$CERT_DIR/letsencrypt/live/$DOMAIN/fullchain.pem" "$CERT_DIR/fullchain.pem"
sudo cp "$CERT_DIR/letsencrypt/live/$DOMAIN/privkey.pem" "$CERT_DIR/privkey.pem"
sudo chown "$(id -u):$(id -g)" "$CERT_DIR/fullchain.pem" "$CERT_DIR/privkey.pem"

echo "Certificate for $DOMAIN written to $CERT_DIR (fullchain.pem, privkey.pem)."
echo "Bring the stack back up: docker compose -f docker-compose.prod.yml up -d"
echo ""
echo "NOTE: Let's Encrypt certs expire in 90 days. Re-run this script before"
echo "then to renew (it's safe to re-run)."
