#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed"
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is not installed"
  exit 1
fi

HOST_IP="$(hostname -I | awk '{print $1}')"
DOMAIN="${1:-$HOST_IP}"
IP_SAN="${2:-$HOST_IP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

./scripts/generate-self-signed.sh "$DOMAIN" "$IP_SAN" "nginx/certs"

docker compose up -d --build

echo "Deployment complete."
echo "Open: https://$DOMAIN"
