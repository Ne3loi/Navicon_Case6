#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-localhost}"
IP_SAN="${2:-127.0.0.1}"
CERT_DIR="${3:-nginx/certs}"

mkdir -p "$CERT_DIR"

openssl req \
  -x509 \
  -nodes \
  -newkey rsa:4096 \
  -sha256 \
  -days 365 \
  -keyout "$CERT_DIR/navicon-selfsigned.key" \
  -out "$CERT_DIR/navicon-selfsigned.crt" \
  -subj "/C=RU/ST=Moscow/L=Moscow/O=Navicon/OU=AI Sprint/CN=$DOMAIN" \
  -addext "subjectAltName=DNS:$DOMAIN,DNS:localhost,IP:$IP_SAN,IP:127.0.0.1"

chmod 600 "$CERT_DIR/navicon-selfsigned.key"

echo "Generated: $CERT_DIR/navicon-selfsigned.crt"
echo "Generated: $CERT_DIR/navicon-selfsigned.key"
