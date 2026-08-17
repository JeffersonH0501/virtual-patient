#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TLS_DIR="$ROOT_DIR/virtual-patient-ui/ssl"

usage() {
  echo "Usage: bash setup-tls.sh CERTIFICATE_FILE PRIVATE_KEY_FILE" >&2
}

if [[ $# -ne 2 ]]; then
  usage
  exit 2
fi

certificate_source="$1"
key_source="$2"

for source_file in "$certificate_source" "$key_source"; do
  if [[ ! -f "$source_file" ]]; then
    echo "File not found: $source_file" >&2
    exit 1
  fi
done

certificate_public_key="$(openssl x509 -in "$certificate_source" -pubkey -noout | openssl pkey -pubin -outform pem)"
private_public_key="$(openssl pkey -in "$key_source" -pubout -outform pem)"

if [[ "$certificate_public_key" != "$private_public_key" ]]; then
  echo "The certificate and private key do not match" >&2
  exit 1
fi

mkdir -p "$TLS_DIR"
cp "$certificate_source" "$TLS_DIR/cert.pem"
cp "$key_source" "$TLS_DIR/key.pem"
chmod 644 "$TLS_DIR/cert.pem"
chmod 600 "$TLS_DIR/key.pem"

openssl x509 -in "$TLS_DIR/cert.pem" -noout -subject -issuer -dates
echo "TLS files installed in virtual-patient-ui/ssl"
echo "Continue with: bash deploy-full.sh setup"
