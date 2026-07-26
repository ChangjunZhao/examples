#!/usr/bin/env bash
# Issue a certificate covering <domain> and *.<domain> via the DNS-01 challenge.
#
# DNS-01 rather than the more familiar HTTP-01 because Let's Encrypt only issues
# wildcards that way — and the wildcard is not optional: E2B addresses a service
# inside a sandbox as <port>-<sandboxID>.<domain>, and the sandbox ID does not
# exist until the sandbox does. You cannot pre-issue certificates for names you
# cannot enumerate.
set -euo pipefail

DOMAIN=${SANDRPOD_DOMAIN:?set SANDRPOD_DOMAIN}
EMAIL=${ACME_EMAIL:?set ACME_EMAIL}
LEGO_DIR=/etc/lego
LEGO_VER=v4.29.0

set -a; set -a; source "$(dirname "$0")/dns.env"; set +a; set +a

if ! command -v lego >/dev/null; then
  echo "==> installing lego $LEGO_VER"
  cd /tmp
  curl -fsSL -o lego.tar.gz \
    "https://github.com/go-acme/lego/releases/download/${LEGO_VER}/lego_${LEGO_VER}_linux_amd64.tar.gz"
  tar -xzf lego.tar.gz lego && install -m755 lego /usr/local/bin/lego && rm -f lego lego.tar.gz
fi
lego --version

mkdir -p "$LEGO_DIR"
echo "==> requesting certificate (DNS-01)"
# lego polls the authoritative nameservers for the TXT record it just wrote.
# DNSPod took ~100s per domain to serve it consistently; be generous here.
lego --email "$EMAIL" --accept-tos \
     --dns tencentcloud \
     --dns.propagation-wait 90s \
     -d "$DOMAIN" -d "*.$DOMAIN" \
     --path "$LEGO_DIR" \
     run

echo "==> issued"
CRT="$LEGO_DIR/certificates/_.${DOMAIN}.crt"
openssl x509 -in "$CRT" -noout -subject -issuer -dates
echo -n "  SAN: "; openssl x509 -in "$CRT" -noout -ext subjectAltName | tail -1
